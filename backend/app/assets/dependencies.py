from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException

from app.assets.service import AssetService
from app.assets.storage import PrivateStorage, SupabasePrivateStorage, UnavailableStorage
from app.config import Settings, get_settings


@lru_cache
def build_asset_service(
    database_url: str, url: str | None, service_key: str | None
) -> AssetService:
    storage: PrivateStorage = UnavailableStorage()
    if url and service_key:
        storage = SupabasePrivateStorage(url, service_key)
    return AssetService(database_url, storage)


def get_asset_service(settings: Annotated[Settings, Depends(get_settings)]) -> AssetService:
    if settings.database_url is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "database_unavailable", "message": "База данных не настроена"},
        )
    key = settings.supabase_service_role_key
    return build_asset_service(
        settings.database_url,
        str(settings.supabase_url) if settings.supabase_url else None,
        key.get_secret_value() if key else None,
    )
