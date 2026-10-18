from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class ParticipantRole(StrEnum):
    GM = "gm"
    PLAYER = "player"


class Participant(BaseModel):
    id: UUID
    campaign_id: UUID
    room_id: UUID
    role: ParticipantRole
    display_name: str
    user_id: UUID | None = None
    guest_session_id: UUID | None = None
    joined_at: datetime
    removed_at: datetime | None = None
    authorization_expires_at: datetime | None = Field(default=None, exclude=True)

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    @property
    def authorization_expired(self) -> bool:
        return not self.is_guest and (
            self.authorization_expires_at is None
            or self.authorization_expires_at <= datetime.now(UTC)
        )
