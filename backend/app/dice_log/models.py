from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=3, max_length=40)
    visibility: Literal["everyone", "gm_only"] = "everyone"


class RollEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    expression: str
    results: tuple[int, ...]
    modifier: int
    total: int
    visibility: Literal["everyone", "gm_only"]
    created_at: datetime


class JournalEntry(BaseModel):
    cursor: int
    aggregate_version: int
    actor_name: str
    occurred_at: datetime
    action: str
    type: str
    result: Literal["accepted"]
    visibility: Literal["everyone", "gm_only", "owner_only"]
    roll: RollEvent | None
    can_undo: bool
    revoked: bool = False


class JournalPage(BaseModel):
    entries: list[JournalEntry]
    next_cursor: int | None
