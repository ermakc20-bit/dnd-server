from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Visibility = Literal["everyone", "gm_only", "owner_only"]
Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Text = Annotated[str, Field(max_length=10000)]


class ValueModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class CardField(ValueModel):
    key: Key
    label: str = Field(min_length=1, max_length=120)
    value: str | float | bool | None = None
    value_type: Literal["text", "number", "boolean"] = "text"
    visibility: Visibility = "everyone"
    order: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def valid_value(self) -> Self:
        types: dict[str, type | tuple[type, ...]] = {
            "text": str,
            "number": (int, float),
            "boolean": bool,
        }
        expected = types[self.value_type]
        if self.value is not None and (
            not isinstance(self.value, expected)
            or (self.value_type == "number" and isinstance(self.value, bool))
        ):
            raise ValueError("Тип значения не соответствует полю")
        if isinstance(self.value, str) and len(self.value) > 10000:
            raise ValueError("Поле слишком длинное")
        return self


class Resource(ValueModel):
    key: Key
    label: str = Field(min_length=1, max_length=120)
    current: float = Field(ge=0, le=1000000000)
    max: float | None = Field(default=None, ge=0, le=1000000000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    visibility: Visibility = "everyone"

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.max is not None and self.current > self.max:
            raise ValueError("Текущее значение превышает максимум")
        return self


class Skill(ValueModel):
    key: Key
    name: str = Field(min_length=1, max_length=120)
    bonus: float | None = Field(default=None, ge=-1000000, le=1000000)
    proficient: bool = False
    description: Text | None = None
    visibility: Visibility = "everyone"


class InventoryItem(ValueModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=160)
    quantity: float | None = Field(default=None, ge=0, le=1000000)
    description: Text | None = None
    icon: str | None = Field(default=None, max_length=120)
    visibility: Visibility = "everyone"


class Geometry(ValueModel):
    shape: Literal["circle", "cone", "line", "cube", "radius"]
    origin: Literal["token", "point"] = "token"
    range: float | None = Field(default=None, ge=0, le=1000000)
    radius: float | None = Field(default=None, ge=0, le=1000000)
    length: float | None = Field(default=None, ge=0, le=1000000)
    width: float | None = Field(default=None, ge=0, le=1000000)
    angle: float | None = Field(default=None, gt=0, le=360)
    units: str = Field(default="фут", min_length=1, max_length=24)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class Ability(ValueModel):
    id: UUID = Field(default_factory=uuid4)
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=160)
    description: Text = ""
    action_type: str | None = Field(default=None, max_length=120)
    uses: Resource | None = None
    geometry: Geometry | None = None
    automation: None = None
    visibility: Visibility = "everyone"


class CardData(ValueModel):
    schema_version: Literal[1] = 1
    system_id: str = Field(default="neutral", max_length=64)
    system_version: int = Field(default=1, ge=1)
    kind: Literal["player_character", "npc", "mob", "object"] = "player_character"
    name: str = Field(min_length=1, max_length=160)
    subtitle: str | None = Field(default=None, max_length=240)
    external_key: str | None = Field(default=None, max_length=160)
    image_asset_id: UUID | None = None
    owner_participant_id: UUID | None = None
    visibility: Visibility = "everyone"
    allow_player_export: bool = False
    fields: list[CardField] = Field(default_factory=list, max_length=200)
    resources: list[Resource] = Field(default_factory=list, max_length=100)
    skills: list[Skill] = Field(default_factory=list, max_length=200)
    inventory: list[InventoryItem] = Field(default_factory=list, max_length=500)
    abilities: list[Ability] = Field(default_factory=list, max_length=200)
    notes: Text | None = None
    notes_visibility: Visibility = "gm_only"

    @model_validator(mode="before")
    @classmethod
    def private_npc_default(cls, value: Any) -> Any:
        if (
            isinstance(value, dict)
            and "visibility" not in value
            and value.get("kind") in {"npc", "mob"}
        ):
            return {**value, "visibility": "gm_only"}
        return value

    @model_validator(mode="after")
    def unique_keys(self) -> Self:
        for entries in (self.fields, self.resources, self.skills):
            if len({entry.key for entry in entries}) != len(entries):
                raise ValueError("Ключи должны быть уникальными")
        for entries_by_id in (self.inventory, self.abilities):
            if len({entry.id for entry in entries_by_id}) != len(entries_by_id):
                raise ValueError("Идентификаторы должны быть уникальными")
        return self


class Card(CardData):
    id: UUID
    campaign_id: UUID
    room_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class CardView(Card):
    can_edit_structure: bool = False
    can_edit_current: bool = False
    can_export: bool = False


class CardPage(BaseModel):
    cards: list[CardView]
    offset: int
    limit: int
    has_more: bool


class CreateCard(ValueModel):
    card: CardData


class UpdateCard(CreateCard):
    card_id: UUID


class CloneCard(ValueModel):
    card_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=160)


class ChangeResource(ValueModel):
    card_id: UUID
    resource_key: Key
    current: float = Field(ge=0, le=1000000000)


class DeleteCard(ValueModel):
    card_id: UUID
