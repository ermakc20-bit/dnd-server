"""Explicit native acceptance entry; does not activate any development prototype."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen


def ready(url: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError("owned fixture stopped before readiness")
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310 - fixed loopback URL
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.1)
    raise RuntimeError("fixture readiness timeout")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--browser-only", action="store_true")
    modes.add_argument("--load-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("existing Node runtime required")
    for name in ("VTT_TEST_DATABASE_URL", "VTT_TEST_REDIS_URL"):
        value = os.environ.get(name, "")
        if urlparse(value).hostname not in {"localhost", "127.0.0.1"}:
            raise RuntimeError("explicit local PostgreSQL/Redis services required; no skips")
    with tempfile.TemporaryDirectory(
        prefix="dnd-acceptance-", dir=Path(tempfile.gettempdir()).resolve()
    ) as temporary:
        output = Path(os.environ.get("VTT_E2E_OUTPUT", temporary))
        if not output.is_absolute() or ".." in output.parts:
            raise RuntimeError("absolute owned temporary output directory required")
        if any(path.is_symlink() for path in (output, *output.parents)):
            raise RuntimeError("symlink output route is forbidden")
        output.mkdir(parents=True, exist_ok=True)
        if any(path.is_symlink() for path in output.rglob("*")):
            raise RuntimeError("symlink output descendant is forbidden")
        marker = output / ".dnd-acceptance-owned"
        if any(output.iterdir()) and not marker.is_file():
            raise RuntimeError("existing output directory is not owned by acceptance")
        marker.write_text("DND native acceptance v1\n")
        for filename in ("results.json", "load-results.json", "cleanup.json", "failure.json"):
            (output / filename).unlink(missing_ok=True)
        env = {
            key: value for key, value in os.environ.items() if not key.startswith(("VTT_", "VITE_"))
        }
        for name in (
            "VTT_TEST_DATABASE_URL",
            "VTT_TEST_REDIS_URL",
            "VTT_PLAYWRIGHT_MODULE",
            "VTT_CHROME_EXECUTABLE",
            "VTT_E2E_API_PORT",
            "VTT_E2E_WEB_PORT",
        ):
            if name in os.environ:
                env[name] = os.environ[name]
        api_port = env.setdefault("VTT_E2E_API_PORT", "18010")
        web_port = env.setdefault("VTT_E2E_WEB_PORT", "5190")
        env.update(
            PYTHONPATH=str(root / "backend"),
            VTT_E2E_OUTPUT=str(output),
            VTT_E2E_URL=f"http://127.0.0.1:{web_port}",
            VTT_ENVIRONMENT="test",
            VTT_E2E_ENV_DIR=temporary,
        )
        processes: list[subprocess.Popen[bytes]] = []
        try:
            with (
                (output / "api.log").open("wb") as api_log,
                (output / "web.log").open("wb") as web_log,
            ):
                api = subprocess.Popen(  # noqa: S603 - fixed local owned fixture
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "runtime:app",
                        "--app-dir",
                        str(root / "tests/e2e"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        api_port,
                        "--no-access-log",
                    ],
                    cwd=temporary,
                    env=env,
                    stdout=api_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(api)
                ready(f"http://127.0.0.1:{api_port}/health/live", api)
                web = subprocess.Popen(  # noqa: S603 - existing pinned local Vite
                    [
                        node,
                        str(root / "frontend/node_modules/vite/bin/vite.js"),
                        "--config",
                        str(root / "tests/e2e/vite.config.mjs"),
                    ],
                    cwd=temporary,
                    env=env,
                    stdout=web_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(web)
                ready(f"http://127.0.0.1:{web_port}/__e2e/bootstrap", web)
                paths = []
                if not args.load_only:
                    paths.append(root / "tests/e2e/browser.cjs")
                if not args.browser_only:
                    paths.append(root / "tests/load/room-smoke.cjs")
                if not paths:
                    raise RuntimeError("acceptance requires at least one scenario")
                for path in paths:
                    subprocess.run(  # noqa: S603 - fixed local acceptance module
                        [node, str(path)],
                        env=env,
                        cwd=temporary,
                        check=True,
                        timeout=180,
                    )
                    filename, key = (
                        ("results.json", "native_paths")
                        if path.name == "browser.cjs"
                        else ("load-results.json", "cases")
                    )
                    evidence = json.loads((output / filename).read_text())
                    if evidence.get("status") != "passed" or not evidence.get(key):
                        raise RuntimeError("selected acceptance scenario did not produce evidence")
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        cleanup = json.loads((output / "cleanup.json").read_text())
        if any(
            cleanup[key] != 0
            for key in (
                "fixture_users_remaining",
                "fixture_campaigns_remaining",
                "fixture_jobs_remaining",
            )
        ):
            raise RuntimeError("exact fixture cleanup incomplete")
        print(json.dumps({"status": "passed", "owned_processes_remaining": 0, "cleanup": cleanup}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "acceptance_error", "reason": type(error).__name__}))
        raise SystemExit(2) from None
