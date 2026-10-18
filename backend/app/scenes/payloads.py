from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class CreateScene(Payload):
    name: str = Field(min_length=1, max_length=120)


class ActivateScene(Payload):
    scene_id: UUID


class RenameScene(ActivateScene):
    name: str = Field(min_length=1, max_length=120)


class GridChange(Payload):
    grid_size: int | None = Field(default=None, ge=8, le=512)
    grid_enabled: bool | None = None
    snap_enabled: bool | None = None
    unit_size: float | None = Field(default=None, gt=0, le=10000)
    unit_label: str | None = Field(default=None, min_length=1, max_length=24)


class CreateItem(Payload):
    kind: Literal["map", "token"] = "token"
    name: str = Field(default="Токен", max_length=160)
    asset_id: UUID | None = None
    card_id: UUID | None = None
    x: float = Field(default=0, ge=-1000000, le=1000000)
    y: float = Field(default=0, ge=-1000000, le=1000000)
    width: float = Field(default=64, ge=0.01, le=1000000)
    height: float = Field(default=64, ge=0.01, le=1000000)
    rotation: float = Field(default=0, ge=-360000, le=360000)
    z_index: int = Field(default=0, ge=-1000000, le=1000000)
    visibility: Literal["everyone", "gm_only", "owner_only"] = "everyone"
    is_locked: bool = False
    owner_participant_id: UUID | None = None


class DuplicateItem(Payload):
    item_id: UUID


class UpdateItem(DuplicateItem):
    name: str | None = Field(default=None, max_length=160)
    asset_id: UUID | None = None
    card_id: UUID | None = None
    x: float | None = Field(default=None, ge=-1000000, le=1000000)
    y: float | None = Field(default=None, ge=-1000000, le=1000000)
    width: float | None = Field(default=None, ge=0.01, le=1000000)
    height: float | None = Field(default=None, ge=0.01, le=1000000)
    rotation: float | None = Field(default=None, ge=-360000, le=360000)
    z_index: int | None = Field(default=None, ge=-1000000, le=1000000)
    visibility: Literal["everyone", "gm_only", "owner_only"] | None = None
    is_locked: bool | None = None
    owner_participant_id: UUID | None = None


PAYLOAD_TYPES: dict[str, type[BaseModel]] = {
    "scene.create": CreateScene,
    "scene.rename": RenameScene,
    "scene.activate": ActivateScene,
    "scene.grid": GridChange,
    "item.create": CreateItem,
    "item.duplicate": DuplicateItem,
    "item.update": UpdateItem,
    "item.delete": DuplicateItem,
}
