from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.identity.models import Participant


async def participant_is_active(connection: AsyncConnection, actor: Participant) -> bool:
    """Recheck membership and guest expiry inside the authority transaction."""
    row = (
        await connection.execute(
            text("""
        select p.id from app.participants p
        where p.id=:actor and p.room_id=:room and p.campaign_id=:campaign
          and p.removed_at is null and p.role::text=:role
          and p.user_id is not distinct from :user
          and (p.identity_kind='registered' or exists (
            select 1 from app.guest_sessions g where g.participant_id=p.id
              and g.id=:session and g.revoked_at is null and g.expires_at > now()
          )) for share of p
    """),
            {
                "actor": actor.id,
                "room": actor.room_id,
                "campaign": actor.campaign_id,
                "role": actor.role.value,
                "user": actor.user_id,
                "session": actor.guest_session_id,
            },
        )
    ).first()
    return row is not None
