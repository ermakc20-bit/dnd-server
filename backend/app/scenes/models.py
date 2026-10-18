from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ability_geometry.models import AbilityPresentation
from app.scene_tools.models import Annotation, Fog


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    room_id: UUID
    actor_session_id: UUID
    expected_aggregate_version: int = Field(ge=0)
    type: str
    payload: dict[str, Any]
    client_sent_at: datetime


class CommandResult(BaseModel):
    command_id: UUID
    status: Literal["accepted", "rejected", "duplicate"]
    aggregate_version: int | None = None
    event_cursor: int | None = None
    error_code: str | None = None
    message: str | None = None


class SceneSummary(BaseModel):
    id: UUID
    name: str


class Scene(SceneSummary):
    width: int
    height: int
    grid_size: int
    grid_enabled: bool
    snap_enabled: bool
    unit_size: float
    unit_label: str


class SceneItem(BaseModel):
    id: UUID
    kind: Literal["map", "token"]
    name: str
    asset_id: UUID | None
    x: float
    y: float
    width: float
    height: float
    rotation: float
    z_index: int
    visibility: Literal["everyone", "gm_only", "owner_only"]
    is_locked: bool
    owner_participant_id: UUID | None
    card_id: UUID | None = None
    can_transform: bool = False


class SceneProjection(BaseModel):
    room_id: UUID
    aggregate_version: int
    event_cursor: int
    actor_session_id: UUID
    can_manage: bool
    scenes: list[SceneSummary]
    scene: Scene | None
    items: list[SceneItem]
    fog: Fog = Field(default_factory=Fog)
    annotations: list[Annotation] = Field(default_factory=list)
    ability_presentations: list[AbilityPresentation] = Field(default_factory=list)


class SceneFailure(Exception):  # noqa: N818 - stable domain failure contract
    def __init__(self, code: str, message: str, status_code: int = 403) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)
