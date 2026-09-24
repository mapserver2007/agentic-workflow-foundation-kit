#!/usr/bin/env python3
"""agentic-workflow-update の consumer / lock / preimage 契約を検査する。"""
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
FETCH_SCRIPT = ROOT / ".cursor/skills/agentic-workflow-update/bin/kit-source-fetch-safe"
SKILL_FILE = ROOT / ".cursor/skills/agentic-workflow-update/SKILL.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module を読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UPDATE = _load_module(UPDATE_SCRIPT, "test_kit_update_impl")
RUNNER = _load_module(RUNNER_SCRIPT, "test_kit_update_runner")


def _write(root: Path, relative: str, content: str, mode: int | None = None) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def _manifest(outputs: list[tuple[str, str, str | None]]) -> str:
    lines = [
        "version: 1",
        "code_review:",
        "  enabled: true",
        "outputs:",
    ]
    for path, mode, feature in outputs:
        lines.extend(
            [
                f'  - path: "{path}"',
                f'    template: "{path}.template"',
                f"    mode: {mode}",
            ]
        )
        if feature:
            lines.append(f"    feature: {feature}")
    return "\n".join(lines) + "\n"


def _root_manifest(*, code_review: bool = False) -> str:
    return (
        "version: 1\n"
        "project:\n"
        "  quality_gate:\n"
        "    profile: application\n"
        "code_review:\n"
        f"  enabled: {'true' if code_review else 'false'}\n"
    )


def _fixture(
    *,
    outputs: list[tuple[str, str, str | None]] | None = None,
    candidate_updates: dict[str, str] | None = None,
    app_manifest: str | None = None,
) -> tuple[Path, Path, Path, tempfile.TemporaryDirectory[str]]:
    temp = tempfile.TemporaryDirectory(prefix="kit-update-test-")
    base = Path(temp.name)
    app = base / "app"
    clone = base / "clone"
    work = base / "work"
    outputs = outputs or [
        ("AGENTS.md", "render", None),
        ("docs/spec.md", "seed", None),
        (".gitignore", "marker", None),
    ]
    candidate_updates = candidate_updates or {
        "AGENTS.md": "generated-v2\n",
        ".gitignore": "# marker-v2\n",
        "docs/spec.md": "domain-owned\n",
    }

    (app / ".git").mkdir(parents=True)
    _write(app, "manifest.yaml", app_manifest or _root_manifest())
    _write(app, "AGENTS.md", "generated-v1\n")
    _write(app, ".gitignore", "# marker-v1\n")
    _write(app, "docs/spec.md", "domain-owned\n")
    _write(app, "docs/DECISIONS.md", "decision-owned\n")
    _write(app, "docs/GOTCHAS.md", "gotcha-owned\n")
    _write(app, "bin/quality-gate", "#!/usr/bin/env bash\nexit 0\n", 0o755)

    _write(clone, ".cursor/skills/agentic-workflow-foundation/manifest.yaml", _manifest(outputs))
    _write(clone, ".cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py", "")
    shutil.copytree(
        ROOT / ".cursor/skills/agentic-workflow-foundation/scripts",
        clone / ".cursor/skills/agentic-workflow-foundation/scripts",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        ROOT / ".cursor/skills/agentic-workflow-engine/scripts",
        clone / ".cursor/skills/agentic-workflow-engine/scripts",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        ROOT / ".cursor/skills/agentic-workflow-update",
        clone / ".cursor/skills/agentic-workflow-update",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.email", "kit-update-test@example.invalid"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.name", "kit-update-test"], cwd=clone, check=True)
    subprocess.run(["git", "add", "."], cwd=clone, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=clone, check=True)

    _write(work, "manifest.yaml", app_manifest or _root_manifest())
    for relative, content in candidate_updates.items():
        _write(work, relative, content)
    return app, clone, work, temp


def _revision(clone: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _plan(app: Path, clone: Path, work: Path, *, overlay: Path | None = None) -> dict:
    return UPDATE._build_plan(
        app,
        clone,
        work,
        overlay or app / "manifest.yaml",
        validate=False,
        kit_revision=_revision(clone),
    )


def test_public_fetch_contract() -> None:
    content = FETCH_SCRIPT.read_text(encoding="utf-8")
    assert 'https://github.com/mapserver2007/agentic-workflow-foundation-kit.git' in content
    assert "--kit-root" not in content
    assert "--app-root" not in content
    assert "init.yaml" not in content
    assert "_github-auth" not in content
    assert "credential.helper=" in content


def test_consumer_plan_and_apply_exclude_kit_sources() -> None:
    app, clone, work, temp = _fixture()
    try:
        plan = _plan(app, clone, work)
        paths = {item["path"] for item in plan["changes"]}
        assert "AGENTS.md" in paths
        assert ".gitignore" in paths
        assert "agentic-workflow-kit.lock.yaml" in paths
        assert not any(path.startswith(".cursor/skills/agentic-workflow-") for path in paths)
        assert not any(path.startswith(".cursor/docs/AI_") for path in paths)
        assert plan["baseline"] == "adopt"
        assert not plan["blocking_issues"], plan
        UPDATE._validate_plan(plan, app, plan["plan_digest"])
        UPDATE._apply_plan(plan)
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v2\n"
        assert (app / "agentic-workflow-kit.lock.yaml").is_file()
        assert not (app / ".cursor/skills/agentic-workflow-foundation").exists()
        assert not (app / ".cursor/skills/agentic-workflow-engine").exists()
        UPDATE._run_application_validation(app, clone, app / "manifest.yaml")
    finally:
        temp.cleanup()


def test_resolved_catalog_applies_overlay_features() -> None:
    outputs = [
        ("AGENTS.md", "render", None),
        ("optional.md", "render", "code_review"),
    ]
    app, clone, work, temp = _fixture(
        outputs=outputs,
        candidate_updates={"AGENTS.md": "generated-v2\n"},
        app_manifest=_root_manifest(code_review=False),
    )
    try:
        plan = _plan(app, clone, work)
        catalog_paths = {item["path"] for item in plan["catalog"]}
        assert "AGENTS.md" in catalog_paths
        assert "optional.md" not in catalog_paths
    finally:
        temp.cleanup()


def test_initial_adopt_does_not_infer_orphans() -> None:
    app, clone, work, temp = _fixture()
    try:
        _write(app, "legacy-project-owned.md", "keep\n")
        plan = _plan(app, clone, work)
        assert plan["baseline"] == "adopt"
        assert plan["orphan"] == []
        assert "KU-ORPHAN-001" not in plan["blocking_issues"]
    finally:
        temp.cleanup()


def test_lock_catalog_detects_removed_managed_output() -> None:
    app, clone, work, temp = _fixture(
        outputs=[("AGENTS.md", "render", None)],
        candidate_updates={"AGENTS.md": "generated-v2\n"},
    )
    try:
        _write(app, "removed-managed.md", "old\n")
        _write(
            app,
            "agentic-workflow-kit.lock.yaml",
            "version: 1\n"
            f'kit_revision: "{_revision(clone)}"\n'
            "catalog:\n"
            '  - path: "removed-managed.md"\n'
            '    mode: "render"\n'
            f'    sha256: "{UPDATE._sha256(app / "removed-managed.md")}"\n',
        )
        plan = _plan(app, clone, work)
        assert plan["orphan"] == ["removed-managed.md"]
        assert "KU-ORPHAN-001" in plan["blocking_issues"]
    finally:
        temp.cleanup()


def test_overlay_preflight_happens_before_fetch() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-preflight-") as temp_dir:
        app = Path(temp_dir) / "app"
        (app / ".git").mkdir(parents=True)
        called = False

        def fail_fetch(_clone: Path) -> dict:
            nonlocal called
            called = True
            raise AssertionError("fetch が overlay preflight より先に実行された")

        with patch.object(UPDATE, "_fetch_kit", side_effect=fail_fetch):
            result = UPDATE.main(["plan", "--app-root", str(app)])
        assert result == 2
        assert not called


def test_external_overlay_is_copied_to_work_tree() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-overlay-") as temp_dir:
        base = Path(temp_dir)
        app = base / "app"
        work = base / "work"
        overlay = base / "overlay.yaml"
        (app / ".git").mkdir(parents=True)
        _write(app, "AGENTS.md", "owned\n")
        _write(base, "overlay.yaml", _root_manifest())
        UPDATE._prepare_work_tree(app, overlay, work)
        assert (work / "manifest.yaml").read_text(encoding="utf-8") == _root_manifest()


def test_plan_digest_and_preimage_reject_unapproved_apply() -> None:
    app, clone, work, temp = _fixture()
    try:
        plan = _plan(app, clone, work)
        try:
            UPDATE._validate_plan(plan, app, "unapproved")
        except UPDATE.UpdateError as exc:
            assert "KU-PREIMAGE-001" in str(exc)
        else:
            raise AssertionError("未承認 plan が受理された")
        (app / "AGENTS.md").write_text("changed-after-plan\n", encoding="utf-8")
        try:
            UPDATE._apply_plan(plan)
        except UPDATE.UpdateError as exc:
            assert "KU-PREIMAGE-001" in str(exc)
        else:
            raise AssertionError("preimage drift が受理された")
    finally:
        temp.cleanup()


def test_subprocess_error_keeps_exit_and_stderr() -> None:
    try:
        UPDATE._run(
            [sys.executable, "-c", "import sys; print('diagnostic', file=sys.stderr); sys.exit(2)"],
            Path.cwd(),
        )
    except UPDATE.CommandUpdateError as exc:
        assert exc.exit_code == 2
        assert "exit 2" in str(exc)
    else:
        raise AssertionError("subprocess failure が受理された")


def test_candidate_validation_scopes_seed_audit() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-audit-scope-") as temp_dir:
        base = Path(temp_dir)
        clone = base / "clone"
        work = base / "work"
        runner = clone / ".cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py"
        seed = clone / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"
        (runner.parent).mkdir(parents=True)
        seed.parent.mkdir(parents=True, exist_ok=True)
        runner.write_text("", encoding="utf-8")
        seed.write_text("version: 1\n", encoding="utf-8")
        (clone / ".cursor/skills/agentic-workflow-engine").mkdir(parents=True)
        (clone / ".cursor/skills/agentic-workflow-foundation/scripts").mkdir(
            parents=True,
            exist_ok=True,
        )
        (work / "manifest.yaml").parent.mkdir(parents=True)
        (work / "manifest.yaml").write_text("version: 1\n", encoding="utf-8")
        gate = work / "bin/quality-gate"
        gate.parent.mkdir()
        gate.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        calls: list[list[str]] = []

        def record(command: list[str], cwd: Path) -> None:
            calls.append(command)

        with (
            patch.object(UPDATE, "_run", side_effect=record),
            patch.object(
                UPDATE,
                "_load_resolved_manifest",
                return_value={"project": {"quality_gate": {"profile": "application"}}},
            ),
        ):
            result = UPDATE._run_candidate_validation(clone, work)
        assert result["project"]["quality_gate"]["profile"] == "application"
        assert [command[2] for command in calls[:3]] == ["generate", "check", "audit"]
        assert "--skip-seed-required-sections" in calls[2]
        assert all(
            "--skip-seed-required-sections" not in command
            for command in (calls[0], calls[1], calls[3])
        )

        calls.clear()

        def fail_on_audit(command: list[str], cwd: Path) -> None:
            calls.append(command)
            if command[2] == "audit":
                raise UPDATE.CommandUpdateError("audit failed", 1)

        with patch.object(UPDATE, "_run", side_effect=fail_on_audit):
            try:
                UPDATE._run_candidate_validation(clone, work)
            except UPDATE.CommandUpdateError as exc:
                assert exc.exit_code == 1
            else:
                raise AssertionError("audit failure が quality gate へ進行した")
        assert len(calls) == 3


def test_candidate_validation_rehearses_existing_seed() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-rehearsal-") as temp_dir:
        base = Path(temp_dir)
        clone = base / "clone"
        work = base / "work"
        seed_dir = clone / ".cursor/skills/agentic-workflow-foundation"
        seed_dir.mkdir(parents=True)
        _write(
            seed_dir,
            "manifest.yaml",
            """\
version: 1
outputs:
  - path: rendered.md
    template: rendered.template
    mode: render
    required_sections:
      - RENDERED-V2
  - path: managed.txt
    template: managed.template
    mode: marker
    required_sections:
      - MANAGED-V2
  - path: seed.md
    template: seed.template
    mode: seed
    required_sections:
      - KIT-SEED-SECTION
""",
        )
        foundation_scripts = seed_dir / "scripts"
        shutil.copytree(
            ROOT / ".cursor/skills/agentic-workflow-foundation/scripts",
            foundation_scripts,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                "test_worker_contract.py",
                "__pycache__",
                "*.pyc",
            ),
        )
        shutil.copytree(
            ROOT / ".cursor/skills/agentic-workflow-engine/scripts",
            clone / ".cursor/skills/agentic-workflow-engine/scripts",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(
            ROOT / ".cursor/skills/agentic-workflow-foundation/templates",
            seed_dir / "templates",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        _write(
            seed_dir / "templates",
            "rendered.template",
            "RENDERED-V2\n",
        )
        _write(seed_dir / "templates", "managed.template", "MANAGED-V2\n")
        _write(seed_dir / "templates", "seed.template", "KIT-SEED-SECTION\n")
        _write(
            foundation_scripts,
            "run_resolved_engine.py",
            (ROOT / ".cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py").read_text(
                encoding="utf-8"
            ),
        )

        _write(
            work,
            "manifest.yaml",
            """\
version: 1
project:
  quality_gate:
    profile: application
""",
        )
        _write(work, "rendered.md", "RENDERED-V1\n")
        _write(
            work,
            "managed.txt",
            "project-owned\n"
            "# >>> managed managed >>>\n"
            "MANAGED-V1\n"
            "# <<< managed managed <<<\n",
        )
        _write(work, "seed.md", "consumer-owned seed\n")
        gate = work / "bin/quality-gate"
        gate.parent.mkdir(parents=True)
        gate.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        gate.chmod(0o755)

        manifest = UPDATE._run_candidate_validation(clone, work)
        assert manifest["project"]["quality_gate"]["profile"] == "application"
        assert (work / "seed.md").read_text(encoding="utf-8") == "consumer-owned seed\n"
        assert (work / "rendered.md").read_text(encoding="utf-8") == "RENDERED-V2\n"
        assert "MANAGED-V2" in (work / "managed.txt").read_text(encoding="utf-8")


def test_skill_contract_excludes_vendor_flow() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    assert "固定public URL" in content
    assert "並置 kit の `origin`" not in content
    assert "foundation/engine" in content
    assert "agentic-workflow-kit.lock.yaml" in content
    assert "--root-manifest" in content


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
                        "--skip-host-update",
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
        ("public fetch contract", test_public_fetch_contract),
        ("consumer plan and apply", test_consumer_plan_and_apply_exclude_kit_sources),
        ("resolved catalog", test_resolved_catalog_applies_overlay_features),
        ("initial adopt", test_initial_adopt_does_not_infer_orphans),
        ("lock orphan", test_lock_catalog_detects_removed_managed_output),
        ("overlay preflight", test_overlay_preflight_happens_before_fetch),
        ("external overlay", test_external_overlay_is_copied_to_work_tree),
        ("plan digest and preimage", test_plan_digest_and_preimage_reject_unapproved_apply),
        ("subprocess diagnostics", test_subprocess_error_keeps_exit_and_stderr),
        ("candidate validation audit scope", test_candidate_validation_scopes_seed_audit),
        ("candidate validation rehearsal", test_candidate_validation_rehearses_existing_seed),
        ("skill contract", test_skill_contract_excludes_vendor_flow),
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
