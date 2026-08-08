from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "not_ready"]
    environment: str
    missing_configuration: list[str] = []


@router.get("/health/live", response_model=HealthResponse)
def live(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.environment)


@router.get("/health/ready", response_model=HealthResponse)
def ready(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    missing = settings.missing_runtime_configuration()
    if missing and settings.environment not in {"local", "test"}:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="not_ready",
            environment=settings.environment,
            missing_configuration=missing,
        )
    return HealthResponse(status="ok", environment=settings.environment)
