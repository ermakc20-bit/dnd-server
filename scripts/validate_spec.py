from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

REQUIREMENT_ID = r"(?:FR|NFR)-[A-Z0-9]+(?:-[A-Z0-9]+)*"
AC_ID = r"AC-[A-Z0-9]+(?:-[A-Z0-9]+)*"


def section(source: str, title: str) -> tuple[str, list[str]]:
    headers = list(re.finditer(r"^##\s+([^\n]+)$", source, re.MULTILINE))
    positions = [index for index, header in enumerate(headers) if header[1].strip() == title]
    if len(positions) != 1:
        return "", [f"{title}: expected exactly one section"]
    index = positions[0]
    end = headers[index + 1].start() if index + 1 < len(headers) else len(source)
    return source[headers[index].end():end], []


def declarations(body: str, pattern: str, label: str) -> tuple[list[str], list[str]]:
    lines = [line.strip() for line in body.splitlines() if line.strip().startswith("-")]
    matches = [re.fullmatch(pattern, line) for line in lines]
    errors = [f"{label}: empty or malformed declaration"] if not lines or not all(matches) else []
    identifiers = [match[1] for match in matches if match is not None]
    if any(count > 1 for count in Counter(identifiers).values()):
        errors.append(f"duplicate {label.lower()}")
    return identifiers, errors


def validate_spec(path: Path) -> list[str]:
    try:
        source = path.read_text()
    except OSError:
        return ["spec: unreadable document"]
    requirements, errors = section(source, "Requirements")
    acceptance, acceptance_errors = section(source, "Acceptance criteria")
    errors.extend(acceptance_errors)
    requirement_ids, requirement_errors = declarations(
        requirements, rf"- `({REQUIREMENT_ID})`: .+", "Requirements",
    )
    acceptance_ids, declaration_errors = declarations(
        acceptance, rf"- \[[ xX]\] `({AC_ID})` covers .+: .+", "Acceptance criteria",
    )
    errors.extend(requirement_errors)
    errors.extend(declaration_errors)
    covered: set[str] = set()
    for match in re.finditer(
        rf"^- \[[ xX]\] `({AC_ID})` covers (.+?): .+$", acceptance, re.MULTILINE,
    ):
        references = re.findall(r"`([^`]+)`", match[2])
        if not references or any(not re.fullmatch(REQUIREMENT_ID, item) for item in references):
            errors.append(f"{match[1]}: invalid requirement link")
        if set(references) - set(requirement_ids):
            errors.append(f"{match[1]}: unknown requirement")
        covered.update(references)
    if set(requirement_ids) - covered:
        errors.append("Requirements: uncovered requirement")
    evidence_body, evidence_errors = section(source, "Evidence map")
    errors.extend(evidence_errors)
    evidence_ids: list[str] = []
    for line in evidence_body.splitlines():
        if not line.strip().startswith("-"):
            continue
        evidence = re.fullmatch(rf"- `({AC_ID})`:[ \t]*(.*)", line.strip())
        if evidence is None:
            errors.append("Evidence map: malformed evidence")
            continue
        evidence_ids.append(evidence[1])
        if not evidence[2].strip():
            errors.append(f"{evidence[1]}: empty evidence")
    if any(count > 1 for count in Counter(evidence_ids).values()):
        errors.append("Evidence map: duplicate evidence")
    if set(acceptance_ids) - set(evidence_ids):
        errors.append("Evidence map: missing evidence")
    if set(evidence_ids) - set(acceptance_ids):
        errors.append("Evidence map: orphan evidence")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate requirement-to-evidence traceability.")
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    errors = validate_spec(args.spec)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print("Spec traceability valid")


if __name__ == "__main__":
    main()
