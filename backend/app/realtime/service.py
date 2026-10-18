import hashlib
import json
import secrets
from datetime import datetime
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.identity.models import Participant


class TicketRateLimitError(Exception):
    pass


class Realtime:
    def __init__(self, url: str | None):
        self.redis: Redis | None = (
            Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=2,
            )
            if url
            else None
        )

    async def close(self) -> None:
        if self.redis:
            await self.redis.aclose()

    async def connected_actors(self, room_id: UUID) -> set[str] | None:
        if self.redis is None:
            return None
        try:
            keys = [key async for key in self.redis.scan_iter(f"vtt:presence:{room_id}:*")]
            values = await self.redis.mget(keys) if keys else []
            return {str(value) for value in values if value is not None}
        except RedisError:
            return None

    async def notify(self, room_id: UUID) -> None:
        if self.redis:
            try:
                await self.redis.publish(f"vtt:room:{room_id}", '{"type":"changed"}')
            except RedisError:
                # Postgres has committed; resync recovers a lost wakeup.
                pass

    @staticmethod
    def ticket_key(ticket: str) -> str:
        return "vtt:ticket:" + hashlib.sha256(ticket.encode()).hexdigest()

    async def issue(self, actor: Participant) -> str:
        if self.redis is None:
            raise RedisError("unavailable")
        key = f"vtt:rate:{actor.id}:tickets"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 30)
        if count > 20:
            raise TicketRateLimitError
        ticket = secrets.token_urlsafe(32)
        saved = {
            "actor": actor.model_dump(mode="json"),
            "authorization_expires_at": actor.authorization_expires_at.isoformat()
            if actor.authorization_expires_at
            else None,
        }
        await self.redis.set(self.ticket_key(ticket), json.dumps(saved), ex=30)
        return ticket

    async def consume(self, ticket: str, room_id: UUID) -> Participant | None:
        if self.redis is None:
            return None
        saved = await self.redis.getdel(self.ticket_key(ticket))
        if not saved:
            return None
        record = json.loads(saved)
        actor = Participant.model_validate(record["actor"])
        expires_at = record.get("authorization_expires_at")
        actor.authorization_expires_at = datetime.fromisoformat(expires_at) if expires_at else None
        return actor if actor.room_id == room_id and not actor.authorization_expired else None
