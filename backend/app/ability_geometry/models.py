from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.scene_tools.models import Point


class Value(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class WorldPoint(Value):
    # Derived token centers may exceed the public input Point limit.
    x: float
    y: float


class PresentedGeometry(Value):
    schema_version: Literal[1] = 1
    shape: Literal["circle", "radius", "cone", "line", "cube"]
    origin: WorldPoint
    rotation: float = 0
    radius: float = 0
    length: float = 0
    width: float = 0
    angle: float = 360
    color: str = Field(default="#c5a65c", pattern=r"^#[0-9a-fA-F]{6}$")


class PresentAbility(Value):
    card_id: UUID
    ability_id: UUID
    origin_item_id: UUID | None = None
    origin: Point | None = None
    direction: Point | None = None


class ClearAbility(Value):
    presentation_id: UUID


class AbilityPresentation(Value):
    id: UUID
    geometry: PresentedGeometry
    created_at: datetime
    can_clear: bool
    affected_item_ids: list[UUID]
