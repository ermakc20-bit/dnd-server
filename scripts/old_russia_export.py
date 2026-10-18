"""Explicit, offline build bridge for the bounded local Old Russia corpus.

No HTML/JavaScript is executed. Runtime imports use the installed VTT package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.card_import.parser import parse
from app.cards.models import CardData

MAX_SOURCE = 2_000_000
SLUGS = (
    "yashka-brosok",
    "malasha-inokop",
    "agafya-travnitsa",
    "varfolomei-molchalnik",
    "saveliy-glukhoy-kolokol",
    "tikhon-zharok",
    "ostapiy-krivets",
    "voevoda-vorontsov",
    "lavrentiy-som",
    "egor-klet",
    "matrona-ustinya",
    "nastasya-zharok",
    "semen-rybtsev",
    "praskovya",
    "whispering-shard",
    "false-witness",
    "false-bailiff",
    "condemned-shadow",
    "ostapiy-guard",
    "archive-arsonist",
    "archive-fire",
    "mirror-grasp",
)
FILES = {slug: f"{index:02d}-{slug}.html" for index, slug in enumerate(SLUGS, 1)}
HERO_FILES = {slug: FILES[slug] for slug in SLUGS[:5]}
HERO_FILES[SLUGS[3]] = "04-varlolomei-molchalnik.html"
ASSET = "old_russia_export_client.js"
START = "<!-- old-russia-export:v1 -->"
END = "<!-- /old-russia-export:v1 -->"
HOOK = (
    "\n// Old Russia canonical export v1 (local asset, no network).\n"
    'require("./old_russia_export_client.js").install(__dirname);\n'
)


PRELUDE = (
    "// Old Russia export preflight v1: reject before the generator writes.\n"
    'if (fs.lstatSync(path.join(root, "old_russia_export_client.js")).isSymbolicLink()) {\n'
    '  throw new Error("Unsafe Old Russia symlink");\n'
    "}\n"
    'require("./old_russia_export_client.js").preflight(root);\n'
)
ROOT_DECLARATION = "const root = __dirname;\n"


def check_paths(root: Path, names: list[str]) -> None:
    """Validate the complete write set before opening any destination for writing."""
    for name in names:
        parts = Path(name).parts
        if Path(name).is_absolute() or ".." in parts:
            raise ValueError("Unsafe Old Russia destination")
        current = root
        for index, part in enumerate(parts):
            current /= part
            if current.is_symlink():
                raise ValueError("Unsafe Old Russia symlink leaf or ancestor")
            if current.exists():
                leaf = index == len(parts) - 1
                if (leaf and not current.is_file()) or (not leaf and not current.is_dir()):
                    raise ValueError("Unsafe Old Russia destination type")


def read(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE:
        raise ValueError(f"Missing, linked or oversized source: {path.name}")
    return path.read_text(encoding="utf-8")


class LiteralReader:
    """A data-only subset of JS literals: no expressions, calls or getters."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.position = 0
        self.nodes = 0

    def whitespace(self) -> None:
        while self.position < len(self.source) and self.source[self.position].isspace():
            self.position += 1

    def consume(self, expected: str) -> None:
        self.whitespace()
        if not self.source.startswith(expected, self.position):
            raise ValueError("Invalid overview literal")
        self.position += len(expected)

    def string(self) -> str:
        self.whitespace()
        start = self.position
        self.consume('"')
        escaped = False
        while self.position < len(self.source):
            char = self.source[self.position]
            self.position += 1
            if char == '"' and not escaped:
                value: str = json.loads(self.source[start : self.position])
                return value
            escaped = char == "\\" and not escaped
        raise ValueError("Unterminated overview string")

    def value(self, depth: int = 0) -> Any:
        self.nodes += 1
        if depth > 16 or self.nodes > 20000:
            raise ValueError("Overview literal limit")
        self.whitespace()
        char = self.source[self.position : self.position + 1]
        if char == '"':
            return self.string()
        if char in ("[", "{"):
            closing = "]" if char == "[" else "}"
            self.consume(char)
            result: Any = [] if char == "[" else {}
            while True:
                self.whitespace()
                if self.source.startswith(closing, self.position):
                    self.consume(closing)
                    return result
                if char == "{":
                    if self.source[self.position : self.position + 1] == '"':
                        key = self.string()
                    else:
                        match = re.match(r"[A-Za-z_][A-Za-z_0-9]*", self.source[self.position :])
                        if match is None:
                            raise ValueError("Invalid overview key")
                        key = match[0]
                        self.position += len(key)
                    if key in result:
                        raise ValueError("Duplicate overview key")
                    self.consume(":")
                    result[key] = self.value(depth + 1)
                else:
                    result.append(self.value(depth + 1))
                self.whitespace()
                if self.source.startswith(closing, self.position):
                    continue
                self.consume(",")
        match = re.match(
            r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", self.source[self.position :]
        )
        if match:
            self.position += len(match[0])
            number = json.loads(match[0])
            if not math.isfinite(number):
                raise ValueError("Nonfinite overview number")
            return number
        raise ValueError("Only strings, numbers, arrays and objects are allowed")


def overview(source: str) -> list[dict[str, Any]]:
    marker = "const cards = "
    if source.count(marker) != 1:
        raise ValueError("Expected one overview cards array")
    reader = LiteralReader(source.split(marker, 1)[1])
    rows = reader.value()
    reader.consume(";")
    if not isinstance(rows, list) or len(rows) != 22:
        raise ValueError("Expected exactly 22 Old Russia cards")
    allowed = {
        "id",
        "type",
        "name",
        "subtitle",
        "sigil",
        "hp",
        "ac",
        "stats",
        "attrs",
        "role",
        "actions",
        "scenes",
    }
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) - allowed:
            raise ValueError("Unknown overview fields")
        if row.get("id") != SLUGS[index] or row.get("type") != (
            "hero" if index < 5 else "npc" if index < 14 else "mob"
        ):
            raise ValueError("Unexpected corpus identity, order or kind")
        for key in ("name", "subtitle", "sigil", "role"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError(f"Invalid overview {key}")
        if not isinstance(row.get("stats"), dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in row["stats"].items()
        ):
            raise ValueError("Invalid overview stats")
        for key in ("attrs", "scenes"):
            if not isinstance(row.get(key, []), list) or not all(
                isinstance(v, str) for v in row.get(key, [])
            ):
                raise ValueError(f"Invalid overview {key}")
        if not isinstance(row.get("actions"), list) or not all(
            isinstance(v, list) and len(v) == 2 and all(isinstance(t, str) for t in v)
            for v in row["actions"]
        ):
            raise ValueError("Invalid overview actions")
        for key in ("hp", "ac"):
            if key in row and (type(row[key]) is not int or not 0 <= row[key] <= 1_000_000_000):
                raise ValueError(f"Invalid overview {key}")
    return rows


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    content: list[Node | str] = field(default_factory=list)

    def has(self, class_name: str) -> bool:
        return class_name in self.attrs.get("class", "").split()

    def all(self, class_name: str) -> list[Node]:
        result = []
        for item in self.content:
            if isinstance(item, Node):
                if item.has(class_name):
                    result.append(item)
                result.extend(item.all(class_name))
        return result

    def text(self) -> str:
        if self.tag in {"script", "style", "button"} and not self.has("skill"):
            return ""
        # Retain the source stream order, including text after inline strong/em tags.
        return "".join(item if isinstance(item, str) else item.text() for item in self.content)

    def normalized(self) -> str:
        return " ".join(self.text().split())

    def one(self, class_name: str) -> Node:
        nodes = self.all(class_name)
        if len(nodes) != 1:
            raise ValueError(f"Expected one semantic node: {class_name}")
        return nodes[0]

    def label(self, class_name: str) -> str:
        return self.one(class_name).normalized()


class Document(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.stack = [self.root]
        self.count = 0
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.count += 1
        if self.count > 15000 or len(self.stack) > 64:
            raise ValueError("HTML limit")
        node = Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].content.append(node)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].content.append(data)


def identity(slug: str, collection: str, index: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"old-russia:v1:{slug}:{collection}:{index}"))


def build_card(row: dict[str, Any], hero_html: str | None = None) -> dict[str, Any]:
    slug = row["id"]
    fields: list[dict[str, Any]] = []

    def add(label: str, value: str) -> None:
        fields.append(
            {"key": f"source_{len(fields)}", "label": label, "value": value, "order": len(fields)}
        )

    add("Сигил", row["sigil"])
    add("Роль", row["role"])
    for label, value in row["stats"].items():
        add(label, value)
    if "ac" in row:
        add("Класс доспеха (overview)", str(row["ac"]))
    for value in row.get("attrs", []):
        add("Характеристика (overview)", value)
    for value in row.get("scenes", []):
        add("Сцена", value)
    resources = []
    if "hp" in row:
        resources.append({"key": "hp", "label": "Здоровье", "current": row["hp"], "max": row["hp"]})
    abilities = [
        {
            "id": identity(slug, "overview_actions", i),
            "name": name,
            "description": text,
            "action_type": "Действия / улики (overview)",
        }
        for i, (name, text) in enumerate(row["actions"])
    ]
    skills: list[dict[str, Any]] = (
        [
            {"key": f"skill_{index}", "name": label, "description": value, "proficient": True}
            for index, (label, value) in enumerate(
                [("Роль", row["role"]), *row["stats"].items()][:6]
            )
        ]
        if hero_html is None
        else []
    )
    inventory: list[dict[str, Any]] = []
    notes: list[str] = []
    subtitle = row["subtitle"]
    if hero_html is not None:
        sheet = Document(hero_html).root.one("sheet")
        known_classes = set(
            """
            sheet sheet-title header avatar header-info char-name char-sub badges badge
            special-banner vitals vital vital-label vital-val hp-val vital-max hp-max hp-bar
            hp-fill hp-controls hp-btn attrs attr attr-name attr-val attr-mod section-title
            two-col skills skill skill-dot proficient skill-name skill-bonus inv inv-item
            inv-icon inv-name inv-note ability ability-type ability-name ability-desc
            uses-tracker use-pip spent ulta-card ulta-label ulta-name ulta-desc adv-list
            adv-item adv-icon tips-list tip-item notes-box footer footer-hint export-date
        """.split()
        )

        def check_semantics(node: Node) -> None:
            if set(node.attrs.get("class", "").split()) - known_classes:
                raise ValueError("Unknown hero semantic block; explicit mapping required")
            for item in node.content:
                if isinstance(item, Node):
                    check_semantics(item)

        check_semantics(sheet)
        if sheet.label("char-name") != row["name"]:
            add("Имя на карточке", sheet.label("char-name"))
        add("Описание (overview)", subtitle)
        subtitle = sheet.label("char-sub")
        add("Заголовок", sheet.label("sheet-title"))
        add("Аватар", sheet.label("avatar"))
        for node in sheet.all("badge") + sheet.all("special-banner"):
            add("Особенность", node.normalized())
        hp = sheet.label("hp-val")
        maximum = sheet.label("hp-max")
        if not re.fullmatch(r"[0-9]+", hp) or not re.fullmatch(r"[0-9]+", maximum):
            raise ValueError("Invalid hero HP")
        resources = [{"key": "hp", "label": "Здоровье", "current": int(hp), "max": int(maximum)}]
        for node in sheet.all("vital"):
            if not node.all("hp-val"):
                add(node.label("vital-label"), node.label("vital-val"))
                add(node.label("vital-label") + " — пояснение", node.label("vital-max"))
        for node in sheet.all("attr"):
            add(node.label("attr-name"), node.label("attr-val"))
            add(node.label("attr-name") + " — модификатор", node.label("attr-mod"))
        for index, node in enumerate(sheet.all("skill")):
            bonus = node.label("skill-bonus")
            if not re.fullmatch(r"[+-]?[0-9]+", bonus):
                raise ValueError("Invalid hero skill bonus")
            skills.append(
                {
                    "key": f"skill_{index}",
                    "name": node.label("skill-name"),
                    "bonus": int(bonus),
                    "proficient": node.one("skill-dot").has("proficient"),
                    "description": "Спасброски",
                }
            )
        for node in sheet.all("inv-item"):
            if node.all("inv-name"):
                # Quantity stays null: numbers within prose names are not game rules.
                description = "\n".join(n.normalized() for n in node.all("inv-note")) or None
                inventory.append(
                    {
                        "id": identity(slug, "inventory", len(inventory)),
                        "name": node.label("inv-name"),
                        "description": description,
                        "icon": node.label("inv-icon"),
                    }
                )
        rich = sheet.all("inv-item")
        rich = [node for node in rich if node.all("ability-name")]
        rich += sheet.all("ulta-card")
        rich_abilities = []
        for index, node in enumerate(rich):
            ultimate = node.has("ulta-card")
            name = node.label("ulta-name" if ultimate else "ability-name")
            description = node.label("ulta-desc" if ultimate else "ability-desc")
            action_type = node.label("ulta-label" if ultimate else "ability-type")
            tracker = node.all("uses-tracker")
            uses = None
            if tracker:
                pips = node.all("use-pip")
                if not pips:
                    raise ValueError("Empty uses tracker")
                # Full source wording includes reset cadence and inline emphasis.
                if ultimate:
                    uses_label = action_type
                else:
                    containers = [
                        item
                        for item in node.content
                        if isinstance(item, Node) and item.all("uses-tracker")
                    ]
                    uses_label = containers[0].normalized() if containers else "Использования"
                uses = {
                    "key": f"uses_{index}",
                    "label": uses_label,
                    "current": sum(not p.has("spent") for p in pips),
                    "max": len(pips),
                }
                for pip in pips:
                    if pip.attrs.get("title"):
                        description += "\n" + pip.attrs["title"]
            rich_abilities.append(
                {
                    "id": identity(slug, "abilities", index),
                    "name": name,
                    "description": description,
                    "action_type": action_type,
                    "uses": uses,
                }
            )
        abilities = rich_abilities + abilities
        for class_name, label in (
            ("adv-item", "Преимущества в этом приключении"),
            ("tip-item", "Подсказки игроку"),
            ("notes-box", "История"),
        ):
            for node in sheet.all(class_name):
                notes.append(label + ": " + node.normalized())
    card = CardData.model_validate(
        {
            "schema_version": 1,
            "kind": {"hero": "player_character", "npc": "npc", "mob": "mob"}[row["type"]],
            "name": row["name"],
            "subtitle": subtitle,
            "external_key": "old-russia:" + slug,
            "fields": fields,
            "resources": resources,
            "skills": skills,
            "inventory": inventory,
            "abilities": abilities,
            "notes": "\n".join(notes) or None,
        }
    )
    return card.model_dump(mode="json")


def emit(root: Path) -> dict[str, Any]:
    rows = overview(read(root / "index.html"))
    cards = [
        build_card(row, read(root / HERO_FILES[row["id"]]) if row["type"] == "hero" else None)
        for row in rows
    ]
    document = {"schema_version": 1, "cards": cards}
    result = parse(json_bytes(document), "json")
    if result.diagnostics or len(result.drafts) != 22:
        raise ValueError("Canonical export produced import diagnostics")
    return document


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def clean_html(source: str) -> str:
    source = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", source, flags=re.S)
    return re.sub(
        r'^[ \t]*@import url\("https://fonts\.googleapis\.com/[^\n]*\);\n?', "", source, flags=re.M
    )


def apply(root: Path, document: dict[str, Any]) -> list[str]:
    # Validate every destination, including the asset, before any write.
    # The original five hero files are inputs and are never written.
    paths = [
        "index.html",
        "old-russia/index.html",
        *["old-russia/" + value for value in FILES.values()],
    ]
    check_paths(root, [*paths, "build_old_russia_pages.js", ASSET, *HERO_FILES.values()])
    builder = read(root / "build_old_russia_pages.js").replace(PRELUDE, "")
    if builder.count(ROOT_DECLARATION) != 1:
        raise ValueError("Expected one generator root declaration")
    builder = builder.replace(ROOT_DECLARATION, ROOT_DECLARATION + PRELUDE)
    sources = {name: clean_html(read(root / name)) for name in paths}
    client = read(Path(__file__).with_name(ASSET))
    manifest = {
        "document": document,
        "files": FILES,
        "source_hashes": {
            name: hashlib.sha256(read(root / name).encode()).hexdigest()
            for name in HERO_FILES.values()
        },
        "overview_hash": hashlib.sha256(sources["index.html"].encode()).hexdigest(),
    }
    asset = (
        "const oldRussiaExportV1 = "
        + json.dumps(manifest, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        + ";\n"
        + client
    )
    additions: dict[str, str] = {}
    for name, source in sources.items():
        if source.count("</body>") != 1:
            raise ValueError("Expected one body boundary")
        slug = next(
            (key for key, filename in FILES.items() if name == "old-russia/" + filename), ""
        )
        relative = "../" if name.startswith("old-russia/") else ""
        block = (
            f'{START}\n<script src="{relative}{ASSET}" '
            f'data-old-russia-card="{slug}"></script>\n{END}\n'
        )
        additions[name] = source.replace("</body>", block + "</body>")
    if HOOK.strip() not in builder:
        builder += HOOK
    additions["build_old_russia_pages.js"] = builder
    additions[ASSET] = asset
    for name, content in additions.items():
        (root / name).write_text(content, encoding="utf-8")
    return list(additions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards-root", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--apply", action="store_true", help="Install local offline buttons and regeneration hook"
    )
    args = parser.parse_args()
    try:
        root = args.cards_root.resolve(strict=True)
        if not args.output_dir and not args.apply:
            parser.error("Specify --output-dir and/or --apply")
        document = emit(root)
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "old-russia-v1.json").write_bytes(json_bytes(document))
            for slug, card in zip(SLUGS, document["cards"], strict=True):
                (args.output_dir / f"{slug}.json").write_bytes(json_bytes(card))
        paths = apply(root, document) if args.apply else []
        print(
            json.dumps(
                {
                    "cards": 22,
                    "kinds": {"player_character": 5, "npc": 9, "mob": 8},
                    "applied_paths": paths,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (ValueError, OSError) as error:
        print(f"Old Russia export rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
