import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from app.card_import import bounded
from app.card_import.models import MAX_BYTES, ParseFailure
from app.card_import.parser import parse
from app.card_import.templates import download_template
from openpyxl import load_workbook


def test_formula_oversized_corrupt_and_unmarked_content_are_rejected():
    workbook = load_workbook(BytesIO(download_template("xlsx")))
    workbook["Карточки"]["B2"] = '=WEBSERVICE("https://invalid.test")'
    output = BytesIO()
    workbook.save(output)
    for data, format in [
        (output.getvalue(), "xlsx"),
        (b"x" * (MAX_BYTES + 1), "txt"),
        (b"NOT A ZIP", "docx"),
        (b"unmarked prose", "txt"),
        (b"%PDF-corrupt", "pdf"),
    ]:
        with pytest.raises(ParseFailure):
            parse(data, format)
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"x" * (21 * 1024 * 1024))
    with pytest.raises(ParseFailure) as error:
        parse(output.getvalue(), "docx")
    assert error.value.diagnostics[0].code == "archive_limit"


@pytest.mark.asyncio
async def test_bounded_parser_process_roundtrip_and_deadline(monkeypatch, caplog):
    source = json.dumps({"schema_version": 1, "cards": [{"name": "PRIVATE_MARKER"}]}).encode()
    result = await bounded.parse_bounded(source, "json")
    assert result.drafts[0].card.name == "PRIVATE_MARKER"
    monkeypatch.setattr(bounded, "PARSER_TIMEOUT", 0.0001)
    with pytest.raises(ParseFailure) as error:
        await bounded.parse_bounded(source, "json")
    assert error.value.diagnostics[0].code == "parse_timeout"
    assert "PRIVATE_MARKER" not in caplog.text


def test_static_import_graph_has_no_ai_or_network_clients():
    import ast
    from pathlib import Path

    root = Path(__file__).parents[2]
    forbidden = {"openai", "anthropic", "langchain", "transformers", "requests", "httpx", "urllib"}
    for path in (root / "backend/app/card_import").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {alias.name.split(".")[0] for alias in node.names} & forbidden
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden
    assert not any(
        f'"{name}' in (root / "pyproject.toml").read_text()
        for name in ["openai", "anthropic", "langchain"]
    )
