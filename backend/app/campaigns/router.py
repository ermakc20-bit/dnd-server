from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.dependencies import bearer_scheme, get_current_identity, get_verifier
from app.auth.jwt import AuthenticationError, AuthIdentity
from app.campaigns.dependencies import get_campaign_service
from app.campaigns.errors import CampaignError
from app.campaigns.models import (
    Campaign,
    CreateCampaignRequest,
    GuestJoinRequest,
    GuestJoinResponse,
    InviteResponse,
    IssueInviteRequest,
    ParticipantListResponse,
    ParticipantStatusResponse,
    Room,
    RoomAccessRequest,
    RoomSecurityPage,
)
from app.campaigns.service import CampaignService
from app.config import Settings, get_settings
from app.identity.dependencies import GUEST_COOKIE, resolve_room_actor
from app.identity.models import Participant

router = APIRouter(prefix="/api/v1", tags=["campaigns"])


@router.get("/rooms/{room_id}/participants/status", response_model=ParticipantStatusResponse)
async def participant_status(
    room_id: UUID,
    request: Request,
    response: Response,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> ParticipantStatusResponse:
    try:
        participants = await service.participant_status(actor, room_id)
    except CampaignError as error:
        _raise_http(error)
    connected = await request.app.state.realtime.connected_actors(room_id)
    for participant in participants:
        participant.connection_status = (
            "unknown"
            if connected is None
            else ("connected" if str(participant.id) in connected else "disconnected")
        )
    try:
        await service.require_current_manager(actor, room_id)
    except CampaignError as error:
        _raise_http(error)
    response.headers["Cache-Control"] = "no-store"
    return ParticipantStatusResponse(participants=participants)


@router.get("/rooms/{room_id}/security-events", response_model=RoomSecurityPage)
async def security_events(
    room_id: UUID,
    response: Response,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before_id: Annotated[int | None, Query(ge=1)] = None,
) -> RoomSecurityPage:
    try:
        page = await service.security_events(actor, room_id, limit=limit, before_id=before_id)
        await service.require_current_manager(actor, room_id)
    except CampaignError as error:
        _raise_http(error)
    response.headers["Cache-Control"] = "no-store"
    return page


def _raise_http(error: CampaignError) -> NoReturn:
    messages = {
        "forbidden": "Недостаточно прав",
        "not_found": "Объект не найден",
        "invalid_invite": "Приглашение недействительно или истекло",
        "room_locked": "Комната закрыта мастером",
        "invalid_pin": "Неверный PIN",
        "rate_limited": "Слишком много попыток. Повторите вход через 15 минут",
        "invalid_guest_session": "Гостевая сессия недействительна или истекла",
    }
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": messages.get(error.code, "Операция не выполнена")},
    ) from error


@router.post("/campaigns", response_model=Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    request: CreateCampaignRequest,
    actor: Annotated[AuthIdentity, Depends(get_current_identity)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> Campaign:
    return await service.create_campaign(actor, request.name, request.system_id)


@router.get("/campaigns", response_model=list[Campaign])
async def list_campaigns(
    actor: Annotated[AuthIdentity, Depends(get_current_identity)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> list[Campaign]:
    return await service.list_campaigns(actor)


@router.post("/rooms/{room_id}/invites", response_model=InviteResponse)
async def issue_invite(
    room_id: UUID,
    request: IssueInviteRequest,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> InviteResponse:
    try:
        return await service.issue_invite(actor, room_id, request.expires_in_minutes)
    except CampaignError as error:
        _raise_http(error)


@router.delete("/rooms/{room_id}/invites", status_code=204)
async def revoke_invites(
    room_id: UUID,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> Response:
    try:
        await service.revoke_invites(actor, room_id)
    except CampaignError as error:
        _raise_http(error)
    return Response(status_code=204)


@router.post("/rooms/{room_id}/invites/rotate", response_model=InviteResponse)
async def rotate_invite(
    room_id: UUID,
    request: IssueInviteRequest,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> InviteResponse:
    try:
        return await service.rotate_invite(actor, room_id, request.expires_in_minutes)
    except CampaignError as error:
        _raise_http(error)


@router.patch("/rooms/{room_id}/access", response_model=Room)
async def update_room_access(
    room_id: UUID,
    request: RoomAccessRequest,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> Room:
    try:
        return await service.set_room_access(
            actor, room_id, request.is_locked, request.pin, request.remove_pin
        )
    except CampaignError as error:
        _raise_http(error)


@router.post("/join/{invite_token}", response_model=GuestJoinResponse)
async def join_guest(
    invite_token: str,
    request: GuestJoinRequest,
    response: Response,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GuestJoinResponse:
    try:
        participant, room, session_token = await service.join_guest(
            invite_token, request.display_name, request.pin
        )
    except CampaignError as error:
        _raise_http(error)
    response.set_cookie(
        GUEST_COOKIE,
        session_token,
        max_age=12 * 60 * 60,
        httponly=True,
        secure=settings.environment not in {"local", "test"},
        samesite="lax",
        path="/api/v1",
    )
    return GuestJoinResponse(participant=participant, room=room)


@router.post("/join/{invite_token}/registered", response_model=GuestJoinResponse)
async def join_registered(
    invite_token: str,
    request: GuestJoinRequest,
    actor: Annotated[AuthIdentity, Depends(get_current_identity)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> GuestJoinResponse:
    try:
        participant, room = await service.join_registered(
            actor, invite_token, request.display_name, request.pin
        )
    except CampaignError as error:
        _raise_http(error)
    return GuestJoinResponse(participant=participant, room=room)


@router.get("/join/{invite_token}/session", response_model=GuestJoinResponse)
async def restore_join_session(
    invite_token: str,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
) -> GuestJoinResponse:
    user_id = None
    if credentials is None and guest_session is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Сессия отсутствует"},
        )
    if credentials is not None:
        try:
            user_id = get_verifier(settings).verify(credentials.credentials).user_id
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail={"code": "invalid_credentials"}) from error
    try:
        participant, room = await service.resolve_invite_actor(
            invite_token, registered_user_id=user_id, guest_token=guest_session
        )
    except CampaignError as error:
        _raise_http(error)
    return GuestJoinResponse(participant=participant, room=room)


@router.get("/rooms/{room_id}/participants", response_model=ParticipantListResponse)
async def list_participants(
    room_id: UUID,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> ParticipantListResponse:
    try:
        participants = await service.list_participants(actor, room_id)
    except CampaignError as error:
        _raise_http(error)
    return ParticipantListResponse(participants=participants)


@router.delete("/rooms/{room_id}/participants/{participant_id}", status_code=204)
async def remove_participant(
    room_id: UUID,
    participant_id: UUID,
    request: Request,
    actor: Annotated[Participant, Depends(resolve_room_actor)],
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> Response:
    try:
        await service.remove_participant(actor, room_id, participant_id)
    except CampaignError as error:
        _raise_http(error)
    realtime = getattr(request.app.state, "realtime", None)
    if realtime is not None:
        await realtime.notify(room_id)
    return Response(status_code=204)
