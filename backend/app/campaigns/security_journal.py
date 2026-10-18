"""Private append-only room audit; intentionally independent of gameplay history."""

from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.campaigns.errors import ForbiddenError

SecurityEventType = Literal["participant.joined", "connection.opened", "connection.closed"]
SecurityEventReason = Literal[
    "guest_join",
    "registered_join",
    "authorized_socket",
    "socket_closed_actor_connected",
    "socket_closed_actor_disconnected",
    "socket_closed_actor_unknown",
]


async def append_security_event(
    connection: AsyncConnection,
    room_id: UUID,
    participant_id: UUID,
    event_type: SecurityEventType,
    reason: SecurityEventReason,
) -> None:
    event_id = await connection.scalar(
        text("""
        insert into app.room_security_events(room_id,participant_id,display_name,type,reason)
        select :room,p.id,p.display_name,:type,:reason from app.participants p
        where p.id=:participant and p.room_id=:room
        returning id
    """),
        {"room": room_id, "participant": participant_id, "type": event_type, "reason": reason},
    )
    if event_id is None:
        raise ForbiddenError
