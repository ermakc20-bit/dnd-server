from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from app.card_import.models import (
    MAX_BYTES,
    MAX_DRAFTS,
    CardDraft,
    Diagnostic,
    DraftSet,
    Location,
    ParseFailure,
    SourceFragment,
    fail,
)
from app.cards.models import CardData
from app.system_packages.service import validate_card


def extra_key(label: str) -> str:
    return "import_" + hashlib.sha256(label.encode()).hexdigest()[:20]


def build_drafts(
    rows: list[dict[str, Any]], version: int = 1, diagnostics: list[Diagnostic] | None = None,
    *, fragments: list[SourceFragment] | None = None,
) -> DraftSet:
    if type(version) is not int or version not in (0, 1):
        raise fail("schema_version", "Поддерживаются версии 0 и 1", field="schema_version")
    if not 1 <= len(rows) <= MAX_DRAFTS:
        raise fail("entity_limit", "В документе должно быть от 1 до 100 карточек")
    messages = list(diagnostics or [])
    drafts = []
    seen: set[str] = set()
    for index, entry in enumerate(rows, 1):
        data = dict(entry)
        source = data.pop("_source", {})
        section = str(data.pop("_section", "Карточки"))
        row = int(data.pop("_row", index))
        external = str(data.get("external_key") or f"entity-{index}")
        if external in seen:
            raise fail(
                "duplicate_key",
                "Внешний ключ повторяется",
                section=section,
                row=row,
                field="external_key",
                entity=external,
            )
        seen.add(external)
        data["external_key"] = external
        if "schema_version" in data and (
            type(data["schema_version"]) is not int or data["schema_version"] not in (0, 1)
        ):
            raise fail(
                "schema_version",
                "Неподдерживаемая версия карточки",
                section=section,
                row=row,
                field="schema_version",
                entity=external,
            )
        data["schema_version"] = 1
        count = data.pop("count", 1)
        token = data.pop("create_token", False)
        # Full canonical exports carry identity fields, never imported as shared IDs.
        for key in (
            "id",
            "campaign_id",
            "room_id",
            "version",
            "created_at",
            "updated_at",
            "can_edit_structure",
            "can_edit_current",
            "can_export",
        ):
            data.pop(key, None)
        for key in list(data):
            if key not in CardData.model_fields:
                value = data.pop(key)
                data.setdefault("fields", []).append(
                    {
                        "key": extra_key(key),
                        "label": key,
                        "value": value
                        if isinstance(value, str)
                        else json.dumps(value, ensure_ascii=False),
                    }
                )
                extra_origin = Location.model_validate(
                    source.get(key, {"section": section, "row": row, "field": key})
                )
                messages.append(
                    Diagnostic(
                        severity="warning",
                        code="unknown_field",
                        message="Неизвестное поле сохранено как дополнительное",
                        entity=external,
                        section=extra_origin.section,
                        row=extra_origin.row,
                        field=extra_origin.field,
                    )
                )
        for collection in ("inventory", "abilities"):
            for position, item in enumerate(data.get(collection, [])):
                item = dict(item)
                item.setdefault(
                    "id",
                    str(uuid5(NAMESPACE_URL, f"vtt-import:{external}:{collection}:{position}")),
                )
                data[collection][position] = item
        try:
            card = validate_card(CardData.model_validate(data))
            locations = {
                key: Location(section=section, row=row, field=key)
                for key in data
                if key != "schema_version"
            }
            locations.update(source)
            drafts.append(
                CardDraft(
                    external_key=external,
                    card=card,
                    count=count,
                    create_token=token,
                    source=locations,
                )
            )
        except (ValidationError, ValueError) as error:
            detail = error.errors()[0] if isinstance(error, ValidationError) else None
            field = (
                ".".join(str(p) for p in detail["loc"])
                if detail is not None
                else "card"
            )
            if (
                detail is not None
                and detail["type"] == "value_error"
                and len(detail["loc"]) == 2
                and detail["loc"][0] == "fields"
            ):
                field += ".value"
            origin = next(
                (
                    source[key]
                    for key in sorted(source, key=len, reverse=True)
                    if field == key or field.startswith(key + ".")
                ),
                None,
            )
            if origin is not None:
                origin = Location.model_validate(origin)
                section, row, field = origin.section, origin.row, origin.field
            raise fail(
                "invalid_field",
                "Проверьте тип и допустимый диапазон поля",
                section=section,
                row=row,
                field=field,
                entity=external,
            ) from None
    if version == 0:
        messages.append(
            Diagnostic(
                severity="info",
                code="migrated_v0",
                message="Совместимый контракт 0 преобразован в версию 1",
                section="Документ",
                row=1,
                field="schema_version",
            )
        )
    return DraftSet(drafts=drafts, diagnostics=messages, fragments=fragments or [])


def parse(data: bytes, format: str) -> DraftSet:
    if not 0 < len(data) <= MAX_BYTES:
        raise fail("file_size", "Разрешены файлы до 5 МБ")
    try:
        if format == "json":

            def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in pairs:
                    if key in result:
                        raise fail("duplicate_field", "Повтор поля JSON", field=key[:160])
                    result[key] = value
                return result

            document = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique)
            if "schema_version" not in document:
                raise fail("schema_version", "Укажите schema_version", field="schema_version")
            cards = document.get("cards", [document])
            return build_drafts(cards, document["schema_version"])
        if format in {"xlsx", "docx", "txt"}:
            from app.card_import.office import read_docx, read_markup, read_xlsx

            if format == "xlsx":
                rows, version = read_xlsx(data)
            elif format == "docx":
                rows, version = read_docx(data)
            else:
                rows, version = read_markup(data.decode("utf-8-sig"))
            return build_drafts(rows, version, fragments=getattr(rows, "fragments", None))
        if format == "html":
            from app.card_import.legacy import read_html

            rows, messages = read_html(data)
            return build_drafts(rows, diagnostics=messages)
        if format == "pdf":
            from app.card_import.pdf import read_pdf

            rows, version = read_pdf(data)
            return build_drafts(rows, version, fragments=getattr(rows, "fragments", None))
        raise fail("format", "Формат не поддерживается")
    except ParseFailure:
        raise
    except Exception:
        # Parser errors can contain document text. Only fixed diagnostics leave this boundary.
        raise fail("corrupt_file", "Файл повреждён или не соответствует формату") from None
