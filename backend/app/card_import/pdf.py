from io import BytesIO
from typing import Any

from pypdf import PdfReader
from pypdf.generic import IndirectObject

from app.card_import.models import MAX_EXPANDED, fail
from app.card_import.office import read_markup


def read_pdf(data: bytes) -> tuple[list[dict[str, Any]], int]:
    reader = PdfReader(BytesIO(data), strict=True)
    if reader.is_encrypted or len(reader.pages) > 100:
        raise fail("pdf_limit", "Зашифрованный PDF или более 100 страниц не поддерживается")
    seen: set[int] = set()
    count = 0
    forbidden = {
        "/JS",
        "/JavaScript",
        "/OpenAction",
        "/AA",
        "/EmbeddedFiles",
        "/EF",
        "/RichMedia",
        "/XFA",
        "/Launch",
        "/URI",
        "/GoToR",
        "/SubmitForm",
        "/ImportData",
    }

    def inspect(node: Any, depth: int = 0) -> None:
        nonlocal count
        count += 1
        if count > 50000 or depth > 80:
            raise fail("pdf_limit", "Слишком сложный PDF")
        if isinstance(node, IndirectObject):
            if node.idnum in seen:
                return
            seen.add(node.idnum)
            node = node.get_object()
        if isinstance(node, dict):
            if forbidden.intersection(node) or str(node.get("/S", "")) in forbidden:
                raise fail("active_content", "Активное содержимое и вложения PDF запрещены")
            for child in node.values():
                inspect(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                inspect(child, depth + 1)

    inspect(reader.trailer)
    texts = []
    total = 0
    for page in reader.pages:
        text = page.extract_text()
        total += len(text.encode())
        if total > MAX_EXPANDED:
            raise fail("pdf_limit", "Слишком большой текст PDF")
        texts.append(text)
    return read_markup("\n".join(texts))
