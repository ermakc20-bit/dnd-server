from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.campaigns.errors import GuestSessionError
from app.identity.crypto import hash_token
from app.identity.models import Participant


class ActorStore(Protocol):
    async def resolve_registered(self, user_id: UUID, room_id: UUID) -> Participant: ...

    async def restore_guest(
        self, session_hash: str, expected_room_id: UUID
    ) -> tuple[Participant, object]: ...


async def resolve_actor(
    store: ActorStore,
    room_id: UUID,
    *,
    registered_user_id: UUID | None = None,
    guest_token: str | None = None,
) -> Participant:
    """Resolve either credential to a persisted, room-scoped Participant."""
    if registered_user_id is not None:
        return await store.resolve_registered(registered_user_id, room_id)
    if guest_token is not None:
        participant, _room = await store.restore_guest(hash_token(guest_token), room_id)
        return participant
    raise GuestSessionError
