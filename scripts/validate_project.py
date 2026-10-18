from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Annotated, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TextList = Annotated[list[Text], Field(min_length=1)]
NonNegative = Annotated[int, Field(ge=0)]


class ManifestSection(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Project(ManifestSection):
    id: Text
    owners: TextList
    stack: TextList
    risk_class: Literal["low", "medium", "high", "critical"]


class VerifyCommands(ManifestSection):
    focused: TextList
    full: TextList


class Commands(ManifestSection):
    dev: TextList
    build: TextList
    test: TextList
    verify: VerifyCommands
    e2e: TextList
    security: TextList
    release: TextList


class Route(ManifestSection):
    required_gates: TextList
    required_review_lenses: list[Text]


class Routing(ManifestSection):
    trivial: Route
    standard: Route
    complex: Route
    autonomous: Route


class Review(ManifestSection):
    available_lenses: TextList


class Release(ManifestSection):
    environments: TextList
    monitoring: Text
    canary: Text
    rollback: Text


class Autonomy(ManifestSection):
    allowed: bool
    repository_allowlist: list[Text]
    concurrency: Annotated[int, Field(ge=1)]
    turn_limit: NonNegative
    retry_limit: NonNegative
    budget: NonNegative
    commit: bool
    push: bool
    merge: bool
    deploy: bool


class Integrations(ManifestSection):
    guarded: list[Text]


class Secrets(ManifestSection):
    permitted_sources: TextList
    prohibited_outputs: TextList


class ProjectManifest(ManifestSection):
    schema_version: Annotated[int, Field(ge=2, le=2)]
    project: Project
    commands: Commands
    routing: Routing
    review: Review
    release: Release
    autonomy: Autonomy
    integrations: Integrations
    secrets: Secrets

yaml = import_module("yaml")
safe_load = cast(Callable[[str], object], yaml.safe_load)
YAMLError = cast(type[Exception], yaml.YAMLError)


class YAMLNode(Protocol):
    tag: str
    value: object


compose = cast(Callable[[str], YAMLNode | None], yaml.compose)
GATES = {"authority", "context", "readiness", "plan", "build", "verify", "review",
         "release", "learn"}
BASE_GATES = {"authority", "context", "build", "verify", "learn"}


def has_duplicate_keys(node: YAMLNode | None, visited: set[int]) -> bool:
    if node is None or id(node) in visited:
        return False
    visited.add(id(node))
    if node.tag == "tag:yaml.org,2002:map":
        pairs = cast(list[tuple[YAMLNode, YAMLNode]], node.value)
        keys = [str(key.value) for key, _value in pairs]
        if len(keys) != len(set(keys)):
            return True
        return any(has_duplicate_keys(value, visited) for _key, value in pairs)
    if node.tag == "tag:yaml.org,2002:seq":
        return any(has_duplicate_keys(value, visited)
                   for value in cast(list[YAMLNode], node.value))
    return False


def validate_references(manifest: ProjectManifest) -> list[str]:
    errors: list[str] = []
    available = manifest.review.available_lenses
    if len(available) != len(set(available)):
        errors.append("review.available_lenses: duplicate reference")
    for name in ("trivial", "standard", "complex", "autonomous"):
        route = cast(Route, getattr(manifest.routing, name))
        gates, lenses = route.required_gates, route.required_review_lenses
        if (len(gates) != len(set(gates)) or set(gates) - GATES
                or not BASE_GATES <= set(gates) or (lenses and "review" not in gates)):
            errors.append(f"routing.{name}.required_gates: invalid or inconsistent reference")
        if len(lenses) != len(set(lenses)) or set(lenses) - set(available):
            errors.append(f"routing.{name}.required_review_lenses: invalid reference")
    return errors


def validate_manifest(path: Path) -> list[str]:
    try:
        source = path.read_text()
        if has_duplicate_keys(compose(source), set()):
            return ["manifest: duplicate YAML key"]
        document = safe_load(source)
    except (OSError, YAMLError):
        return ["manifest: unreadable or invalid YAML"]
    try:
        manifest = ProjectManifest.model_validate(document)
    except ValidationError as error:
        # Report locations and categories only, never manifest values or secrets.
        return [f"{'.'.join(str(part) for part in item['loc'])}: {item['type']}"
                for item in error.errors(include_input=False)]
    return validate_references(manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the repository project manifest.")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    errors = validate_manifest(args.manifest)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print("Project manifest valid")


if __name__ == "__main__":
    main()
