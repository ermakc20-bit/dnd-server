from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".ai-studio/project.yaml"
SPEC = ROOT / "docs/specs/VTT-001-foundation.md"


def validate(script: str, flag: str, path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / script), flag, str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def test_current_project_manifest_is_valid() -> None:
    assert validate("validate_project.py", "--manifest", MANIFEST).returncode == 0


@pytest.mark.parametrize(
    "section", ["project", "commands", "routing", "review", "release", "autonomy",
                "integrations", "secrets"],
)
def test_project_rejects_missing_sections(tmp_path: Path, section: str) -> None:
    lines = MANIFEST.read_text().splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines) if line.startswith(f"{section}:"))
    end = next((index for index in range(start + 1, len(lines))
                if lines[index] and not lines[index][0].isspace()), len(lines))
    fixture = tmp_path / "missing.yaml"
    fixture.write_text("".join(lines[:start] + lines[end:]))
    result = validate("validate_project.py", "--manifest", fixture)
    assert result.returncode == 1
    assert section in result.stderr


@pytest.mark.parametrize("original,replacement,error", [
    ("schema_version: 2", "schema_version: 1", "schema_version"),
    ("schema_version: 2", "schema_version: true", "schema_version"),
    ('  id: "dnd-vtt-v2"', '  id: ""', "project.id"),
    ('    - "DnD VTT product owner"', '    - 42', "project.owners"),
    ('  risk_class: "critical"', '  risk_class: "unknown"', "project.risk_class"),
    ('    - "make build"', '    - false', "commands.build"),
    ('  concurrency: 1', '  concurrency: 0', "autonomy.concurrency"),
    ('  budget: 0', '  budget: -1', "autonomy.budget"),
    ('  allowed: false', '  allowed: "false"', "autonomy.allowed"),
    ('  deploy: false', '  deploy: 1', "autonomy.deploy"),
    ('    - "local"', '    - 23', "release.environments"),
    ('    - "Supabase"', '    - null', "integrations.guarded"),
    ('    - "credentials"', '    - ""', "secrets.prohibited_outputs"),
    ('  rollback: "Redeploy the previous immutable image; database changes remain '
     'backward-compatible and use forward fixes"', '  rollback: null', "release.rollback"),
    ('  push: false\n', '', "autonomy.push"),
    ('  permitted_sources:', '  unexpected_field: []\n  permitted_sources:', "secrets"),
])
def test_project_rejects_invalid_structure_and_types(
    tmp_path: Path, original: str, replacement: str, error: str,
) -> None:
    source = MANIFEST.read_text()
    assert original in source
    fixture = tmp_path / "invalid.yaml"
    fixture.write_text(source.replace(original, replacement, 1))
    result = validate("validate_project.py", "--manifest", fixture)
    assert result.returncode == 1
    assert error in result.stderr


@pytest.mark.parametrize("original,replacement,error", [
    ('      - "specification-fidelity"', '      - "unknown-lens"', "required_review_lenses"),
    ('\n    - "engineering"\n', '\n', "required_review_lenses"),
    ('      - "context"', '      - "unknown-gate"', "required_gates"),
    ('      - "review"\n', '', "required_gates"),
    ('      - "authority"', '      - "authority"\n      - "authority"', "required_gates"),
    ('\n    - "engineering"', '\n    - "engineering"\n    - "engineering"', "available_lenses"),
    ('  budget: 0', '  budget: 0\n  budget: 12', "duplicate YAML key"),
])
def test_project_rejects_unknown_duplicate_and_inconsistent_references(
    tmp_path: Path, original: str, replacement: str, error: str,
) -> None:
    fixture = tmp_path / "references.yaml"
    source = MANIFEST.read_text()
    assert original in source
    fixture.write_text(source.replace(original, replacement, 1))
    result = validate("validate_project.py", "--manifest", fixture)
    assert result.returncode == 1
    assert error in result.stderr


def test_current_spec_has_valid_traceability() -> None:
    assert validate("validate_spec.py", "--spec", SPEC).returncode == 0


@pytest.mark.parametrize("mutation,error", [
    ("missing-requirements", "Requirements"),
    ("missing-acceptance", "Acceptance criteria"),
    ("duplicate-requirement", "duplicate requirement"),
    ("duplicate-acceptance", "duplicate acceptance"),
    ("empty-requirements", "Requirements"),
    ("empty-acceptance", "Acceptance criteria"),
])
def test_spec_rejects_missing_empty_and_duplicate_declarations(
    tmp_path: Path, mutation: str, error: str,
) -> None:
    source = SPEC.read_text()
    if mutation.startswith("missing-") or mutation.startswith("empty-"):
        title = "Requirements" if mutation.endswith("requirements") else "Acceptance criteria"
        start = source.index(f"## {title}\n")
        end = source.index("\n## ", start + 3)
        replacement = "" if mutation.startswith("missing-") else f"## {title}\n"
        source = source[:start] + replacement + source[end:]
    else:
        prefix = "- `FR-FOUNDATION-APP`" if mutation.endswith("requirement") else "- [x] `AC-APP`"
        line = next(line for line in source.splitlines(keepends=True) if line.startswith(prefix))
        source = source.replace(line, line + line, 1)
    fixture = tmp_path / "declarations.md"
    fixture.write_text(source)
    result = validate("validate_spec.py", "--spec", fixture)
    assert result.returncode == 1
    assert error in result.stderr


@pytest.mark.parametrize("mutation,error", [
    ("unknown-requirement", "unknown requirement"),
    ("uncovered-requirement", "uncovered requirement"),
    ("missing-evidence-section", "Evidence map"),
    ("missing-evidence", "missing evidence"),
    ("empty-evidence", "empty evidence"),
    ("duplicate-evidence", "duplicate evidence"),
    ("orphan-evidence", "orphan evidence"),
    ("no-requirement-link", "requirement link"),
])
def test_spec_rejects_broken_requirement_to_evidence_traceability(
    tmp_path: Path, mutation: str, error: str,
) -> None:
    source = SPEC.read_text()
    evidence = next(line for line in source.splitlines(keepends=True)
                    if line.startswith("- `AC-APP`:"))
    if mutation == "unknown-requirement":
        source = source.replace('covers `FR-FOUNDATION-APP`', 'covers `FR-UNKNOWN`', 1)
    elif mutation == "uncovered-requirement":
        source = source.replace(
            "## Requirements\n", "## Requirements\n\n- `FR-UNCOVERED`: new.\n", 1,
        )
    elif mutation == "missing-evidence-section":
        source = source.replace("## Evidence map", "## Other evidence", 1)
    elif mutation == "missing-evidence":
        source = source.replace(evidence, "", 1)
    elif mutation == "empty-evidence":
        source = source.replace(evidence, "- `AC-APP`: \n", 1)
    elif mutation == "duplicate-evidence":
        source = source.replace(evidence, evidence + evidence, 1)
    elif mutation == "orphan-evidence":
        source = source.replace(evidence, evidence + "- `AC-ORPHAN`: test.\n", 1)
    else:
        source = source.replace('covers `FR-FOUNDATION-APP`', 'covers nothing', 1)
    fixture = tmp_path / "traceability.md"
    fixture.write_text(source)
    result = validate("validate_spec.py", "--spec", fixture)
    assert result.returncode == 1
    assert error in result.stderr
