from __future__ import annotations

import ctypes
import json
import threading
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest
from pydantic import ValidationError

from jarvis_core.context import visible_applications as collection
from jarvis_core.context.visible_applications import (
    VisibleApplicationsCollectionError,
    VisibleApplicationsContext,
    VisibleApplicationsUnavailableReason,
    collect_visible_applications,
    collect_visible_applications_async,
)


class FakeNativeWindows:
    """Only the allowed WinAPI calls are available; there is no title reader."""

    def __init__(self, windows: dict[int, dict[str, object]]) -> None:
        self.windows = windows
        self.last_error = 0
        self.enumeration_succeeds = True
        self.process_queries: list[int] = []
        self.user32 = SimpleNamespace(
            GetDesktopWindow=lambda: 900,
            GetShellWindow=lambda: 901,
            EnumWindows=self.enum_windows,
            IsWindowVisible=lambda hwnd: self.windows.get(hwnd, {}).get("visible", True),
            GetWindowThreadProcessId=self.window_process,
        )
        self.dwmapi = SimpleNamespace(DwmGetWindowAttribute=self.window_attribute)

    def api(self) -> collection._NativeWindowApi:
        return collection._NativeWindowApi(
            self.user32,
            self.dwmapi,
            self.window_long,
            lambda callback: callback,
            get_last_error=lambda: self.last_error,
            set_last_error=self.set_last_error,
        )

    def set_last_error(self, value: int) -> None:
        self.last_error = value

    def enum_windows(self, callback, parameter: int) -> bool:
        for hwnd in self.windows:
            if not callback(hwnd, parameter):
                return False
        return self.enumeration_succeeds

    def window_long(self, hwnd: int, index: int) -> int:
        window = self.windows[hwnd]
        if window.get("style_error"):
            self.last_error = 1400
            return 0
        return int(window.get("style" if index == -16 else "exstyle", 0))

    def window_attribute(self, hwnd: int, attribute: int, output, size: int) -> int:
        assert attribute == 14  # DWMWA_CLOAKED; no other attribute is requested.
        assert size == ctypes.sizeof(wintypes.DWORD)
        window = self.windows[hwnd]
        ctypes.cast(output, ctypes.POINTER(wintypes.DWORD)).contents.value = int(
            window.get("cloaked", 0)
        )
        return int(window.get("dwm_result", 0))

    def window_process(self, hwnd: int, output) -> int:
        self.process_queries.append(hwnd)
        window = self.windows[hwnd]
        ctypes.cast(output, ctypes.POINTER(wintypes.DWORD)).contents.value = int(
            window.get("pid", hwnd + 1000)
        )
        return int(window.get("thread_id", 1))


@pytest.mark.parametrize("platform_name, expected", [("Linux", "Linux"), ("Darwin", "Darwin"), ("", "Unknown")])
def test_unsupported_platform_never_loads_windows_or_queries_processes(
    monkeypatch, platform_name: str, expected: str
) -> None:
    native = Mock(side_effect=AssertionError("Must not load native libraries."))
    process = Mock(side_effect=AssertionError("Must not query processes."))
    monkeypatch.setattr(collection.platform, "system", lambda: platform_name)
    monkeypatch.setattr(collection, "_create_windows_api", native)
    monkeypatch.setattr(collection.psutil, "Process", process)

    result = collect_visible_applications()

    assert result.model_dump(mode="json") == {
        "available": False,
        "platform_family": expected,
        "applications": [],
        "reason": "unsupported_platform",
    }
    assert result.reason is VisibleApplicationsUnavailableReason.UNSUPPORTED_PLATFORM
    native.assert_not_called()
    process.assert_not_called()


def test_successful_empty_desktop_is_available(monkeypatch) -> None:
    fake = FakeNativeWindows({})
    monkeypatch.setattr(collection.platform, "system", lambda: "Windows")
    monkeypatch.setattr(collection, "_create_windows_api", fake.api)

    assert collect_visible_applications().model_dump(mode="json") == {
        "available": True,
        "platform_family": "Windows",
        "applications": [],
        "reason": None,
    }


@pytest.mark.parametrize("reverse_order", [False, True])
def test_names_are_deduplicated_and_sorted_independently_of_window_order(reverse_order: bool) -> None:
    names = ["chrome.exe", "Code.exe", "Chrome.EXE", "code.exe", "  Notepad.exe  ", "My.Tool.exe"]
    entries = [(index, {"pid": index}) for index in range(1, len(names) + 1)]
    fake = FakeNativeWindows(dict(reversed(entries) if reverse_order else entries))

    result = collection._collect_application_names(fake.api(), lambda pid: names[pid - 1])

    assert result == ["Chrome", "Code", "My.Tool", "Notepad"]


def test_only_eligible_windows_have_process_names_queried(monkeypatch) -> None:
    fake = FakeNativeWindows(
        {
            900: {},  # desktop
            901: {},  # shell desktop
            2: {"visible": False},
            3: {"style": 0x40000000},  # WS_CHILD
            4: {"exstyle": 0x80},  # WS_EX_TOOLWINDOW
            5: {"cloaked": 1},
            6: {"cloaked": 2},
            7: {"cloaked": 4},
            8: {"dwm_result": -2147024891},
            9: {"style_error": True},
            10: {"pid": 0},
            11: {"thread_id": 0},
            12: {"pid": 2345},
        }
    )
    process = Mock(return_value=SimpleNamespace(name=lambda: "Allowed.exe"))
    forbidden = Mock(side_effect=AssertionError("Unrestricted process enumeration is forbidden."))
    monkeypatch.setattr(collection.psutil, "Process", process)
    monkeypatch.setattr(collection.psutil, "process_iter", forbidden)
    monkeypatch.setattr(collection.psutil, "pids", forbidden)

    assert collection._collect_application_names(fake.api()) == ["Allowed"]

    process.assert_called_once_with(2345)
    forbidden.assert_not_called()
    assert fake.process_queries == [10, 11, 12, 12]


@pytest.mark.parametrize(
    "failure",
    [psutil.NoSuchProcess(1001), psutil.AccessDenied(1001), psutil.ZombieProcess(1001), OSError("WINDOW_GONE")],
)
def test_disappearing_or_inaccessible_process_skips_only_its_window(failure: Exception) -> None:
    fake = FakeNativeWindows({1: {}, 2: {}})

    def process_name(pid: int) -> str:
        if pid == 1001:
            raise failure
        return "Remaining.exe"

    assert collection._collect_application_names(fake.api(), process_name) == ["Remaining"]


def test_inaccessible_window_skips_only_its_window() -> None:
    fake = FakeNativeWindows({1: {}, 2: {}})
    original = fake.user32.IsWindowVisible

    def visible(hwnd: int) -> bool:
        if hwnd == 1:
            raise OSError("RAW_WINDOW_ERROR")
        return original(hwnd)

    fake.user32.IsWindowVisible = visible
    assert collection._collect_application_names(fake.api(), lambda pid: "Remaining.exe") == ["Remaining"]


@pytest.mark.parametrize("change", [{"visible": False}, {"cloaked": 1}, {"pid": 9999}, {"thread_id": 0}])
def test_window_changed_during_name_query_is_skipped(change: dict[str, object]) -> None:
    fake = FakeNativeWindows({1: {}, 2: {}})

    def process_name(pid: int) -> str:
        if pid == 1001:
            fake.windows[1].update(change)
            return "Stale.exe"
        return "Stable.exe"

    assert collection._collect_application_names(fake.api(), process_name) == ["Stable"]


@pytest.mark.parametrize("invalid_name", ["", "   ", ".exe", "C:/secret/App.exe", r"C:\secret\App.exe", "bad\x00name.exe"])
def test_blank_or_path_valued_process_names_are_not_exposed(invalid_name: str) -> None:
    fake = FakeNativeWindows({1: {}})
    assert collection._collect_application_names(fake.api(), lambda pid: invalid_name) == []


def test_enumeration_failure_does_not_return_a_partial_success(monkeypatch, caplog) -> None:
    fake = FakeNativeWindows({1: {}})
    fake.enumeration_succeeds = False
    read_name = Mock(side_effect=AssertionError("Partial enumeration must not be consumed."))
    monkeypatch.setattr(collection.platform, "system", lambda: "Windows")
    monkeypatch.setattr(collection, "_create_windows_api", fake.api)
    monkeypatch.setattr(collection, "_read_process_name", read_name)

    with pytest.raises(VisibleApplicationsCollectionError) as exc_info:
        collect_visible_applications()

    assert str(exc_info.value) == "Visible applications collection failed."
    read_name.assert_not_called()
    assert caplog.records == []


@pytest.mark.parametrize("during_name_query", [False, True])
def test_unexpected_total_failure_has_a_safe_public_exception(monkeypatch, caplog, during_name_query: bool) -> None:
    sentinel = "RAW_FAILURE_C:/private/account/key.txt"
    fake = FakeNativeWindows({1: {}})
    failure = Mock(side_effect=RuntimeError(sentinel))
    monkeypatch.setattr(collection.platform, "system", lambda: "Windows")
    monkeypatch.setattr(collection, "_create_windows_api", fake.api if during_name_query else failure)
    if during_name_query:
        monkeypatch.setattr(collection, "_read_process_name", failure)

    with pytest.raises(VisibleApplicationsCollectionError) as exc_info:
        collect_visible_applications()

    assert str(exc_info.value) == "Visible applications collection failed."
    assert sentinel not in str(exc_info.value)
    assert caplog.records == []


@pytest.mark.parametrize("field", ["window_title", "pid", "hwnd", "path", "command_line"])
def test_result_contract_forbids_native_or_sensitive_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        VisibleApplicationsContext.model_validate(
            {"available": True, "platform_family": "Windows", "applications": [], field: "SENTINEL"}
        )


def test_collected_result_contains_only_application_labels(monkeypatch, caplog) -> None:
    fake = FakeNativeWindows({1: {"pid": 98765}})
    monkeypatch.setattr(collection.platform, "system", lambda: "Windows")
    monkeypatch.setattr(collection, "_create_windows_api", fake.api)
    monkeypatch.setattr(collection, "_read_process_name", lambda pid: "ApplicationNameSentinel.exe")

    result = collect_visible_applications()

    assert json.loads(result.model_dump_json()) == {
        "available": True,
        "platform_family": "Windows",
        "applications": ["ApplicationNameSentinel"],
        "reason": None,
    }
    assert "98765" not in result.model_dump_json()
    assert caplog.records == []


@pytest.mark.anyio
async def test_async_wrapper_runs_injected_collector_off_the_event_loop() -> None:
    event_loop_thread = threading.get_ident()
    collected_threads: list[int] = []
    expected = VisibleApplicationsContext(available=True, platform_family="Windows", applications=[])

    def collector() -> VisibleApplicationsContext:
        collected_threads.append(threading.get_ident())
        return expected

    assert await collect_visible_applications_async(collector) is expected
    assert len(collected_threads) == 1
    assert collected_threads[0] != event_loop_thread


@pytest.mark.anyio
async def test_async_wrapper_defaults_to_public_collector(monkeypatch) -> None:
    expected = VisibleApplicationsContext(available=True, platform_family="Windows", applications=[])
    collector = Mock(return_value=expected)
    monkeypatch.setattr(collection, "collect_visible_applications", collector)

    assert await collect_visible_applications_async() is expected
    collector.assert_called_once_with()


@pytest.mark.parametrize("pointer_size", [4, 8])
def test_native_bindings_use_pointer_sized_window_handles_and_no_title_api(monkeypatch, pointer_size: int) -> None:
    user32 = SimpleNamespace(
        EnumWindows=Mock(),
        GetDesktopWindow=Mock(return_value=900),
        GetShellWindow=Mock(return_value=901),
        IsWindowVisible=Mock(),
        GetWindowThreadProcessId=Mock(),
        GetWindowLongW=Mock(),
        GetWindowLongPtrW=Mock(),
    )
    dwmapi = SimpleNamespace(DwmGetWindowAttribute=Mock())
    libraries = {"user32": user32, "dwmapi": dwmapi}
    load_library = Mock(side_effect=lambda name, **kwargs: libraries[name])
    callback_type = object()
    create_callback = Mock(return_value=callback_type)
    real_sizeof = ctypes.sizeof
    monkeypatch.setattr(ctypes, "WinDLL", load_library, raising=False)
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", create_callback, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda value: None, raising=False)
    monkeypatch.setattr(ctypes, "sizeof", lambda value: pointer_size if value is ctypes.c_void_p else real_sizeof(value))

    api = collection._create_windows_api()

    assert isinstance(api, collection._NativeWindowApi)
    assert [call.args[0] for call in load_library.call_args_list] == ["user32", "dwmapi"]
    create_callback.assert_called_once_with(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    assert user32.EnumWindows.argtypes == [callback_type, wintypes.LPARAM]
    assert user32.GetDesktopWindow.restype is wintypes.HWND
    assert user32.GetShellWindow.restype is wintypes.HWND
    chosen_long = user32.GetWindowLongPtrW if pointer_size == 8 else user32.GetWindowLongW
    assert chosen_long.argtypes == [wintypes.HWND, ctypes.c_int]
    assert chosen_long.restype is ctypes.c_ssize_t
    assert dwmapi.DwmGetWindowAttribute.restype is ctypes.c_long
