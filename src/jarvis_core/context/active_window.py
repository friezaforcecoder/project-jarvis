"""Safe active foreground-window context collection."""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Callable
from enum import StrEnum
from pathlib import PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field


class ActiveWindowUnavailableReason(StrEnum):
    """Stable reasons active-window context may be partially unavailable."""

    UNSUPPORTED_PLATFORM = "unsupported_platform"
    NO_ACTIVE_WINDOW = "no_active_window"
    WINDOW_TITLE_UNAVAILABLE = "window_title_unavailable"
    APPLICATION_NAME_UNAVAILABLE = "application_name_unavailable"


class ActiveWindowCollectionError(Exception):
    """Raised when active-window context collection fails unexpectedly."""


class ActiveWindowContext(BaseModel):
    """Safe active-window context returned by JARVIS Core."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    platform_family: str = Field(min_length=1)
    application_name: str | None = None
    window_title: str | None = None
    reason: ActiveWindowUnavailableReason | None = None


class WindowsForegroundWindowSnapshot(BaseModel):
    """Internal Windows foreground-window snapshot before public normalization."""

    model_config = ConfigDict(extra="forbid")

    has_foreground_window: bool
    application_name: str | None = None
    window_title: str | None = None


ActiveWindowCollector = Callable[[], ActiveWindowContext]

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_NAME_BUFFER_SIZE = 32768


def collect_active_window() -> ActiveWindowContext:
    """Collect the current active foreground-window context."""

    platform_family = platform.system() or "Unknown"
    if platform_family != "Windows":
        return ActiveWindowContext(
            available=False,
            platform_family=platform_family,
            application_name=None,
            window_title=None,
            reason=ActiveWindowUnavailableReason.UNSUPPORTED_PLATFORM,
        )

    try:
        snapshot = _collect_windows_foreground_window()
        return active_window_context_from_windows_snapshot(
            snapshot,
            platform_family=platform_family,
        )
    except ActiveWindowCollectionError:
        raise
    except Exception as exc:
        raise ActiveWindowCollectionError("Active window collection failed.") from exc


async def collect_active_window_async(
    collector: ActiveWindowCollector | None = None,
) -> ActiveWindowContext:
    """Collect active-window context without blocking the async event loop."""

    resolved_collector = collector or collect_active_window
    return await asyncio.to_thread(resolved_collector)


def active_window_context_from_windows_snapshot(
    snapshot: WindowsForegroundWindowSnapshot,
    *,
    platform_family: str = "Windows",
) -> ActiveWindowContext:
    """Map a Windows foreground-window snapshot into the public result contract."""

    if not snapshot.has_foreground_window:
        return ActiveWindowContext(
            available=False,
            platform_family=platform_family,
            application_name=None,
            window_title=None,
            reason=ActiveWindowUnavailableReason.NO_ACTIVE_WINDOW,
        )

    reason: ActiveWindowUnavailableReason | None = None
    if snapshot.window_title is None:
        reason = ActiveWindowUnavailableReason.WINDOW_TITLE_UNAVAILABLE
    elif snapshot.application_name is None:
        reason = ActiveWindowUnavailableReason.APPLICATION_NAME_UNAVAILABLE

    return ActiveWindowContext(
        available=True,
        platform_family=platform_family,
        application_name=snapshot.application_name,
        window_title=snapshot.window_title,
        reason=reason,
    )


def _collect_windows_foreground_window() -> WindowsForegroundWindowSnapshot:
    """Collect the foreground top-level window using native Windows APIs."""

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return WindowsForegroundWindowSnapshot(has_foreground_window=False)

    return WindowsForegroundWindowSnapshot(
        has_foreground_window=True,
        window_title=_read_window_title(ctypes, user32, hwnd),
        application_name=_read_application_name(ctypes, wintypes, user32, kernel32, hwnd),
    )


def _read_window_title(ctypes_module: object, user32: object, hwnd: object) -> str | None:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return None

    buffer = ctypes_module.create_unicode_buffer(length + 1)
    copied = user32.GetWindowTextW(hwnd, buffer, length + 1)
    if copied <= 0:
        return None

    title = buffer.value.strip()
    return title or None


def _read_application_name(
    ctypes_module: object,
    wintypes: object,
    user32: object,
    kernel32: object,
    hwnd: object,
) -> str | None:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes_module.byref(process_id))
    if not process_id.value:
        return None

    process = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        process_id.value,
    )
    if not process:
        return None

    try:
        size = wintypes.DWORD(_PROCESS_NAME_BUFFER_SIZE)
        buffer = ctypes_module.create_unicode_buffer(size.value)
        success = kernel32.QueryFullProcessImageNameW(
            process,
            0,
            buffer,
            ctypes_module.byref(size),
        )
        if not success:
            return None

        return _sanitize_process_image_name(buffer.value)
    finally:
        kernel32.CloseHandle(process)


def _sanitize_process_image_name(process_image_name: str) -> str | None:
    name = PureWindowsPath(process_image_name).stem.strip()
    return name or None
