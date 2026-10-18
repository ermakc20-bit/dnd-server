from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.identity.models import Participant, ParticipantRole

__all__ = ["Campaign", "Participant", "ParticipantRole", "Room"]


class Room(BaseModel):
    id: UUID
    campaign_id: UUID
    name: str
    is_locked: bool
    pin_enabled: bool
    created_at: datetime
    can_manage: bool = False


class Campaign(BaseModel):
    id: UUID
    owner_user_id: UUID
    name: str
    system_id: str
    status: Literal["draft", "active", "archived"]
    created_at: datetime
    rooms: list[Room] = Field(default_factory=list)


class CreateCampaignRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    system_id: str = Field(default="neutral", pattern=r"^[a-z][a-z0-9_-]{1,31}$")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name cannot be blank")
        return cleaned


class RoomAccessRequest(BaseModel):
    is_locked: bool | None = None
    pin: str | None = Field(default=None, min_length=4, max_length=12, pattern=r"^[0-9]+$")
    remove_pin: bool = False


class IssueInviteRequest(BaseModel):
    expires_in_minutes: int = Field(default=1440, ge=5, le=10080)


class InviteResponse(BaseModel):
    room_id: UUID
    token: str
    expires_at: datetime


class GuestJoinRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    pin: str | None = Field(default=None, max_length=12)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name cannot be blank")
        return cleaned


class GuestJoinResponse(BaseModel):
    participant: Participant
    room: Room


class ParticipantListResponse(BaseModel):
    participants: list[Participant]


class AssignedToken(BaseModel):
    id: UUID
    name: str
    scene_id: UUID
    scene_name: str


class ParticipantStatus(BaseModel):
    id: UUID
    display_name: str
    role: ParticipantRole
    connection_status: Literal["connected", "disconnected", "unknown"] = "unknown"
    assigned_tokens: list[AssignedToken] = Field(default_factory=list)


class ParticipantStatusResponse(BaseModel):
    participants: list[ParticipantStatus]


class RoomSecurityEvent(BaseModel):
    id: int
    participant_id: UUID
    display_name: str
    type: Literal["participant.joined", "connection.opened", "connection.closed"]
    occurred_at: datetime
    reason: Literal[
        "guest_join",
        "registered_join",
        "authorized_socket",
        "socket_closed_actor_connected",
        "socket_closed_actor_disconnected",
        "socket_closed_actor_unknown",
    ]


class RoomSecurityPage(BaseModel):
    events: list[RoomSecurityEvent]
    next_before_id: int | None = None
