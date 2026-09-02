"""Health endpoint for JARVIS Core."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Semantic health status for the core service."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    service: str = Field(min_length=1)
    version: str = Field(min_length=1)


@router.get("/health", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse:
    """Return basic service health metadata."""

    settings = request.app.state.settings
    return HealthResponse(service=settings.service_name, version=settings.version)
