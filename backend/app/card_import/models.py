from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from app.cards.models import CardData, ValueModel

MAX_BYTES = 5 * 1024 * 1024
MAX_EXPANDED = 20 * 1024 * 1024
MAX_DRAFTS = 100
MAX_INSTANCES = 200
PARSER_TIMEOUT = 8


class Location(ValueModel):
    section: str = Field(max_length=120)
    row: int = Field(ge=1)
    field: str = Field(max_length=160)


class Diagnostic(Location):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    entity: str | None = None


class SourceFragment(Location):
    # Source text is literal, including indentation and line endings.
    model_config = ConfigDict(str_strip_whitespace=False)
    external_key: str | None = Field(default=None, max_length=160)
    text: str = Field(min_length=1, max_length=MAX_EXPANDED)


class CardDraft(ValueModel):
    external_key: str = Field(min_length=1, max_length=160)
    card: CardData
    count: int = Field(default=1, ge=1, le=MAX_INSTANCES)
    included: bool = True
    create_token: bool = False
    source: dict[str, Location] = Field(default_factory=dict)


class DraftSet(ValueModel):
    schema_version: Literal[1] = 1
    drafts: list[CardDraft] = Field(min_length=1, max_length=MAX_DRAFTS)
    diagnostics: list[Diagnostic] = Field(default_factory=list, max_length=2000)
    fragments: list[SourceFragment] = Field(default_factory=list, max_length=2000)


class ImportJob(ValueModel):
    id: UUID
    status: Literal["draft", "confirmed", "cancelled", "expired"]
    version: int
    expires_at: datetime
    draftset: DraftSet
    card_ids: list[UUID] = Field(default_factory=list)


class EditJob(ValueModel):
    expected_version: int = Field(ge=1)
    drafts: list[CardDraft] = Field(min_length=1, max_length=MAX_DRAFTS)


class ConfirmImport(ValueModel):
    job_id: UUID
    expected_job_version: int = Field(ge=1)


class ParseFailure(Exception):  # noqa: N818 - matches the domain SceneFailure convention
    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__("Документ не прошёл проверку")


def fail(
    code: str,
    message: str,
    *,
    section: str = "Документ",
    row: int = 1,
    field: str = "файл",
    entity: str | None = None,
) -> ParseFailure:
    return ParseFailure(
        [
            Diagnostic(
                severity="error",
                code=code,
                message=message,
                section=section,
                row=row,
                field=field,
                entity=entity,
            )
        ]
    )
