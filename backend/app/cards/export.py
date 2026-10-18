from html import escape

from app.cards.models import Card


def export_html(card: Card) -> str:
    """A static view plus inert canonical JSON; no scripts, remote assets or rule engine."""

    def section(title: str, rows: list[tuple[str, str]]) -> str:
        if not rows:
            return ""
        return (
            f"<section><h2>{escape(title)}</h2><dl>"
            + "".join(f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>" for label, value in rows)
            + "</dl></section>"
        )

    content = section(
        "Поля",
        [
            (field.label, str(field.value if field.value is not None else "—"))
            for field in sorted(card.fields, key=lambda entry: entry.order)
        ],
    )
    content += section(
        "Ресурсы",
        [
            (
                resource.label,
                f"{resource.current:g}"
                + (f" / {resource.max:g}" if resource.max is not None else ""),
            )
            for resource in card.resources
        ],
    )
    content += section(
        "Навыки",
        [
            (skill.name, f"{skill.bonus or 0:+g} · {skill.description or ''}")
            for skill in card.skills
        ],
    )
    content += section(
        "Инвентарь",
        [
            (item.name, f"{item.quantity or 0:g} · {item.description or ''}")
            for item in card.inventory
        ],
    )
    content += section(
        "Способности и заклинания",
        [(ability.name, ability.description) for ability in card.abilities],
    )
    if card.notes:
        content += section("Заметки", [("", card.notes)])
    canonical = (
        card.model_dump_json()
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{escape(card.name)}</title><style>
body{{margin:0;background:#f4f1e9;color:#222;font:18px/1.5 system-ui,sans-serif}}
main{{max-width:760px;margin:auto;padding:32px 24px}}h1{{font-size:2.4rem;line-height:1.1}}
section{{border-top:1px solid #b9b3a3;margin-top:24px}}
dl{{display:grid;grid-template-columns:1fr 2fr;gap:8px}}
dt{{font-weight:600}}dd{{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}}footer{{font-size:14px;color:#59574f}}
</style></head><body><main><h1>{escape(card.name)}</h1><p>{escape(card.subtitle or "")}</p>
{content}<footer>Автономный снимок · версия {card.version} · без синхронизации</footer>
<script id="canonical-card" type="application/json">{canonical}</script></main></body></html>"""
