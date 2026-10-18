from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.dependencies import bearer_scheme, get_verifier
from app.auth.jwt import AuthenticationError
from app.campaigns.dependencies import get_campaign_service
from app.campaigns.errors import CampaignError
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings
from app.identity.models import Participant

GUEST_COOKIE = "vtt_guest_session"


async def resolve_room_actor(
    room_id: UUID,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    guest_token: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
) -> Participant:
    user_id = None
    expires_at = None
    if credentials is not None:
        try:
            identity = get_verifier(settings).verify(credentials.credentials)
            user_id, expires_at = identity.user_id, identity.expires_at
        except AuthenticationError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_credentials", "message": "Сессия недействительна"},
            ) from error
    try:
        actor = await service.resolve_actor(
            room_id, registered_user_id=user_id, guest_token=guest_token
        )
        return actor.model_copy(update={"authorization_expires_at": expires_at})
    except CampaignError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": "Нет доступа к этой комнате"},
        ) from error
