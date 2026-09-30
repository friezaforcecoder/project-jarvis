"""Application names from visible top-level desktop windows, without window titles."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Protocol

import psutil
from pydantic import BaseModel, ConfigDict, Field


class VisibleApplicationsUnavailableReason(StrEnum):
    """Stable reasons visible-application collection is unavailable."""

    UNSUPPORTED_PLATFORM = "unsupported_platform"


class VisibleApplicationsCollectionError(Exception):
    """Raised when the complete visible-application collection fails."""


class VisibleApplicationsContext(BaseModel):
    """Public context contains application labels, never native window details."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    platform_family: str = Field(min_length=1)
    applications: list[str] = Field(default_factory=list)
    reason: VisibleApplicationsUnavailableReason | None = None


VisibleApplicationsCollector = Callable[[], VisibleApplicationsContext]

_GWL_STYLE = -16
_GWL_EXSTYLE = -20
_WS_CHILD = 0x40000000
_WS_EX_TOOLWINDOW = 0x00000080
_DWMWA_CLOAKED = 14
_COLLECTION_ERROR_MESSAGE = "Visible applications collection failed."


class _WindowApi(Protocol):
    """Small injectable native boundary; process IDs never leave the collector."""

    def enumerate_windows(self) -> tuple[int, ...]: ...

    def is_application_window(self, hwnd: int) -> bool: ...

    def process_id(self, hwnd: int) -> int | None: ...


def collect_visible_applications() -> VisibleApplicationsContext:
    """Collect owning executable basenames of visible Windows desktop windows."""

    platform_family = platform.system() or "Unknown"
    if platform_family != "Windows":
        return VisibleApplicationsContext(
            available=False,
            platform_family=platform_family,
            applications=[],
            reason=VisibleApplicationsUnavailableReason.UNSUPPORTED_PLATFORM,
        )

    try:
        return VisibleApplicationsContext(
            available=True,
            platform_family=platform_family,
            applications=_collect_application_names(_create_windows_api()),
        )
    except Exception as exc:
        raise VisibleApplicationsCollectionError(_COLLECTION_ERROR_MESSAGE) from exc


async def collect_visible_applications_async(
    collector: VisibleApplicationsCollector | None = None,
) -> VisibleApplicationsContext:
    """Keep synchronous native queries off the async event loop."""

    return await asyncio.to_thread(collector or collect_visible_applications)


def _collect_application_names(
    api: _WindowApi,
    process_name: Callable[[int], str] | None = None,
) -> list[str]:
    """Skip individual disappearing/inaccessible windows, retaining stable names."""

    read_name = process_name or _read_process_name
    names: set[str] = set()
    for hwnd in api.enumerate_windows():
        try:
            if not api.is_application_window(hwnd):
                continue
            process_id = api.process_id(hwnd)
            if not process_id:
                continue
            name = _application_label(read_name(process_id))
            if name is None:
                continue
            # A handle can disappear or be reused while its owner's name is read.
            if not api.is_application_window(hwnd) or api.process_id(hwnd) != process_id:
                continue
        except (OSError, psutil.Error):
            continue
        names.add(name)

    # Case-insensitive ordering/deduplication is independent of enumeration order.
    # Retain the lexicographically smallest exact spelling for each casefold key.
    unique: dict[str, str] = {}
    for name in sorted(names, key=lambda value: (value.casefold(), value)):
        unique.setdefault(name.casefold(), name)
    return list(unique.values())


def _read_process_name(process_id: int) -> str:
    """Inspect only the process identified by a qualifying enumerated window."""

    return psutil.Process(process_id).name()


def _application_label(process_name: str) -> str | None:
    """Use the executable basename as an untrusted label, without its .exe suffix."""

    name = process_name.strip()
    if not name or any(character in name for character in ("/", "\\", ":", "\x00")):
        return None
    if name.casefold().endswith(".exe"):
        name = name[:-4].strip()
    return name or None


class _NativeWindowApi:
    """Native calls are injectable so unit tests never inspect the real desktop."""

    def __init__(
        self,
        user32: Any,
        dwmapi: Any,
        window_long: Any,
        callback_type: Any,
        *,
        get_last_error: Callable[[], int],
        set_last_error: Callable[[int], Any],
    ) -> None:
        self._user32 = user32
        self._dwmapi = dwmapi
        self._window_long = window_long
        self._callback_type = callback_type
        self._get_last_error = get_last_error
        self._set_last_error = set_last_error
        self._desktop_windows = {user32.GetDesktopWindow(), user32.GetShellWindow()}

    def enumerate_windows(self) -> tuple[int, ...]:
        handles: list[int] = []
        callback_failed = False

        def receive_window(hwnd: int, _parameter: int) -> bool:
            nonlocal callback_failed
            try:
                handles.append(hwnd)
                return True
            except Exception:
                # ctypes otherwise prints callback exceptions directly to stderr.
                callback_failed = True
                return False

        callback = self._callback_type(receive_window)
        if not self._user32.EnumWindows(callback, 0) or callback_failed:
            raise VisibleApplicationsCollectionError(_COLLECTION_ERROR_MESSAGE)
        return tuple(handles)

    def is_application_window(self, hwnd: int) -> bool:
        import ctypes
        from ctypes import wintypes

        if not hwnd or hwnd in self._desktop_windows or not self._user32.IsWindowVisible(hwnd):
            return False
        for index, excluded_style in ((_GWL_STYLE, _WS_CHILD), (_GWL_EXSTYLE, _WS_EX_TOOLWINDOW)):
            self._set_last_error(0)
            style = self._window_long(hwnd, index)
            if (not style and self._get_last_error()) or style & excluded_style:
                return False
        cloaked = wintypes.DWORD()
        result = self._dwmapi.DwmGetWindowAttribute(
            hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        # An unreadable visibility attribute is not evidence of a visible window.
        return result == 0 and cloaked.value == 0

    def process_id(self, hwnd: int) -> int | None:
        import ctypes
        from ctypes import wintypes

        process_id = wintypes.DWORD()
        thread_id = self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return process_id.value if thread_id and process_id.value else None


def _create_windows_api() -> _NativeWindowApi:
    """Load Windows libraries lazily; importing this module is platform-neutral."""

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetDesktopWindow.argtypes = []
    user32.GetDesktopWindow.restype = wintypes.HWND
    user32.GetShellWindow.argtypes = []
    user32.GetShellWindow.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    # On 32-bit Windows GetWindowLongPtrW is a C macro for GetWindowLongW.
    window_long = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
    window_long.argtypes = [wintypes.HWND, ctypes.c_int]
    window_long.restype = ctypes.c_ssize_t
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
    ]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    return _NativeWindowApi(
        user32,
        dwmapi,
        window_long,
        callback_type,
        get_last_error=ctypes.get_last_error,
        set_last_error=ctypes.set_last_error,
    )
