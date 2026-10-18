from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.access.policy import Action, authorize
from app.auth.jwt import AuthIdentity
from app.campaigns.errors import ForbiddenError
from app.campaigns.models import Campaign, InviteResponse, ParticipantStatus, Room, RoomSecurityPage
from app.campaigns.repository import CampaignRepository
from app.campaigns.security_journal import SecurityEventReason, SecurityEventType
from app.identity.crypto import hash_token, issue_secret
from app.identity.models import Participant
from app.identity.resolver import resolve_actor

GUEST_SESSION_LIFETIME = timedelta(hours=12)


class CampaignService:
    def __init__(self, repository: CampaignRepository) -> None:
        self._repository = repository

    async def participant_status(
        self, actor: Participant, room_id: UUID
    ) -> list[ParticipantStatus]:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        return await self._repository.participant_status(room_id)

    async def require_current_manager(self, actor: Participant, room_id: UUID) -> None:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        if actor.authorization_expired:
            raise ForbiddenError
        current = await self._repository.resolve_registered(
            self._registered_user_id(actor), room_id
        )
        if actor.authorization_expired:
            raise ForbiddenError
        self._require(current, Action.MANAGE_ROOM, room_id)

    async def security_events(
        self, actor: Participant, room_id: UUID, *, limit: int, before_id: int | None
    ) -> RoomSecurityPage:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        return await self._repository.security_events(room_id, limit, before_id)

    async def connection_event(
        self, actor: Participant, event_type: SecurityEventType, reason: SecurityEventReason
    ) -> None:
        await self._repository.connection_event(actor, event_type, reason)

    async def create_campaign(self, actor: AuthIdentity, name: str, system_id: str) -> Campaign:
        campaign = await self._repository.create_campaign(actor.user_id, name, system_id)
        await self._project_room_capabilities(actor.user_id, [campaign])
        return campaign

    async def list_campaigns(self, actor: AuthIdentity) -> list[Campaign]:
        campaigns = await self._repository.list_campaigns(actor.user_id)
        await self._project_room_capabilities(actor.user_id, campaigns)
        return campaigns

    async def issue_invite(
        self, actor: Participant, room_id: UUID, expires_in_minutes: int
    ) -> InviteResponse:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        user_id = self._registered_user_id(actor)
        token = issue_secret()
        expires_at = datetime.now(UTC) + timedelta(minutes=expires_in_minutes)
        await self._repository.issue_invite(room_id, user_id, hash_token(token), expires_at)
        return InviteResponse(room_id=room_id, token=token, expires_at=expires_at)

    async def rotate_invite(
        self, actor: Participant, room_id: UUID, expires_in_minutes: int
    ) -> InviteResponse:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        user_id = self._registered_user_id(actor)
        token = issue_secret()
        expires_at = datetime.now(UTC) + timedelta(minutes=expires_in_minutes)
        await self._repository.rotate_invite(room_id, user_id, hash_token(token), expires_at)
        return InviteResponse(room_id=room_id, token=token, expires_at=expires_at)

    async def revoke_invites(self, actor: Participant, room_id: UUID) -> None:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        await self._repository.revoke_active_invites(room_id, self._registered_user_id(actor))

    async def set_room_access(
        self,
        actor: Participant,
        room_id: UUID,
        is_locked: bool | None,
        pin: str | None,
        remove_pin: bool,
    ) -> Room:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        user_id = self._registered_user_id(actor)
        room = await self._repository.set_room_access(room_id, user_id, is_locked, pin, remove_pin)
        room.can_manage = authorize(actor, Action.MANAGE_ROOM, room.id).allowed
        return room

    async def join_guest(
        self, invite_token: str, display_name: str, pin: str | None
    ) -> tuple[Participant, Room, str]:
        session_token = issue_secret()
        session_id = uuid4()
        participant, room = await self._repository.join_guest(
            hash_token(invite_token),
            hash_token(session_token),
            session_id,
            display_name,
            pin,
            datetime.now(UTC) + GUEST_SESSION_LIFETIME,
        )
        return participant, room, session_token

    async def join_registered(
        self, actor: AuthIdentity, invite_token: str, display_name: str, pin: str | None
    ) -> tuple[Participant, Room]:
        participant, room = await self._repository.join_registered(
            hash_token(invite_token), actor.user_id, display_name, pin
        )
        room.can_manage = authorize(participant, Action.MANAGE_ROOM, room.id).allowed
        return participant, room

    async def resolve_actor(
        self,
        room_id: UUID,
        *,
        registered_user_id: UUID | None = None,
        guest_token: str | None = None,
    ) -> Participant:
        return await resolve_actor(
            self._repository,
            room_id,
            registered_user_id=registered_user_id,
            guest_token=guest_token,
        )

    async def resolve_invite_actor(
        self,
        invite_token: str,
        *,
        registered_user_id: UUID | None = None,
        guest_token: str | None = None,
    ) -> tuple[Participant, Room]:
        room_id = await self._repository.room_id_for_invite(hash_token(invite_token))
        participant = await self.resolve_actor(
            room_id,
            registered_user_id=registered_user_id,
            guest_token=guest_token,
        )
        room = await self._repository.get_room(room_id)
        room.can_manage = authorize(participant, Action.MANAGE_ROOM, room.id).allowed
        return participant, room

    async def list_participants(self, actor: Participant, room_id: UUID) -> list[Participant]:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        return await self._repository.list_participants(room_id, self._registered_user_id(actor))

    async def remove_participant(
        self, actor: Participant, room_id: UUID, participant_id: UUID
    ) -> None:
        self._require(actor, Action.MANAGE_ROOM, room_id)
        await self._repository.remove_participant(room_id, participant_id, actor)

    async def _project_room_capabilities(self, user_id: UUID, campaigns: list[Campaign]) -> None:
        for campaign in campaigns:
            for room in campaign.rooms:
                room.can_manage = False
                try:
                    participant = await self._repository.resolve_registered(user_id, room.id)
                except ForbiddenError:
                    continue
                room.can_manage = authorize(participant, Action.MANAGE_ROOM, room.id).allowed

    @staticmethod
    def _require(
        actor: Participant,
        action: Action,
        resource_id: UUID,
        subject: Participant | None = None,
    ) -> None:
        if not authorize(actor, action, resource_id, subject).allowed:
            raise ForbiddenError

    @staticmethod
    def _registered_user_id(actor: Participant) -> UUID:
        if actor.user_id is None:
            raise ForbiddenError
        return actor.user_id
