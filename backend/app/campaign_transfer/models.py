from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

MAX_ZIP = 256 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_JSON = 32 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_ENTITIES = 10000
MAX_HISTORY = 1000
TERMINAL = {"completed", "failed", "cancelled", "expired", "cleanup_pending"}


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: UUID
    include_history: bool = False
    include_snapshot: bool = False


class TransferJob(BaseModel):
    id: UUID
    kind: Literal["import", "export"]
    phase: str
    progress: int
    cancel_requested: bool
    result_campaign_id: UUID | None
    error_code: str | None
    expires_at: datetime
    archive_available: bool = False


class TransferFailure(Exception):  # noqa: N818 - stable domain boundary
    def __init__(self, code: str, message: str = "Архив не прошёл проверку", status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)
