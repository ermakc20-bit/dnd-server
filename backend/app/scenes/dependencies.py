from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException

from app.config import Settings, get_settings
from app.scenes.repository import SceneRepository
from app.scenes.service import SceneService


@lru_cache
def build_scene_service(database_url: str) -> SceneService:
    return SceneService(SceneRepository(database_url))


def get_scene_service(settings: Annotated[Settings, Depends(get_settings)]) -> SceneService:
    if settings.database_url is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "database_unavailable", "message": "База данных не настроена"},
        )
    return build_scene_service(settings.database_url)
