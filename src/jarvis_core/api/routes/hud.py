"""Local JARVIS Operator HUD routes."""

from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import FileResponse

from jarvis_core.hud import asset_path

router = APIRouter(tags=["hud"])

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self'; "
        "connect-src 'self'; "
        "font-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


@router.get("/", include_in_schema=False)
def get_hud() -> FileResponse:
    """Return the packaged Operator HUD without server-rendered user data."""

    return FileResponse(
        asset_path("index.html"),
        media_type="text/html",
        headers=_SECURITY_HEADERS,
    )


@router.get("/assets/hud.css", include_in_schema=False)
def get_hud_styles() -> FileResponse:
    """Return the packaged HUD stylesheet."""

    return FileResponse(
        asset_path("hud.css"),
        media_type="text/css",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/assets/hud.js", include_in_schema=False)
def get_hud_script() -> FileResponse:
    """Return the packaged HUD controller."""

    return FileResponse(
        asset_path("hud.js"),
        media_type="text/javascript",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
