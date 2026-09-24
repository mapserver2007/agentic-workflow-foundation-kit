#!/usr/bin/env python3
"""agentic-workflow-update の allowlist / preimage / host 配置契約を検査する。"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
UPDATE_SCRIPT = ROOT / ".cursor/skills/agentic-workflow-update/scripts/kit_update.py"
RUNNER_SCRIPT = HERE / "run_resolved_engine.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module を読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UPDATE = _load_module(UPDATE_SCRIPT, "test_kit_update_impl")
RUNNER = _load_module(RUNNER_SCRIPT, "test_kit_update_runner")


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _manifest(outputs: list[tuple[str, str]]) -> str:
    lines = ["version: 1", "outputs:"]
    for path, mode in outputs:
        lines.extend(
            [
                f"  - path: {path}",
                f"    template: {path}.template",
                f"    mode: {mode}",
            ]
        )
    return "\n".join(lines) + "\n"


def _fixture(
    *,
    outputs: list[tuple[str, str]] | None = None,
    candidate_updates: dict[str, str] | None = None,
) -> tuple[Path, Path, Path, tempfile.TemporaryDirectory[str]]:
    temp = tempfile.TemporaryDirectory(prefix="kit-update-test-")
    base = Path(temp.name)
    app = base / "app"
    clone = base / "clone"
    work = base / "work"
    outputs = outputs or [
        ("AGENTS.md", "render"),
        ("docs/spec.md", "seed"),
        (".gitignore", "marker"),
    ]
    candidate_updates = candidate_updates or {
        "AGENTS.md": "generated-v2\n",
        ".gitignore": "# marker-v2\n",
        "docs/spec.md": "domain-owned\n",
    }

    (app / ".git").mkdir(parents=True)
    _write(app, "manifest.yaml", "version: 1\nproject:\n  name: fixture\n")
    _write(app, ".cursor/skills/agentic-workflow-foundation/manifest.yaml", _manifest(outputs))
    _write(app, ".cursor/skills/agentic-workflow-foundation/source.py", "old-source\n")
    _write(app, ".cursor/skills/agentic-workflow-engine/scripts/engine.py", "old-engine\n")
    _write(app, ".cursor/docs/AI_AGENT_UNIFIED_DESIGN.md", "old-agent-design\n")
    _write(app, ".cursor/docs/AI_BUSINESS_AGENT_SUITE.md", "old-business-design\n")
    _write(app, "AGENTS.md", "generated-v1\n")
    _write(app, ".gitignore", "# marker-v1\n")
    _write(app, "docs/spec.md", "domain-owned\n")
    _write(app, "docs/DECISIONS.md", "decision-owned\n")
    _write(app, "docs/GOTCHAS.md", "gotcha-owned\n")

    _write(clone, ".cursor/skills/agentic-workflow-foundation/manifest.yaml", _manifest(outputs))
    _write(clone, ".cursor/skills/agentic-workflow-foundation/source.py", "new-source\n")
    _write(clone, ".cursor/skills/agentic-workflow-foundation/new.py", "new-file\n")
    _write(clone, ".cursor/skills/agentic-workflow-engine/scripts/engine.py", "new-engine\n")
    _write(clone, ".cursor/docs/AI_AGENT_UNIFIED_DESIGN.md", "new-agent-design\n")
    _write(clone, ".cursor/docs/AI_BUSINESS_AGENT_SUITE.md", "new-business-design\n")
    engine_source = ROOT / ".cursor/skills/agentic-workflow-engine/scripts/genlib.py"
    target_engine = clone / ".cursor/skills/agentic-workflow-engine/scripts/genlib.py"
    target_engine.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(engine_source, target_engine)
    shutil.copytree(
        ROOT / ".cursor/skills/agentic-workflow-update",
        clone / ".cursor/skills/agentic-workflow-update",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.email", "kit-update-test@example.invalid"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.name", "kit-update-test"], cwd=clone, check=True)
    subprocess.run(["git", "add", "."], cwd=clone, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"],
        cwd=clone,
        check=True,
    )

    for relative, content in candidate_updates.items():
        _write(work, relative, content)
    return app, clone, work, temp


def _plan(app: Path, clone: Path, work: Path, *, outputs=None) -> dict:
    return UPDATE._build_plan(
        app,
        clone,
        work,
        validate=False,
        kit_revision=subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
    )


def test_allowlist_and_protection() -> None:
    app, clone, work, temp = _fixture()
    try:
        _write(work, "src/app.py", "application-code\n")
        plan = _plan(app, clone, work)
        paths = {item["path"] for item in plan["changes"]}
        assert ".cursor/skills/agentic-workflow-foundation/new.py" in paths
        assert "AGENTS.md" in paths
        assert ".gitignore" in paths
        assert "src/app.py" not in paths
        assert "docs/spec.md" not in paths
        assert "docs/DECISIONS.md" not in paths
        assert not plan["blocking_issues"], plan
        UPDATE._apply_plan(plan)
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v2\n"
        assert (app / ".cursor/skills/agentic-workflow-foundation/new.py").is_file()
        assert (app / "docs/spec.md").read_text(encoding="utf-8") == "domain-owned\n"
    finally:
        temp.cleanup()


def test_seed_denylist_and_orphan_are_blocking() -> None:
    app, clone, work, temp = _fixture(
        outputs=[
            ("AGENTS.md", "render"),
            ("docs/spec.md", "seed"),
            ("docs/DECISIONS.md", "render"),
        ],
        candidate_updates={
            "AGENTS.md": "generated-v2\n",
            "docs/spec.md": "domain-changed\n",
            "docs/DECISIONS.md": "decision-candidate\n",
        },
    )
    try:
        plan = _plan(app, clone, work)
        assert "KU-SEED-001" in plan["blocking_issues"]
        assert "KU-DENY-001" in plan["blocking_issues"]

        orphan_outputs = [("AGENTS.md", "render")]
        app2, clone2, work2, temp2 = _fixture(outputs=orphan_outputs)
        try:
            _write(app2, "removed-render.md", "old\n")
            _write(
                app2,
                ".cursor/skills/agentic-workflow-foundation/manifest.yaml",
                _manifest([("removed-render.md", "render")]),
            )
            _write(clone2, ".cursor/skills/agentic-workflow-foundation/manifest.yaml", _manifest([]))
            orphan_plan = _plan(app2, clone2, work2)
            assert "KU-ORPHAN-001" in orphan_plan["blocking_issues"]
            assert orphan_plan["orphan"] == ["removed-render.md"]
        finally:
            temp2.cleanup()
    finally:
        temp.cleanup()


def test_digest_preimage_and_atomic_rollback() -> None:
    app, clone, work, temp = _fixture()
    try:
        plan = _plan(app, clone, work)
        UPDATE._validate_plan(plan, app, plan["plan_digest"])
        tampered = json.loads(json.dumps(plan))
        tampered["kit_revision"] = "tampered"
        try:
            UPDATE._validate_plan(tampered, app, plan["plan_digest"])
        except UPDATE.UpdateError as exc:
            assert "KU-PREIMAGE-001" in str(exc)
        else:
            raise AssertionError("tampered plan was accepted")

        (app / "AGENTS.md").write_text("changed-after-approval\n", encoding="utf-8")
        try:
            UPDATE._apply_plan(plan)
        except UPDATE.UpdateError as exc:
            assert "KU-PREIMAGE-001" in str(exc)
        else:
            raise AssertionError("preimage drift was accepted")
        assert not (app / ".cursor/skills/agentic-workflow-foundation/new.py").exists()
        assert (app / ".cursor/skills/agentic-workflow-foundation/source.py").read_text(
            encoding="utf-8"
        ) == "old-source\n"
    finally:
        temp.cleanup()


def test_host_install_and_check_do_not_update_host() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-host-") as temp_dir:
        host = Path(temp_dir)
        assert RUNNER._install_update_skill(str(host)) == 0
        destination = host / "agentic-workflow-update"
        assert (destination / "SKILL.md").is_file()
        before = {
            path.relative_to(destination): path.read_bytes()
            for path in destination.rglob("*")
            if path.is_file()
        }
        with patch.object(RUNNER, "run_engine", return_value=0):
            assert (
                RUNNER.main(
                    [
                        "check",
                        "--seed-manifest",
                        str(ROOT / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"),
                        "--root-manifest",
                        str(ROOT / "manifest.yaml"),
                        "--work-root",
                        str(host / "candidate"),
                    ]
                )
                == 0
            )
        after = {
            path.relative_to(destination): path.read_bytes()
            for path in destination.rglob("*")
            if path.is_file()
        }
        assert before == after

    app, clone, work, temp = _fixture()
    try:
        with tempfile.TemporaryDirectory(prefix="kit-update-apply-host-") as host_dir:
            with patch.dict(os.environ, {"AGENTIC_WORKFLOW_UPDATE_HOME": host_dir}):
                assert UPDATE._install_host_updater(clone) == 0
            assert (Path(host_dir) / "agentic-workflow-update/SKILL.md").is_file()
    finally:
        temp.cleanup()


def test_generate_host_flags() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-generate-") as temp_dir:
        base = Path(temp_dir)
        host = base / "host"
        candidate = base / "candidate"
        arguments = [
            "generate",
            "--seed-manifest",
            str(ROOT / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"),
            "--root-manifest",
            str(ROOT / "manifest.yaml"),
            "--work-root",
            str(candidate),
            "--update-skill-home",
            str(host),
        ]
        with patch.object(RUNNER, "run_engine", return_value=0):
            assert RUNNER.main(arguments) == 0
        assert (host / "agentic-workflow-update/SKILL.md").is_file()

        skipped_host = base / "skipped-host"
        skip_arguments = [
            "generate",
            "--seed-manifest",
            str(ROOT / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"),
            "--root-manifest",
            str(ROOT / "manifest.yaml"),
            "--work-root",
            str(base / "candidate-skipped"),
            "--skip-host-update",
        ]
        with (
            patch.object(RUNNER, "run_engine", return_value=0),
            patch.object(
                RUNNER,
                "_install_update_skill",
                side_effect=AssertionError("skip-host-update が配置を呼び出した"),
            ),
        ):
            assert RUNNER.main(skip_arguments) == 0
        assert not skipped_host.exists()


def main() -> int:
    tests = (
        ("allowlist and protection", test_allowlist_and_protection),
        ("seed denylist and orphan", test_seed_denylist_and_orphan_are_blocking),
        ("digest preimage rollback", test_digest_preimage_and_atomic_rollback),
        ("host install and check", test_host_install_and_check_do_not_update_host),
        ("generate host flags", test_generate_host_flags),
    )
    for label, test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            print(f"[test_kit_update] FAIL: {label}: {exc}", file=sys.stderr)
            return 1
        print(f"[test_kit_update] PASS: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
