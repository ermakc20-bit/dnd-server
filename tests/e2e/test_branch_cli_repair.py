"""Public CLI/config regressions use disposable env and never real credentials."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


def test_conflicting_acceptance_modes_fail_before_any_fixture_start(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "branch_acceptance_runner", ROOT / "tests/e2e/run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["run.py", "--browser-only", "--load-only"])
    monkeypatch.setenv(
        "VTT_TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:55439/vtt_ticket01"
    )
    monkeypatch.setenv("VTT_TEST_REDIS_URL", "redis://127.0.0.1:56439/15")
    monkeypatch.setenv("VTT_E2E_OUTPUT", str(tmp_path / "owned-output"))
    starts = []

    def fail_start(*args, **kwargs):
        starts.append(args)
        raise AssertionError("conflicting modes must be rejected before fixture startup")

    monkeypatch.setattr(module.subprocess, "Popen", fail_start)
    with pytest.raises(SystemExit) as rejected:
        module.main()
    assert rejected.value.code == 2
    assert starts == []


def test_root_only_env_supplies_public_vite_values_without_server_canary(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    shutil.copyfile(ROOT / "frontend/vite.config.ts", frontend / "vite.config.ts")
    (frontend / "node_modules").symlink_to(
        (ROOT / "frontend/node_modules").resolve(), target_is_directory=True
    )
    (frontend / "package.json").write_text('{"type":"module"}')
    (frontend / "index.html").write_text('<script type="module" src="/main.ts"></script>')
    (frontend / "main.ts").write_text("window.fixtureEnvironment = import.meta.env;")
    public = {
        "VITE_SUPABASE_URL": "https://public-fixture.invalid",
        "VITE_SUPABASE_PUBLISHABLE_KEY": "public-fixture-value",
        "VITE_API_BASE_URL": "http://127.0.0.1:8000",
    }
    canary = "synthetic_backend_canary_value"
    (tmp_path / ".env").write_text(
        "\n".join(f"{k}={v}" for k, v in public.items()) + "\nVTT_PRIVATE_FIXTURE=" + canary
    )
    vite = (ROOT / "frontend/node_modules/vite/dist/node/index.js").resolve()
    code = f"""import {{build}} from {json.dumps(str(vite))};
const result = await build({{root:{json.dumps(str(frontend))},
configFile:{json.dumps(str(frontend / "vite.config.ts"))},
logLevel:'silent',build:{{write:false}}}});
console.log(JSON.stringify(result.output.filter(entry=>entry.type==='chunk').map(entry=>entry.code)));
"""
    environment = {k: v for k, v in os.environ.items() if not k.startswith(("VITE_", "VTT_"))}
    result = subprocess.run(  # noqa: S603 - existing local Vite, synthetic disposable env
        [shutil.which("node"), "--input-type=module", "--eval", code],
        cwd=frontend,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    bundle = json.loads(result.stdout)
    assert all(value in str(bundle) for value in public.values())
    assert canary not in str(bundle)


@pytest.mark.parametrize("mode", ["--browser-only", "--load-only", None])
@pytest.mark.parametrize("evidence", ["valid", "missing", "empty"])
def test_successful_cli_modes_require_nonempty_selected_scenario_evidence(
    monkeypatch, tmp_path, mode, evidence
):
    spec = importlib.util.spec_from_file_location(
        "scenario_acceptance_runner", ROOT / "tests/e2e/run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["run.py", *([mode] if mode else [])])
    monkeypatch.setenv(
        "VTT_TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:55439/vtt_ticket01"
    )
    monkeypatch.setenv("VTT_TEST_REDIS_URL", "redis://127.0.0.1:56439/15")
    monkeypatch.setenv("VTT_E2E_OUTPUT", str(tmp_path / "output"))

    class OwnedProcess:
        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: OwnedProcess())
    monkeypatch.setattr(module, "ready", lambda *args: None)
    calls = []

    def scenario(args, *, env, **kwargs):
        calls.append(Path(args[1]).name)
        output = Path(env["VTT_E2E_OUTPUT"])
        (output / "cleanup.json").write_text(
            json.dumps(
                {
                    "fixture_users_remaining": 0,
                    "fixture_campaigns_remaining": 0,
                    "fixture_jobs_remaining": 0,
                }
            )
        )
        if evidence != "missing":
            name, key = (
                ("results.json", "native_paths")
                if calls[-1] == "browser.cjs"
                else ("load-results.json", "cases")
            )
            (output / name).write_text(
                json.dumps({"status": "passed", key: ["scenario"] if evidence == "valid" else []})
            )

    monkeypatch.setattr(module.subprocess, "run", scenario)
    if evidence == "valid":
        module.main()
        expected = (
            ["browser.cjs"]
            if mode == "--browser-only"
            else ["room-smoke.cjs"]
            if mode == "--load-only"
            else ["browser.cjs", "room-smoke.cjs"]
        )
        assert calls == expected
    else:
        with pytest.raises((RuntimeError, FileNotFoundError)):
            module.main()
