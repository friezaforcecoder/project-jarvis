"""Local context collection boundaries for JARVIS Core."""

from jarvis_core.context.active_window import (
    ActiveWindowCollectionError,
    ActiveWindowCollector,
    ActiveWindowContext,
    ActiveWindowUnavailableReason,
    WindowsForegroundWindowSnapshot,
    active_window_context_from_windows_snapshot,
    collect_active_window,
    collect_active_window_async,
)
from jarvis_core.context.system_status import (
    CPUStatus,
    LocalSystemStatus,
    MemoryStatus,
    PowerStatus,
    SystemStatusCollector,
    SystemRuntimeStatus,
    SystemStatusCollectionError,
    collect_system_status,
    collect_system_status_async,
)
from jarvis_core.context.visible_applications import (
    VisibleApplicationsCollectionError,
    VisibleApplicationsCollector,
    VisibleApplicationsContext,
    VisibleApplicationsUnavailableReason,
    collect_visible_applications,
    collect_visible_applications_async,
)

__all__ = [
    "ActiveWindowCollectionError",
    "ActiveWindowCollector",
    "ActiveWindowContext",
    "ActiveWindowUnavailableReason",
    "CPUStatus",
    "LocalSystemStatus",
    "MemoryStatus",
    "PowerStatus",
    "SystemStatusCollector",
    "SystemRuntimeStatus",
    "SystemStatusCollectionError",
    "WindowsForegroundWindowSnapshot",
    "VisibleApplicationsCollectionError",
    "VisibleApplicationsCollector",
    "VisibleApplicationsContext",
    "VisibleApplicationsUnavailableReason",
    "active_window_context_from_windows_snapshot",
    "collect_active_window",
    "collect_active_window_async",
    "collect_system_status",
    "collect_system_status_async",
    "collect_visible_applications",
    "collect_visible_applications_async",
]
