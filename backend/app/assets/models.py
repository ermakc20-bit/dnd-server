from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_ASSET_BYTES = 52428800
ImageMime = Literal["image/jpeg", "image/png", "image/webp", "image/avif"]


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    content_type: ImageMime
    byte_size: int = Field(gt=0, le=MAX_ASSET_BYTES)
    kind: Literal["map", "character", "prop", "image"] = "map"


class AssetMetadata(BaseModel):
    id: UUID
    name: str
    content_type: str
    byte_size: int
    width: int | None = None
    height: int | None = None
    status: Literal["pending", "ready"]
    upload_url: str


class DownloadGrant(BaseModel):
    url: str
    expires_in: int = 60
