from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCANNER = Path(__file__).parents[2] / "scripts" / "acceptance_scan.py"


def run_scan(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed local scanner under test
        [sys.executable, str(SCANNER), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def root_fixture(tmp_path: Path) -> Path:
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies=[]\n")
    (tmp_path / "frontend" / "package-lock.json").write_text('{"packages":{}}')
    (tmp_path / "frontend" / "dist" / "app.js").write_text("const publicTitle = 'Table';")
    return tmp_path


def test_scanner_rejects_secret_canary_without_echoing_it(tmp_path):
    root = root_fixture(tmp_path)
    canary = "sb_" + "secret_" + "syntheticCanary" * 3
    (root / "frontend" / "dist" / "app.js").write_text(f"window.leak = '{canary}'")
    result = run_scan(root)
    assert result.returncode == 1
    assert "server_secret" in result.stdout
    assert canary not in result.stdout + result.stderr


def test_scanner_missing_build_is_error_not_clean(tmp_path):
    result = run_scan(tmp_path)
    assert result.returncode == 2
    assert "scanner_error" in result.stdout


def test_scanner_rejects_server_config_in_frontend(tmp_path):
    root = root_fixture(tmp_path)
    (root / "frontend" / "src" / "bad.ts").write_text("const key = 'VTT_DATABASE_URL';")
    result = run_scan(root)
    assert result.returncode == 1
    assert "server_config" in result.stdout


def test_scanner_rejects_ai_dependency_and_network(tmp_path):
    root = root_fixture(tmp_path)
    (root / "pyproject.toml").write_text('[project]\ndependencies=["openai>=1"]\n')
    (root / "frontend" / "src" / "bad.ts").write_text('fetch("https://api.anthropic.com/v1");')
    result = run_scan(root)
    assert result.returncode == 1
    assert "ai_dependency" in result.stdout and "ai_network" in result.stdout


def test_scanner_clean_source_and_build_pass_without_git(tmp_path):
    assert run_scan(root_fixture(tmp_path)).returncode == 0


def test_scanner_does_not_skip_nul_text_build_canary(tmp_path):
    root = root_fixture(tmp_path)
    canary = "sb_" + "secret_" + "nulCanary" * 4
    (root / "frontend" / "dist" / "app.js").write_bytes(
        b"/* comment \x00 */\nwindow.leak = '" + canary.encode() + b"';"
    )
    result = run_scan(root)
    assert result.returncode in {1, 2}
    assert '"status": "passed"' not in result.stdout
    assert canary not in result.stdout + result.stderr


def test_scanner_does_not_skip_nul_text_log_canary(tmp_path):
    root = root_fixture(tmp_path)
    canary = "sb_" + "secret_" + "logCanary" * 4
    log = tmp_path / "acceptance.log"
    log.write_bytes(b"diagnostic\x00 " + canary.encode())
    result = subprocess.run(  # noqa: S603 - fixed local scanner under test
        [sys.executable, str(SCANNER), "--root", str(root), "--log", str(log)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in {1, 2}
    assert '"status": "passed"' not in result.stdout
    assert canary not in result.stdout + result.stderr


def test_scanner_keeps_genuine_binary_png_control(tmp_path):
    from PIL import Image

    root = root_fixture(tmp_path)
    Image.new("RGB", (2, 2), (20, 30, 40)).save(root / "frontend" / "dist" / "map.png")
    assert run_scan(root).returncode == 0
