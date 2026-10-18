from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.campaigns.repository import PostgresCampaignRepository
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings


@lru_cache
def build_campaign_service(database_url: str) -> CampaignService:
    return CampaignService(PostgresCampaignRepository(database_url))


def get_campaign_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> CampaignService:
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "database_unavailable", "message": "База данных не настроена"},
        )
    return build_campaign_service(settings.database_url)
