from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.access.policy import Action, authorize
from app.campaigns.errors import (
    ForbiddenError,
    GuestSessionError,
    InvalidInviteError,
    InvalidPinError,
    RateLimitedError,
    ResourceNotFoundError,
    RoomLockedError,
)
from app.campaigns.models import (
    AssignedToken,
    Campaign,
    ParticipantStatus,
    Room,
    RoomSecurityEvent,
    RoomSecurityPage,
)
from app.campaigns.security_journal import (
    SecurityEventReason,
    SecurityEventType,
    append_security_event,
)
from app.identity.crypto import hash_pin, verify_pin
from app.identity.models import Participant, ParticipantRole


class CampaignRepository(Protocol):
    async def participant_status(self, room_id: UUID) -> list[ParticipantStatus]: ...

    async def security_events(
        self, room_id: UUID, limit: int, before_id: int | None
    ) -> RoomSecurityPage: ...

    async def connection_event(
        self, actor: Participant, event_type: SecurityEventType, reason: SecurityEventReason
    ) -> None: ...
    async def create_campaign(self, owner_user_id: UUID, name: str, system_id: str) -> Campaign: ...

    async def list_campaigns(self, user_id: UUID) -> list[Campaign]: ...

    async def issue_invite(
        self,
        room_id: UUID,
        actor_user_id: UUID,
        token_hash_value: str,
        expires_at: datetime,
    ) -> None: ...

    async def rotate_invite(
        self,
        room_id: UUID,
        actor_user_id: UUID,
        token_hash_value: str,
        expires_at: datetime,
    ) -> None: ...

    async def revoke_active_invites(self, room_id: UUID, actor_user_id: UUID) -> None: ...

    async def set_room_access(
        self,
        room_id: UUID,
        actor_user_id: UUID,
        is_locked: bool | None,
        pin: str | None,
        remove_pin: bool,
    ) -> Room: ...

    async def join_guest(
        self,
        invite_hash: str,
        session_hash: str,
        session_id: UUID,
        display_name: str,
        pin: str | None,
        session_expires_at: datetime,
    ) -> tuple[Participant, Room]: ...

    async def restore_guest(
        self, session_hash: str, expected_room_id: UUID
    ) -> tuple[Participant, Room]: ...

    async def resolve_registered(self, user_id: UUID, room_id: UUID) -> Participant: ...

    async def room_id_for_invite(self, invite_hash: str) -> UUID: ...

    async def get_room(self, room_id: UUID) -> Room: ...

    async def join_registered(
        self, invite_hash: str, user_id: UUID, display_name: str, pin: str | None
    ) -> tuple[Participant, Room]: ...

    async def list_participants(self, room_id: UUID, actor_user_id: UUID) -> list[Participant]: ...

    async def remove_participant(
        self, room_id: UUID, participant_id: UUID, actor: Participant
    ) -> None: ...


def _async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


class PostgresCampaignRepository:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            _async_database_url(database_url), pool_pre_ping=True
        )

    async def participant_status(self, room_id: UUID) -> list[ParticipantStatus]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text("""
                select p.id,p.display_name,p.role::text as role,
                       i.id as token_id,i.name as token_name,
                       s.id as scene_id,s.name as scene_name
                from app.participants p
                left join app.scene_items i on i.owner_participant_id=p.id
                  and i.kind='token' and i.deleted_at is null
                  and exists(select 1 from app.scenes active where active.id=i.scene_id
                    and active.deleted_at is null)
                  and (i.card_id is null or exists(select 1 from app.cards c
                    where c.id=i.card_id and c.deleted_at is null))
                left join app.scenes s on s.id=i.scene_id and s.deleted_at is null
                where p.room_id=:room and p.removed_at is null
                order by p.joined_at,p.id,s.created_at,s.id,i.z_index,i.id
            """),
                        {"room": room_id},
                    )
                )
                .mappings()
                .all()
            )
        participants: dict[UUID, ParticipantStatus] = {}
        for row in rows:
            participant = participants.setdefault(
                row["id"],
                ParticipantStatus(id=row["id"], display_name=row["display_name"], role=row["role"]),
            )
            if row["token_id"] is not None:
                participant.assigned_tokens.append(
                    AssignedToken(
                        id=row["token_id"],
                        name=row["token_name"],
                        scene_id=row["scene_id"],
                        scene_name=row["scene_name"],
                    )
                )
        return list(participants.values())

    async def security_events(
        self, room_id: UUID, limit: int, before_id: int | None
    ) -> RoomSecurityPage:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text("""
                select id,participant_id,display_name,type,occurred_at,reason
                from app.room_security_events where room_id=:room
                  and (cast(:before as bigint) is null or id<:before)
                order by id desc limit :limit
            """),
                        {"room": room_id, "before": before_id, "limit": limit + 1},
                    )
                )
                .mappings()
                .all()
            )
        events = [RoomSecurityEvent.model_validate(row) for row in rows[:limit]]
        return RoomSecurityPage(
            events=events, next_before_id=events[-1].id if len(rows) > limit else None
        )

    async def connection_event(
        self, actor: Participant, event_type: SecurityEventType, reason: SecurityEventReason
    ) -> None:
        async with self._engine.begin() as connection:
            await append_security_event(connection, actor.room_id, actor.id, event_type, reason)

    async def create_campaign(self, owner_user_id: UUID, name: str, system_id: str) -> Campaign:
        campaign_id = uuid4()
        room_id = uuid4()
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into app.campaigns
                      (id, owner_user_id, name, system_id, status, created_at, updated_at)
                    values (:id, :owner, :name, :system, 'draft', :now, :now)
                    """
                ),
                {
                    "id": campaign_id,
                    "owner": owner_user_id,
                    "name": name,
                    "system": system_id,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into app.rooms
                      (id, campaign_id, owner_user_id, name, game_system, created_at, updated_at)
                    values (:id, :campaign, :owner, :name, :system, :now, :now)
                    """
                ),
                {
                    "id": room_id,
                    "campaign": campaign_id,
                    "owner": owner_user_id,
                    "name": "Основной стол",
                    "system": system_id,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """
                    insert into app.participants
                      (campaign_id, room_id, user_id, role, display_name, joined_at)
                    select :campaign, :room, p.user_id, 'gm', p.display_name, :now
                    from app.profiles p
                    where p.user_id = :user_id
                    """
                ),
                {
                    "campaign": campaign_id,
                    "room": room_id,
                    "user_id": owner_user_id,
                    "now": now,
                },
            )
        room = Room(
            id=room_id,
            campaign_id=campaign_id,
            name="Основной стол",
            is_locked=False,
            pin_enabled=False,
            created_at=now,
        )
        return Campaign(
            id=campaign_id,
            owner_user_id=owner_user_id,
            name=name,
            system_id=system_id,
            status="draft",
            created_at=now,
            rooms=[room],
        )

    async def list_campaigns(self, user_id: UUID) -> list[Campaign]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                        select c.id, c.owner_user_id, c.name, c.system_id, c.status,
                               c.created_at, r.id as room_id, r.name as room_name,
                               r.is_locked, r.pin_hash is not null as pin_enabled,
                               r.created_at as room_created_at
                        from app.campaigns c
                        left join app.rooms r on r.campaign_id = c.id and not r.is_archived
                          and (
                            c.owner_user_id = :user_id
                            or exists (
                              select 1 from app.participants rp
                              where rp.room_id = r.id and rp.user_id = :user_id
                                and rp.removed_at is null
                            )
                          )
                        where exists (
                          select 1 from app.participants p
                          where p.campaign_id = c.id and p.user_id = :user_id
                            and p.removed_at is null
                        )
                        order by c.created_at, r.created_at
                        """
                        ),
                        {"user_id": user_id},
                    )
                )
                .mappings()
                .all()
            )
        campaigns: dict[UUID, Campaign] = {}
        for row in rows:
            campaign_id = row["id"]
            campaign = campaigns.get(campaign_id)
            if campaign is None:
                campaign = Campaign(
                    id=campaign_id,
                    owner_user_id=row["owner_user_id"],
                    name=row["name"],
                    system_id=row["system_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                    rooms=[],
                )
                campaigns[campaign_id] = campaign
            if row["room_id"] is not None:
                campaign.rooms.append(
                    Room(
                        id=row["room_id"],
                        campaign_id=campaign_id,
                        name=row["room_name"],
                        is_locked=row["is_locked"],
                        pin_enabled=row["pin_enabled"],
                        created_at=row["room_created_at"],
                    )
                )
        return list(campaigns.values())

    async def issue_invite(
        self,
        room_id: UUID,
        actor_user_id: UUID,
        token_hash_value: str,
        expires_at: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into app.room_join_tokens
                      (room_id, token_hash, created_by, expires_at)
                    values (:room, :token_hash, :actor, :expires_at)
                    """
                ),
                {
                    "room": room_id,
                    "token_hash": token_hash_value,
                    "actor": actor_user_id,
                    "expires_at": expires_at,
                },
            )

    async def revoke_active_invites(self, room_id: UUID, actor_user_id: UUID) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    update app.room_join_tokens set revoked_at = now()
                    where room_id = :room and revoked_at is null
                    """
                ),
                {"room": room_id},
            )

    async def rotate_invite(
        self,
        room_id: UUID,
        actor_user_id: UUID,
        token_hash_value: str,
        expires_at: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    update app.room_join_tokens set revoked_at = now()
                    where room_id = :room and revoked_at is null
                    """
                ),
                {"room": room_id},
            )
            await connection.execute(
                text(
                    """
                    insert into app.room_join_tokens
                      (room_id, token_hash, created_by, expires_at)
                    values (:room, :token_hash, :actor, :expires_at)
                    """
                ),
                {
                    "room": room_id,
                    "token_hash": token_hash_value,
                    "actor": actor_user_id,
                    "expires_at": expires_at,
                },
            )

    async def set_room_access(
        self,
        room_id: UUID,
        actor_user_id: UUID,
        is_locked: bool | None,
        pin: str | None,
        remove_pin: bool,
    ) -> Room:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    update app.rooms
                    set is_locked = coalesce(cast(:is_locked as boolean), is_locked),
                        pin_hash = case
                          when cast(:remove_pin as boolean) then null
                          when cast(:pin_hash as text) is not null then cast(:pin_hash as text)
                          else pin_hash
                        end,
                        updated_at = now()
                    where id = :room
                    """
                ),
                {
                    "room": room_id,
                    "is_locked": is_locked,
                    "remove_pin": remove_pin,
                    "pin_hash": hash_pin(pin) if pin is not None else None,
                },
            )
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        select id, campaign_id, name, is_locked,
                               pin_hash is not null as pin_enabled, created_at
                        from app.rooms where id = :room
                        """
                        ),
                        {"room": room_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ResourceNotFoundError
        return Room.model_validate(row)

    async def join_guest(
        self,
        invite_hash: str,
        session_hash: str,
        session_id: UUID,
        display_name: str,
        pin: str | None,
        session_expires_at: datetime,
    ) -> tuple[Participant, Room]:
        now = datetime.now(UTC)
        pending_error: Exception | None = None
        participant_id = uuid4()
        async with self._engine.begin() as connection:
            invite, pending_error = await self._check_invite(connection, invite_hash, pin, now)
            if pending_error is None:
                if invite is None:
                    raise InvalidInviteError
                await connection.execute(
                    text(
                        """
                        insert into app.participants
                          (id, campaign_id, room_id, identity_kind, role, display_name, joined_at)
                        values (:id, :campaign, :room, 'guest', 'player', :display_name, :now)
                        """
                    ),
                    {
                        "id": participant_id,
                        "campaign": invite["campaign_id"],
                        "room": invite["room_id"],
                        "display_name": display_name,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        """
                        insert into app.guest_sessions
                          (id, participant_id, token_hash, expires_at, created_at)
                        values (:id, :participant, :token_hash, :expires_at, :now)
                        """
                    ),
                    {
                        "id": session_id,
                        "participant": participant_id,
                        "token_hash": session_hash,
                        "expires_at": session_expires_at,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        """
                        update app.room_join_tokens set use_count = use_count + 1
                        where id = :id
                        """
                    ),
                    {"id": invite["id"]},
                )
                await append_security_event(
                    connection,
                    invite["room_id"],
                    participant_id,
                    "participant.joined",
                    "guest_join",
                )
        if pending_error is not None:
            raise pending_error
        if invite is None:
            raise InvalidInviteError
        participant = Participant(
            id=participant_id,
            campaign_id=invite["campaign_id"],
            room_id=invite["room_id"],
            role=ParticipantRole.PLAYER,
            display_name=display_name,
            guest_session_id=session_id,
            joined_at=now,
        )
        return participant, self._room_from_invite(invite)

    async def restore_guest(
        self, session_hash: str, expected_room_id: UUID
    ) -> tuple[Participant, Room]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        select p.id, p.campaign_id, p.room_id, p.role::text as role,
                               p.display_name, p.joined_at, p.removed_at,
                               s.id as guest_session_id, r.name as room_name,
                               r.is_locked, r.pin_hash is not null as pin_enabled,
                               r.created_at as room_created_at
                        from app.guest_sessions s
                        join app.participants p on p.id = s.participant_id
                        join app.rooms r on r.id = p.room_id
                        where s.token_hash = :token_hash and p.room_id = :room_id
                          and s.revoked_at is null
                          and s.expires_at > now() and p.removed_at is null
                        """
                        ),
                        {"token_hash": session_hash, "room_id": expected_room_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise GuestSessionError
        participant = Participant(
            id=row["id"],
            campaign_id=row["campaign_id"],
            room_id=row["room_id"],
            role=row["role"],
            display_name=row["display_name"],
            guest_session_id=row["guest_session_id"],
            joined_at=row["joined_at"],
            removed_at=row["removed_at"],
        )
        room = Room(
            id=row["room_id"],
            campaign_id=row["campaign_id"],
            name=row["room_name"],
            is_locked=row["is_locked"],
            pin_enabled=row["pin_enabled"],
            created_at=row["room_created_at"],
        )
        return participant, room

    async def resolve_registered(self, user_id: UUID, room_id: UUID) -> Participant:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        select id, campaign_id, room_id, user_id, role::text as role,
                               display_name, joined_at, removed_at
                        from app.participants
                        where user_id = :user_id and room_id = :room_id and removed_at is null
                        """
                        ),
                        {"user_id": user_id, "room_id": room_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ForbiddenError
        return Participant.model_validate(row)

    async def room_id_for_invite(self, invite_hash: str) -> UUID:
        async with self._engine.connect() as connection:
            room_id = await connection.scalar(
                text(
                    """
                    select room_id from app.room_join_tokens
                    where token_hash = :token_hash
                    """
                ),
                {"token_hash": invite_hash},
            )
        if room_id is None:
            raise InvalidInviteError
        return UUID(str(room_id))

    async def get_room(self, room_id: UUID) -> Room:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        select id, campaign_id, name, is_locked,
                               pin_hash is not null as pin_enabled, created_at
                        from app.rooms where id = :room_id
                        """
                        ),
                        {"room_id": room_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ResourceNotFoundError
        return Room.model_validate(row)

    async def join_registered(
        self, invite_hash: str, user_id: UUID, display_name: str, pin: str | None
    ) -> tuple[Participant, Room]:
        now = datetime.now(UTC)
        pending_error: Exception | None = None
        participant: Participant | None = None
        async with self._engine.begin() as connection:
            invite, pending_error = await self._check_invite(connection, invite_hash, pin, now)
            if pending_error is None:
                if invite is None:
                    raise InvalidInviteError
                row = (
                    (
                        await connection.execute(
                            text(
                                """
                            insert into app.participants
                              (id, campaign_id, room_id, user_id, identity_kind, role,
                               display_name, joined_at)
                            values (:id, :campaign, :room, :user_id, 'registered', 'player',
                                    :display_name, :now)
                            on conflict (room_id, user_id) where user_id is not null
                            do update set removed_at = null, display_name = excluded.display_name
                            returning id, campaign_id, room_id, user_id, role::text as role,
                                      display_name, joined_at, removed_at
                            """
                            ),
                            {
                                "id": uuid4(),
                                "campaign": invite["campaign_id"],
                                "room": invite["room_id"],
                                "user_id": user_id,
                                "display_name": display_name,
                                "now": now,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                participant = Participant.model_validate(row)
                await append_security_event(
                    connection,
                    invite["room_id"],
                    participant.id,
                    "participant.joined",
                    "registered_join",
                )
                await connection.execute(
                    text(
                        """
                        update app.room_join_tokens set use_count = use_count + 1
                        where id = :id
                        """
                    ),
                    {"id": invite["id"]},
                )
        if pending_error is not None:
            raise pending_error
        if invite is None:
            raise InvalidInviteError
        if participant is None:
            raise InvalidInviteError
        return participant, self._room_from_invite(invite)

    async def _check_invite(
        self, connection: Any, invite_hash: str, pin: str | None, now: datetime
    ) -> tuple[Any | None, Exception | None]:
        invite = (
            (
                await connection.execute(
                    text(
                        """
                    select t.id, t.room_id, t.expires_at, t.max_uses, t.use_count,
                           t.revoked_at, t.failed_pin_attempts, t.locked_until,
                           r.campaign_id, r.name, r.is_locked, r.pin_hash, r.created_at
                    from app.room_join_tokens t
                    join app.rooms r on r.id = t.room_id
                    where t.token_hash = :invite_hash
                    for update of t
                    """
                    ),
                    {"invite_hash": invite_hash},
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            invite is None
            or invite["revoked_at"] is not None
            or invite["expires_at"] <= now
            or (invite["max_uses"] is not None and invite["use_count"] >= invite["max_uses"])
        ):
            return invite, InvalidInviteError()
        if invite["is_locked"]:
            return invite, RoomLockedError()
        if invite["locked_until"] is not None and invite["locked_until"] > now:
            return invite, RateLimitedError()
        if invite["pin_hash"] is not None and (
            pin is None or not verify_pin(pin, invite["pin_hash"])
        ):
            attempts = min(invite["failed_pin_attempts"] + 1, 5)
            await connection.execute(
                text(
                    """
                    update app.room_join_tokens
                    set failed_pin_attempts = :attempts,
                        locked_until = case
                          when :attempts >= 5 then :locked_until else locked_until
                        end
                    where id = :id
                    """
                ),
                {
                    "attempts": attempts,
                    "locked_until": now.replace(microsecond=0) + timedelta(minutes=15),
                    "id": invite["id"],
                },
            )
            return invite, RateLimitedError() if attempts >= 5 else InvalidPinError()
        if invite["failed_pin_attempts"]:
            await connection.execute(
                text(
                    """
                    update app.room_join_tokens
                    set failed_pin_attempts = 0, locked_until = null where id = :id
                    """
                ),
                {"id": invite["id"]},
            )
        return invite, None

    @staticmethod
    def _room_from_invite(invite: Any) -> Room:
        return Room(
            id=invite["room_id"],
            campaign_id=invite["campaign_id"],
            name=invite["name"],
            is_locked=invite["is_locked"],
            pin_enabled=invite["pin_hash"] is not None,
            created_at=invite["created_at"],
        )

    async def list_participants(self, room_id: UUID, actor_user_id: UUID) -> list[Participant]:
        async with self._engine.connect() as connection:
            rows: Sequence[Any] = (
                (
                    await connection.execute(
                        text(
                            """
                        select p.id, p.campaign_id, p.room_id, p.user_id,
                               p.role::text as role, p.display_name, p.joined_at, p.removed_at,
                               s.id as guest_session_id
                        from app.participants p
                        left join app.guest_sessions s on s.participant_id = p.id
                          and s.revoked_at is null and s.expires_at > now()
                        where p.room_id = :room and p.removed_at is null
                        order by p.joined_at
                        """
                        ),
                        {"room": room_id},
                    )
                )
                .mappings()
                .all()
            )
        return [Participant.model_validate(row) for row in rows]

    async def remove_participant(
        self, room_id: UUID, participant_id: UUID, actor: Participant
    ) -> None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        update app.participants set removed_at = now()
                        where id = :participant and room_id = :room
                          and removed_at is null and role <> 'gm'::app.participant_role
                        returning id, campaign_id, room_id, user_id, role::text as role,
                                  display_name, joined_at, removed_at
                        """
                        ),
                        {"participant": participant_id, "room": room_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ForbiddenError
            target = Participant.model_validate(row)
            if not authorize(actor, Action.REMOVE_PARTICIPANT, room_id, target).allowed:
                raise ForbiddenError
            await connection.execute(
                text(
                    """
                    update app.guest_sessions set revoked_at = now()
                    where participant_id = :participant and revoked_at is null
                    """
                ),
                {"participant": participant_id},
            )
