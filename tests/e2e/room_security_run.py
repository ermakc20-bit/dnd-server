"""Explicit native F3 acceptance, unique own ports/profile/output; no existing runtime changes."""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile

from run import ready


def port():
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        value = candidate.getsockname()[1]
        if value == 64570:
            raise RuntimeError("reserved user dashboard port")
        return value


def main():
    root = Path(__file__).resolve().parents[2]
    node = shutil.which("node")
    if not node:
        raise RuntimeError("existing Node runtime required")
    db = os.environ.get("VTT_TEST_DATABASE_URL", "")
    redis = os.environ.get("VTT_TEST_REDIS_URL", "")
    if (
        db != "postgresql://postgres@127.0.0.1:55439/vtt_ticket01"
        or redis != "redis://127.0.0.1:56439/15"
    ):
        raise RuntimeError("explicit owned F3 local services required")
    for destination in (db, redis):
        if urlparse(destination).hostname != "127.0.0.1":
            raise RuntimeError("loopback required")
    output = Path(tempfile.mkdtemp(prefix="dnd-f3-native-", dir="/private/tmp")).resolve()
    if any(path.is_symlink() for path in (output, *output.parents)) or any(output.iterdir()):
        raise RuntimeError("fresh non-symlink owned output required")
    (output / ".dnd-acceptance-owned").write_text("DND F3 native acceptance v1\n")
    api_port, web_port = port(), port()
    processes = []
    with tempfile.TemporaryDirectory(prefix="dnd-f3-empty-env-", dir="/private/tmp") as temporary:
        env = {
            key: value for key, value in os.environ.items() if not key.startswith(("VTT_", "VITE_"))
        }
        for name in ("VTT_PLAYWRIGHT_MODULE", "VTT_CHROME_EXECUTABLE"):
            if name in os.environ:
                env[name] = os.environ[name]
        env.update(
            VTT_TEST_DATABASE_URL=db,
            VTT_TEST_REDIS_URL=redis,
            PYTHONPATH=str(root / "backend"),
            VTT_E2E_OUTPUT=str(output),
            VTT_ENVIRONMENT="test",
            VTT_E2E_API_PORT=str(api_port),
            VTT_E2E_WEB_PORT=str(web_port),
            VTT_E2E_ENV_DIR=temporary,
            VTT_E2E_URL=f"http://127.0.0.1:{web_port}",
        )
        try:
            with (
                (output / "api.log").open("wb") as api_log,
                (output / "web.log").open("wb") as web_log,
            ):
                api = subprocess.Popen(  # noqa: S603 - fixed owned loopback fixture
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "room_security_runtime:app",
                        "--app-dir",
                        str(root / "tests/e2e"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
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
                subprocess.run(  # noqa: S603 - fixed native F3 scenario
                    [node, str(root / "frontend/e2e/room-security.cjs")],
                    env=env,
                    cwd=temporary,
                    check=True,
                    timeout=150,
                )
                result = json.loads((output / "room-security-results.json").read_text())
                if result.get("status") != "passed" or result.get("offline_seconds", 0) < 32:
                    raise RuntimeError("native evidence incomplete")
                with ZipFile(output / "campaign.zip") as archive:
                    text = "".join(
                        archive.read(name).decode("utf8")
                        for name in archive.namelist()
                        if name.endswith(".json")
                    )
                    if any(
                        value in text
                        for value in (
                            "connection.opened",
                            "connection.closed",
                            "participant.joined",
                            "socket_closed_actor_",
                        )
                    ):
                        raise RuntimeError("security audit contaminated campaign ZIP")
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
                "fixture_security_events_remaining",
            )
        ):
            raise RuntimeError("exact fixture cleanup incomplete")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "output": str(output),
                    "owned_processes_remaining": 0,
                    "cleanup": cleanup,
                    "native": result,
                    "campaign_zip_security_events": 0,
                }
            )
        )


if __name__ == "__main__":
    main()
