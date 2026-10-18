from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from app.card_import.models import Diagnostic, fail


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    children: list[Node] = field(default_factory=list)
    text: str = ""

    def find(self, cls: str) -> list[Node]:
        return ([self] if cls in self.attrs.get("class", "").split() else []) + [
            node for child in self.children for node in child.find(cls)
        ]

    def plain(self) -> str:
        return " ".join((self.text + " " + " ".join(c.plain() for c in self.children)).split())

    def first(self, cls: str) -> str:
        found = self.find(cls)
        return found[0].plain() if found else ""


class InertHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]
        self.count = 0
        self.ignored = 0
        self.canonical = ""
        self.in_canonical = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.count += 1
        if self.count > 10000 or len(self.stack) > 100:
            raise fail("html_limit", "Слишком сложный HTML")
        attributes = {key: val or "" for key, val in attrs}
        if (
            tag == "script"
            and attributes.get("id") == "canonical-card"
            and attributes.get("type") == "application/json"
        ):
            self.in_canonical = True
        if tag in {"script", "style", "iframe", "object", "embed"}:
            self.ignored += 1
        node = Node(tag, attributes)
        self.stack[-1].children.append(node)
        if tag not in {"meta", "link", "img", "input", "br", "hr", "embed", "source"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "iframe", "object", "embed"}:
            self.ignored = max(0, self.ignored - 1)
        if tag == "script":
            self.in_canonical = False
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.in_canonical:
            self.canonical += data
        elif not self.ignored:
            self.stack[-1].text += data


def read_html(data: bytes) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
    parser = InertHTML()
    parser.feed(data.decode("utf-8-sig"))
    if parser.canonical:
        canonical = json.loads(parser.canonical)
        if canonical.get("schema_version") != 1:
            raise fail("schema_version", "Неподдерживаемая версия карточки HTML")
        return [canonical], []
    root = parser.root
    name = root.first("char-name")
    if not name:
        raise fail("legacy_format", "Не найдены известные блоки карточки Vampires / Old Russia")
    card: dict[str, Any] = {
        "name": name,
        "subtitle": root.first("char-sub") or None,
        "external_key": "legacy-" + hashlib.sha256(name.encode()).hexdigest()[:24],
        "fields": [],
        "resources": [],
        "skills": [],
        "inventory": [],
        "abilities": [],
        "notes": root.first("notes-box") or None,
        "_section": "HTML",
    }
    for index, vital in enumerate(root.find("vital")):
        current = vital.first("hp-val") or vital.first("resource-val")
        maximum = vital.first("hp-max") or vital.first("resource-max")
        label = vital.first("vital-label")
        if current:
            card["resources"].append(
                {
                    "key": vital.attrs.get("data-resource", "hp"),
                    "label": label or "Ресурс",
                    "current": float(current),
                    "max": float(maximum) if maximum else None,
                }
            )
        elif label and vital.first("vital-val"):
            card["fields"].append(
                {"key": f"vital_{index}", "label": label, "value": vital.first("vital-val")}
            )
    for index, node in enumerate(root.find("attr")):
        card["fields"].append(
            {
                "key": f"attribute_{index}",
                "label": node.first("attr-name"),
                "value": node.first("attr-val"),
            }
        )
    for index, node in enumerate(root.find("skill")):
        bonus = node.first("skill-bonus")
        try:
            number: float | None = float(bonus)
        except ValueError:
            number = None
        card["skills"].append(
            {
                "key": f"skill_{index}",
                "name": node.first("skill-name"),
                "bonus": number,
                "description": bonus if number is None else None,
                "proficient": bool(node.find("proficient")),
            }
        )
    for node in root.find("inv-item"):
        if node.first("inv-name"):
            card["inventory"].append(
                {
                    "name": node.first("inv-name"),
                    "description": node.first("inv-note") or None,
                    "quantity": 1,
                }
            )
    for node in root.find("ability"):
        if node.first("ability-name"):
            card["abilities"].append(
                {
                    "name": node.first("ability-name"),
                    "description": node.first("ability-desc"),
                    "action_type": node.first("ability-type") or None,
                }
            )
    # Older mob HTML groups known names/descriptions without .ability wrappers.
    if not card["abilities"]:
        for title, description in zip(
            root.find("ability-name"), root.find("ability-desc"), strict=False
        ):
            card["abilities"].append({"name": title.plain(), "description": description.plain()})
    warning = Diagnostic(
        severity="warning",
        code="legacy_review",
        entity=card["external_key"],
        section="HTML",
        row=1,
        field="document",
        message=(
            "Перенесены только известные смысловые блоки. Стили, сценарии, ссылки "
            "и прочие блоки не исполнялись и не переносились. Проверьте карточку."
        ),
    )
    return [card], [warning]
