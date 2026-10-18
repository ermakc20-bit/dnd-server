"""Portable real Old Russia corpus contract; no parent-directory dependency."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from app.card_import.parser import parse

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "old_russia_corpus_v1.json"


def corpus_root(tmp_path: Path) -> Path:
    fixture = json.loads(FIXTURE.read_text())
    root = tmp_path / "cards"
    root.mkdir()
    (root / "index.html").write_text(
        '<html><body><main id="content"></main><script>const cards = '
        + json.dumps(fixture["overview"], ensure_ascii=False)
        + ";\nconst labels = {};</script></body></html>"
    )
    for hero in fixture["heroes"].values():
        (root / hero["file"]).write_text(hero["html"])
    return root


def emit(root: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts/old_russia_export.py"),
            "--cards-root",
            str(root),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_real_corpus_export_preserves_rich_semantics_and_roundtrip(tmp_path: Path) -> None:
    root = corpus_root(tmp_path)
    output = tmp_path / "json"
    result = emit(root, output)
    assert result.returncode == 0, result.stderr
    batch = (output / "old-russia-v1.json").read_bytes()
    drafts = parse(batch, "json")
    assert not drafts.diagnostics
    assert len(drafts.drafts) == 22
    assert Counter(d.card.kind for d in drafts.drafts) == {
        "player_character": 5,
        "npc": 9,
        "mob": 8,
    }
    cards = [d.card.model_dump(mode="json") for d in drafts.drafts]
    assert [
        d.card
        for d in parse(json.dumps({"schema_version": 1, "cards": cards}).encode(), "json").drafts
    ] == [d.card for d in drafts.drafts]
    first = cards[0]
    assert first["name"] == "Яшка-Бросок"
    assert first["resources"][0]["current"] == 30
    assert first["inventory"][0]["name"] == "Метательный кинжал / топорик"
    assert first["inventory"][0]["quantity"] is None
    assert first["skills"][0]["name"] == "Ловкость"
    assert first["skills"][0]["bonus"] == 6
    assert first["abilities"][0]["name"] == "Веер стали"  # noqa: RUF001
    assert first["abilities"][0]["uses"]["max"] == 1
    ultimate = next(a for a in first["abilities"] if a["name"] == "Смерть под аплодисменты")
    assert "Телосложения Сл 14. При провале" in ultimate["description"]
    assert "Купец Сом: попробуй отвлечь" in first["notes"]
    assert all(
        a["geometry"] is None and a["automation"] is None for c in cards for a in c["abilities"]
    )
    assert len({a["id"] for c in cards for a in c["abilities"]}) == sum(
        len(c["abilities"]) for c in cards
    )
    again = emit(root, output)
    assert again.returncode == 0
    assert (output / "old-russia-v1.json").read_bytes() == batch
    assert len(list(output.glob("*.json"))) == 23


def test_apply_is_offline_idempotent_and_survives_regeneration(tmp_path: Path) -> None:
    root = corpus_root(tmp_path)
    fixture = json.loads(FIXTURE.read_text())
    generated = root / "old-russia"
    generated.mkdir()
    (generated / "index.html").write_text("<html><body>Каталог</body></html>")
    pages = sorted(json.loads(FIXTURE.read_text())["overview"], key=lambda row: row["id"])
    for row in pages:
        position = next(
            i for i, value in enumerate(fixture["overview"], 1) if value["id"] == row["id"]
        )
        (generated / f"{position:02d}-{row['id']}.html").write_text(
            "<html><body>Карточка</body></html>"
        )
    # The existing generator owns the pages; integration must reinstall exports afterwards.
    (root / "build_old_russia_pages.js").write_text(
        'const fs = require("fs"); const path = require("path");\n'
        "const root = __dirname;\n"
        'for (const file of fs.readdirSync(path.join(__dirname,"old-russia"))) '
        'fs.writeFileSync(path.join(__dirname,"old-russia",file),"<html><body>Карточка</body></html>");\n'
    )
    originals = {
        hero["file"]: (root / hero["file"]).read_bytes() for hero in fixture["heroes"].values()
    }
    command = [
        sys.executable,
        str(ROOT / "scripts/old_russia_export.py"),
        "--cards-root",
        str(root),
        "--apply",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, result.stderr
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert b"data-old-russia-card" in (root / "index.html").read_bytes()
    assert (root / "old_russia_export_client.js").is_file()
    again = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603
    assert again.returncode == 0, again.stderr
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    rebuild = subprocess.run(  # noqa: S603
        ["node", str(root / "build_old_russia_pages.js")],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert rebuild.returncode == 0, rebuild.stderr
    assert all(b"data-old-russia-card" in p.read_bytes() for p in generated.glob("*.html"))
    assert originals == {name: (root / name).read_bytes() for name in originals}


def test_browser_download_uses_only_visible_current_card_state(tmp_path: Path) -> None:
    root = corpus_root(tmp_path)
    output = tmp_path / "json"
    result = emit(root, output)
    assert result.returncode == 0, result.stderr
    # Existing locked jsdom runtime exercises the actual client click/download boundary.
    runner = r"""
const fs = require('fs');
const {JSDOM} = require(process.cwd() + '/frontend/node_modules/jsdom');
const document = JSON.parse(fs.readFileSync(process.argv[1] + '/old-russia-v1.json'));
const dom = new JSDOM(`<body><article class="sheet">
<span class="hp-val">0</span><span class="hp-max">30</span>
<button class="skill"><i class="skill-dot"></i></button>
<button class="skill"><i class="skill-dot proficient"></i></button>
${[1,3,2,1].map((n,i)=>`<div class="${i===3?'ulta-card':'inv-item ability'}">
${i===3?'':'<span class="ability-name">Умение</span>'}
${Array.from({length:n},(_,j)=>
`<i class="use-pip ${j===0?'spent':''}"></i>`).join('')}</div>`).join('')}
</article><script data-old-russia-card="yashka-brosok"></script></body>`,
{runScripts:'outside-only'});
const w=dom.window; let downloaded;
w.Blob=class {constructor(parts){this.parts=parts;}};
w.URL.createObjectURL=blob=>{downloaded=JSON.parse(blob.parts.join(''));return 'blob:offline';};
w.URL.revokeObjectURL=()=>{}; w.HTMLAnchorElement.prototype.click=function(){};
w.eval('const oldRussiaExportV1 = '+JSON.stringify({document,files:{}})+';\n'
+fs.readFileSync('scripts/old_russia_export_client.js','utf8'));
w.document.querySelector('[data-old-russia-export="batch"]').click();
if(!downloaded || downloaded.cards.length!==22) throw Error('No batch download');
const card=downloaded.cards[0];
if(card.resources[0].current!==0 || card.skills[0].proficient!==false
|| card.abilities[1].uses.current!==2 || card.abilities[3].uses.current!==0)
throw Error('Live state lost');
if(downloaded.cards[1].resources[0].current!==30) throw Error('Another page state guessed');
const saved=JSON.stringify(downloaded);
w.document.querySelector('.hp-val').textContent='NaN'; downloaded=null;
w.document.querySelector('[data-old-russia-export="single"]').click();
if(downloaded!==null || !w.document.querySelector('[role="alert"]').textContent)
throw Error('Invalid DOM silently exported');
console.log(saved); w.close();
"""
    browser = subprocess.run(  # noqa: S603
        ["node", "-e", runner, str(output)],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert browser.returncode == 0, browser.stderr
    drafts = parse(browser.stdout.encode(), "json")
    assert len(drafts.drafts) == 22 and not drafts.diagnostics


def test_bridge_rejects_unmapped_meaningful_source_and_active_literals(tmp_path: Path) -> None:
    root = corpus_root(tmp_path)
    hero = root / "01-yashka-brosok.html"
    original = hero.read_text()
    hero.write_text(
        original.replace(
            '<article class="sheet">',
            '<article class="sheet"><div class="new-rule">Неизвестное правило</div>',
        )
    )
    result = emit(root, tmp_path / "json")
    assert result.returncode != 0 and "semantic" in result.stderr
    hero.write_text(original)
    index = root / "index.html"
    index.write_text(
        index.read_text().replace('"stats":', 'unexpected: process.exit(77), "stats":', 1)
    )
    result = emit(root, tmp_path / "json")
    assert result.returncode == 1 and "Only strings" in result.stderr
    assert not (tmp_path / "json" / "old-russia-v1.json").exists()


def generator_root(tmp_path: Path) -> Path:
    root = corpus_root(tmp_path)
    generated = root / "old-russia"
    generated.mkdir()
    fixture = json.loads(FIXTURE.read_text())
    for index, row in enumerate(fixture["overview"], 1):
        (generated / f"{index:02d}-{row['id']}.html").write_text(
            "<html><body>Карточка</body></html>"
        )
    (generated / "index.html").write_text("<html><body>Каталог</body></html>")
    (root / "build_old_russia_pages.js").write_text(
        'const fs = require("fs"); const path = require("path");\n'
        "const root = __dirname;\n"
        'for (const file of fs.readdirSync(path.join(root,"old-russia"))) '
        'fs.writeFileSync(path.join(root,"old-russia",file),'
        '"<html><body>Карточка</body></html>");\n'
    )
    return root


def apply_corpus(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts/old_russia_export.py"),
            "--cards-root",
            str(root),
            "--apply",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_symlink_boundaries_reject_before_any_apply_or_installer_write(tmp_path: Path) -> None:
    import shutil

    for mode in ("apply", "installer"):
        for boundary in ("asset", "ancestor"):
            case = tmp_path / f"{mode}-{boundary}"
            case.mkdir()
            root = generator_root(case)
            assert apply_corpus(root).returncode == 0
            runtime = case / "runtime.js"
            shutil.copyfile(root / "old_russia_export_client.js", runtime)
            sentinel = case / "outside-sentinel.txt"
            sentinel.write_text("Outside the exact owned boundary\n")
            if boundary == "asset":
                (root / "old_russia_export_client.js").unlink()
                (root / "old_russia_export_client.js").symlink_to(sentinel)
            else:
                outside = case / "outside-pages"
                (root / "old-russia").rename(outside)
                (root / "old-russia").symlink_to(outside, target_is_directory=True)
            targets = [root / "index.html", *sorted((root / "old-russia").glob("*.html")), sentinel]
            before = {str(p): p.read_bytes() for p in targets}
            result = (
                apply_corpus(root)
                if mode == "apply"
                else subprocess.run(  # noqa: S603
                    [  # noqa: S607
                        "node",
                        "-e",
                        "require(process.argv[1]).install(process.argv[2])",
                        str(runtime),
                        str(root),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            )
            assert result.returncode != 0, f"{mode} followed {boundary} symlink"
            assert before == {str(p): p.read_bytes() for p in targets}


def test_stale_source_regeneration_preserves_all_export_pages(tmp_path: Path) -> None:
    root = generator_root(tmp_path)
    assert apply_corpus(root).returncode == 0
    targets = [
        root / "index.html",
        *sorted((root / "old-russia").glob("*.html")),
        root / "old_russia_export_client.js",
    ]
    before = {str(p): p.read_bytes() for p in targets}
    hero = root / "01-yashka-brosok.html"
    hero.write_text(hero.read_text().replace("Сл 14", "Сл 15"))
    result = subprocess.run(  # noqa: S603
        ["node", str(root / "build_old_russia_pages.js")],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and "source changed" in result.stderr
    assert before == {str(p): p.read_bytes() for p in targets}
