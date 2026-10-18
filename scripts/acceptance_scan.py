"""Bounded source/build checks; exit 1 is a finding, exit 2 is an incomplete scan."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from importlib.metadata import distributions
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024
MAX_FILES = 10000
BINARY_IMAGES = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".avif": "AVIF"}
AI_PACKAGES = {
    "openai",
    "anthropic",
    "google-genai",
    "google-generativeai",
    "langchain",
    "langchain-openai",
    "litellm",
    "llama-index",
    "cohere",
    "mistralai",
}
PATTERNS = {
    "server_secret": re.compile(r"sb_secret_[A-Za-z0-9_-]{20,}"),
    "private_key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "bearer_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\."),
    "ai_network": re.compile(
        r"(?:api\.openai\.com|api\.anthropic\.com|"
        r"generativelanguage\.googleapis\.com|api\.mistral\.ai)"
    ),
}
SERVER_CONFIG = re.compile(
    r"VTT_(?:DATABASE_URL|REDIS_URL|SUPABASE_SERVICE_ROLE_KEY)|"
    r"VITE_[A-Z0-9_]*(?:SERVICE_ROLE|SECRET_KEY|PRIVATE_KEY)"
)


def scan(root: Path, logs: list[Path]) -> dict[str, Any]:
    build = root / "frontend" / "dist"
    if not build.is_dir() or not any(build.rglob("*.js")):
        raise ValueError("frontend build missing")
    paths: list[Path] = []
    for directory in (
        root / "backend",
        root / "frontend" / "src",
        root / "scripts",
        root / "supabase",
        root / ".github",
        build,
    ):
        if directory.is_dir():
            paths.extend(
                p
                for p in directory.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
            )
    paths.extend(
        p
        for p in (
            root / "pyproject.toml",
            root / "frontend" / "package.json",
            root / "frontend" / "package-lock.json",
            root / "Makefile",
        )
        if p.is_file()
    )
    paths.extend(logs)
    findings: list[dict[str, Any]] = []
    total = 0
    files = sorted(set(paths))
    if len(files) > MAX_FILES:
        raise ValueError("file count bound exceeded")
    for path in files:
        if path.is_symlink() or any(part.startswith(".env") for part in path.parts):
            raise ValueError("unsupported source path")
        size = path.stat().st_size
        total += size
        if size > MAX_FILE or total > MAX_TOTAL:
            raise ValueError("byte bound exceeded")
        data = path.read_bytes()
        if path.suffix.lower() in BINARY_IMAGES:
            try:
                with Image.open(BytesIO(data)) as asset:
                    if asset.format != BINARY_IMAGES[path.suffix.lower()]:
                        raise ValueError("binary image format mismatch")
                    asset.verify()
            except (UnidentifiedImageError, Image.DecompressionBombError) as error:
                raise ValueError("invalid binary image") from error
            continue
        source = data.decode("utf-8", errors="strict")
        categories = dict(PATTERNS)
        if path.is_relative_to(root / "frontend"):
            categories["server_config"] = SERVER_CONFIG
        for kind, pattern in categories.items():
            for match in pattern.finditer(source):
                findings.append(
                    {
                        "kind": kind,
                        "path": path.relative_to(root).as_posix()
                        if path.is_relative_to(root)
                        else "acceptance-log",
                        "line": source.count("\n", 0, match.start()) + 1,
                    }
                )
    project = tomllib.loads((root / "pyproject.toml").read_text())
    dependencies = project.get("project", {}).get("dependencies", [])
    packages = json.loads((root / "frontend" / "package-lock.json").read_text())["packages"]
    names = {re.split(r"[\[<>=!~; ]", entry.lower())[0] for entry in dependencies}
    names.update(d.metadata["Name"].lower().replace("_", "-") for d in distributions())
    names.update(name.rsplit("node_modules/", 1)[-1] for name in packages if name)
    for name in sorted(names & AI_PACKAGES):
        findings.append({"kind": "ai_dependency", "package": name})
    return {
        "status": "failed" if findings else "passed",
        "files": len(files),
        "bytes": total,
        "findings": findings,
        "scope": "bounded patterns/dependency graph; runtime privacy uses canary assertions",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--log", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        result = scan(args.root.resolve(), args.log)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "scanner_error", "reason": type(error).__name__}))
        raise SystemExit(2) from None
    print(json.dumps(result))
    sys.exit(1 if result["findings"] else 0)


if __name__ == "__main__":
    main()
