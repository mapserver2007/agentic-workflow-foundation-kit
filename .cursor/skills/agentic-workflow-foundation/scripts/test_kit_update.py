#!/usr/bin/env python3
"""agentic-workflow-update の consumer / lock / preimage 契約を検査する。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
UPDATE_SCRIPT = ROOT / ".cursor/skills/agentic-workflow-update/scripts/kit_update.py"
RUNNER_SCRIPT = HERE / "run_resolved_engine.py"
FETCH_SCRIPT = ROOT / ".cursor/skills/agentic-workflow-update/bin/kit-source-fetch-safe"
SKILL_FILE = ROOT / ".cursor/skills/agentic-workflow-update/SKILL.md"
README_FILE = ROOT / "README.md"


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


def _worker_contract_fixture(base: Path) -> tuple[Path, Path]:
    """clone 側に worker test/fixture、work 側に生成済み gate を用意する。"""
    clone_skill = (
        base
        / "clone"
        / ".cursor"
        / "skills"
        / "agentic-workflow-foundation"
    )
    clone_scripts = clone_skill / "scripts"
    clone_scripts.mkdir(parents=True)
    shutil.copytree(
        ROOT / ".cursor/skills/agentic-workflow-foundation/scripts",
        clone_scripts,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        ROOT / ".cursor/skills/agentic-workflow-foundation/fixtures",
        clone_skill / "fixtures",
    )

    work_root = base / "work"
    work_root.mkdir()
    step_templates = (
        ROOT
        / ".cursor"
        / "skills"
        / "agentic-workflow-foundation"
        / "templates"
        / "docs"
        / "agent-tasks"
        / "agent-workflow"
    )
    step_docs = work_root / "docs/agent-tasks/agent-workflow"
    step_docs.mkdir(parents=True)
    for index, name in enumerate(
        ("investigation", "report-creation", "implementation", "testing"),
        start=1,
    ):
        source = step_templates / f"{index:02d}-{name}.md.template"
        (step_docs / f"{index:02d}-{name}.md").write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return clone_scripts, work_root


def _install_worker_gate(work_root: Path) -> Path:
    gate = work_root / ".cursor/skills/session-handover/scripts/gate-artifact.py"
    gate.parent.mkdir(parents=True)
    template = (
        ROOT
        / ".cursor"
        / "skills"
        / "agentic-workflow-foundation"
        / "templates"
        / "skills"
        / "session-handover"
        / "scripts"
        / "gate-artifact.py.template"
    )
    gate.write_text(
        template.read_text(encoding="utf-8").replace(
            "{{agent_workflow.artifact.envelope.parser_missing_exit}}",
            "2",
        ),
        encoding="utf-8",
    )
    return gate


def _plan(
    app: Path,
    clone: Path,
    work: Path,
    *,
    overlay: Path | None = None,
    retirement: str | None = None,
) -> dict:
    return UPDATE._build_plan(
        app,
        clone,
        work,
        overlay or app / "manifest.yaml",
        validate=False,
        kit_revision=_revision(clone),
        retirement=retirement,
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
        assert ".cursor/agentic-workflow-update.lock.yaml" in paths
        assert not any(path.startswith(".cursor/skills/agentic-workflow-") for path in paths)
        assert not any(path.startswith(".cursor/docs/AI_") for path in paths)
        assert plan["baseline"] == "adopt"
        assert not plan["blocking_issues"], plan
        UPDATE._validate_plan(plan, app, plan["plan_digest"])
        UPDATE._apply_plan(plan)
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v2\n"
        assert (app / ".cursor/agentic-workflow-update.lock.yaml").is_file()
        assert not (app / ".cursor/skills/agentic-workflow-foundation").exists()
        assert not (app / ".cursor/skills/agentic-workflow-engine").exists()
        UPDATE._run_application_validation(app, clone, app / "manifest.yaml")
    finally:
        temp.cleanup()


def test_plan_creates_lock_when_cursor_directory_is_absent() -> None:
    app, clone, work, temp = _fixture()
    try:
        cursor = work / ".cursor"
        if cursor.exists():
            shutil.rmtree(cursor)
        assert not cursor.exists()
        plan = _plan(app, clone, work)
        lock = ".cursor/agentic-workflow-update.lock.yaml"
        assert (work / lock).is_file()
        assert lock in {item["path"] for item in plan["changes"]}
        assert not plan["blocking_issues"], plan
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
            ".cursor/agentic-workflow-update.lock.yaml",
            "version: 1\n"
            f'kit_revision: "{_revision(clone)}"\n'
            "catalog:\n"
            '  - path: "removed-managed.md"\n'
            '    mode: "render"\n'
            f'    sha256: "{UPDATE._sha256(app / "removed-managed.md")}"\n',
        )
        plan = _plan(app, clone, work)
        assert plan["orphan"] == ["removed-managed.md"]
        assert plan["retirement"] is None
        assert "KU-ORPHAN-001" in plan["blocking_issues"]
        try:
            UPDATE._validate_plan(plan, app, plan["plan_digest"])
        except UPDATE.UpdateError as exc:
            assert "KU-ORPHAN-001" in str(exc)
        else:
            raise AssertionError("未指定の orphan が apply 検証を通過した")
        assert (app / "removed-managed.md").is_file()
        assert (app / "docs/spec.md").read_text(encoding="utf-8") == "domain-owned\n"
    finally:
        temp.cleanup()


def _write_removed_lock(app: Path, clone: Path, relative: str = "removed-managed.md") -> None:
    _write(
        app,
        ".cursor/agentic-workflow-update.lock.yaml",
        "version: 1\n"
        f'kit_revision: "{_revision(clone)}"\n'
        "catalog:\n"
        f'  - path: "{relative}"\n'
        '    mode: "render"\n'
        f'    sha256: "{UPDATE._sha256(app / relative)}"\n',
    )


def test_retire_keep_leaves_file_and_drops_lock() -> None:
    app, clone, work, temp = _fixture(
        outputs=[("AGENTS.md", "render", None)],
        candidate_updates={"AGENTS.md": "generated-v2\n"},
    )
    try:
        _write(app, "removed-managed.md", "local-edit\n")
        _write(app, "app-owned.md", "owned\n")
        _write_removed_lock(app, clone)
        plan = _plan(app, clone, work, retirement="keep")
        assert plan["retirement"] == "keep"
        assert "KU-ORPHAN-001" not in plan["blocking_issues"]
        assert not any(item["path"] == "removed-managed.md" for item in plan["catalog"])
        assert not any(
            item["path"] == "removed-managed.md" and item.get("action") == "delete"
            for item in plan["changes"]
        )
        UPDATE._validate_plan(plan, app, plan["plan_digest"])
        UPDATE._apply_plan(plan)
        assert (app / "removed-managed.md").read_text(encoding="utf-8") == "local-edit\n"
        assert (app / "app-owned.md").read_text(encoding="utf-8") == "owned\n"
        assert (app / "docs/spec.md").read_text(encoding="utf-8") == "domain-owned\n"
    finally:
        temp.cleanup()


def test_retire_delete_removes_only_former_managed_file() -> None:
    app, clone, work, temp = _fixture(
        outputs=[("AGENTS.md", "render", None)],
        candidate_updates={"AGENTS.md": "generated-v2\n"},
    )
    try:
        _write(app, "removed-managed.md", "local-edit\n")
        _write(app, "app-owned.md", "owned\n")
        _write_removed_lock(app, clone)
        plan = _plan(app, clone, work, retirement="delete")
        assert plan["retirement"] == "delete"
        assert "KU-ORPHAN-001" not in plan["blocking_issues"]
        assert any(
            item["path"] == "removed-managed.md" and item.get("action") == "delete"
            for item in plan["changes"]
        )
        UPDATE._validate_plan(plan, app, plan["plan_digest"])
        UPDATE._apply_plan(plan)
        assert not (app / "removed-managed.md").exists()
        assert (app / "app-owned.md").read_text(encoding="utf-8") == "owned\n"
        assert (app / "docs/spec.md").read_text(encoding="utf-8") == "domain-owned\n"
    finally:
        temp.cleanup()


def test_retire_delete_renames_by_removing_old_path_only() -> None:
    app, clone, work, temp = _fixture(
        outputs=[("docs/new-guide.md", "render", None)],
        candidate_updates={"docs/new-guide.md": "same-bytes\n"},
    )
    try:
        _write(app, "docs/old-guide.md", "same-bytes\n")
        _write_removed_lock(app, clone, "docs/old-guide.md")
        plan = _plan(app, clone, work, retirement="delete")
        assert plan["rename_candidates"] == [
            {"old": "docs/old-guide.md", "new": "docs/new-guide.md"}
        ]
        UPDATE._apply_plan(plan)
        assert not (app / "docs/old-guide.md").exists()
        assert (app / "docs/new-guide.md").read_text(encoding="utf-8") == "same-bytes\n"
        assert (app / "docs/spec.md").read_text(encoding="utf-8") == "domain-owned\n"
    finally:
        temp.cleanup()


def test_retire_without_targets_is_fatal() -> None:
    app, clone, work, temp = _fixture(
        outputs=[("AGENTS.md", "render", None)],
        candidate_updates={"AGENTS.md": "generated-v2\n"},
    )
    try:
        try:
            _plan(app, clone, work, retirement="keep")
        except UPDATE.FatalUpdateError as exc:
            assert "KU-ORPHAN-001" in str(exc)
        else:
            raise AssertionError("解消対象がない retirement が受理された")
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


def test_malformed_overlay_stops_before_fetch() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-preflight-yaml-") as temp_dir:
        app = Path(temp_dir) / "app"
        (app / ".git").mkdir(parents=True)
        (app / "manifest.yaml").write_text(
            "project:\n  malformed: [\n",
            encoding="utf-8",
        )
        with patch.object(
            UPDATE,
            "_fetch_kit",
            side_effect=AssertionError("malformed overlay の後に fetch が呼ばれた"),
        ):
            assert UPDATE.main(["plan", "--app-root", str(app)]) == 2


def test_divergent_external_overlay_stops_before_fetch() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-overlay-") as temp_dir:
        base = Path(temp_dir)
        app = base / "app"
        (app / ".git").mkdir(parents=True)
        _write(app, "manifest.yaml", _root_manifest())
        overlay = base / "overlay.yaml"
        _write(base, "overlay.yaml", _root_manifest(code_review=True))
        before = (app / "manifest.yaml").read_bytes()
        with patch.object(
            UPDATE,
            "_fetch_kit",
            side_effect=AssertionError("不一致 overlay の後に fetch が呼ばれた"),
        ):
            assert (
                UPDATE.main(
                    [
                        "plan",
                        "--app-root",
                        str(app),
                        "--root-manifest",
                        str(overlay),
                    ]
                )
                == 2
            )
        assert (app / "manifest.yaml").read_bytes() == before


def test_same_digest_overlay_copies_work_tree_only() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-overlay-same-") as temp_dir:
        base = Path(temp_dir)
        app = base / "app"
        work = base / "work"
        overlay = base / "overlay.yaml"
        (app / ".git").mkdir(parents=True)
        _write(app, "manifest.yaml", _root_manifest())
        _write(app, "AGENTS.md", "owned\n")
        _write(base, "overlay.yaml", _root_manifest())
        before = (app / "manifest.yaml").read_bytes()
        UPDATE._assert_overlay_matches_app_manifest(app, overlay)
        UPDATE._prepare_work_tree(app, overlay, work)
        assert (work / "manifest.yaml").read_bytes() == before
        assert (app / "manifest.yaml").read_bytes() == before


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


def test_dirty_clone_updater_is_rejected_after_plan() -> None:
    app, clone, work, temp = _fixture()
    try:
        plan = _plan(app, clone, work)
        updater = clone / ".cursor/skills/agentic-workflow-update/SKILL.md"
        updater.write_text("tampered\n", encoding="utf-8")
        try:
            UPDATE._validate_plan(plan, app, plan["plan_digest"])
        except UPDATE.UpdateError as exc:
            assert "KU-PREIMAGE-001" in str(exc)
        else:
            raise AssertionError("plan 後に変更された host updater が受理された")
    finally:
        temp.cleanup()


def test_root_separation_rejects_app_overlap() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-root-scope-") as temp_dir:
        app = Path(temp_dir) / "app"
        clone = Path(temp_dir) / "clone"
        work = Path(temp_dir) / "work"
        app.mkdir()
        UPDATE._validate_root_separation(app, clone, work, None)
        for bad_clone, bad_work, bad_plan in (
            (app, work, None),
            (clone, app / "candidate", None),
            (clone, work, app / "plan.json"),
        ):
            try:
                UPDATE._validate_root_separation(app, bad_clone, bad_work, bad_plan)
            except UPDATE.FatalUpdateError as exc:
                assert "KU-SCOPE-001" in str(exc)
            else:
                raise AssertionError("対象アプリと重なる updater path が受理された")


def test_domain_path_mode_change_is_blocked() -> None:
    app, clone, work, temp = _fixture(
        outputs=[("docs/spec.md", "render", None)],
        candidate_updates={"docs/spec.md": "upstream-overwrite\n"},
    )
    try:
        plan = _plan(app, clone, work)
        assert "docs/spec.md" in {item["path"] for item in plan["changes"]}
        assert "KU-DENY-001" in plan["blocking_issues"]
    finally:
        temp.cleanup()


def test_malformed_plan_root_is_exit_2() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-plan-schema-") as temp_dir:
        plan = Path(temp_dir) / "plan.json"
        plan.write_text("[]\n", encoding="utf-8")
        assert (
            UPDATE.main(
                [
                    "apply",
                    "--plan-file",
                    str(plan),
                    "--approve-plan",
                    "invalid",
                ]
            )
            == 2
        )


def test_apply_lock_does_not_follow_symlink() -> None:
    app, _clone, _work, temp = _fixture()
    lock_path = (
        Path(tempfile.gettempdir())
        / f"agentic-workflow-update-{hashlib.sha256(str(app.resolve()).encode()).hexdigest()[:24]}.lock"
    )
    try:
        victim = Path(temp.name) / "victim"
        victim.write_text("safe\n", encoding="utf-8")
        if lock_path.is_symlink() or lock_path.exists():
            lock_path.unlink()
        lock_path.symlink_to(victim)
        try:
            with UPDATE._app_apply_lock(app):
                raise AssertionError("symlink の apply lock が受理された")
        except UPDATE.FatalUpdateError as exc:
            assert "apply lock" in str(exc)
        assert victim.read_text(encoding="utf-8") == "safe\n"
    finally:
        if lock_path.is_symlink() or lock_path.exists():
            lock_path.unlink()
        temp.cleanup()


def test_unchanged_catalog_is_rechecked_at_apply() -> None:
    app, clone, work, temp = _fixture(
        outputs=[("AGENTS.md", "render", None), ("README.md", "render", None)],
        candidate_updates={"AGENTS.md": "generated-v2\n", "README.md": "stable\n"},
    )
    try:
        _write(app, "README.md", "stable\n")
        plan = _plan(app, clone, work)
        assert "README.md" not in {item["path"] for item in plan["changes"]}
        _write(app, "README.md", "tampered\n")
        try:
            UPDATE._apply_plan(plan)
        except UPDATE.UpdateError as exc:
            assert "KU-PREIMAGE-001" in str(exc)
            assert "README.md" in str(exc)
        else:
            raise AssertionError("計画後の未変更ファイル改変が適用された")
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v1\n"
    finally:
        temp.cleanup()


def test_tampered_plan_cannot_apply_denied_path() -> None:
    app, clone, work, temp = _fixture(
        outputs=[("docs/spec.md", "render", None)],
        candidate_updates={"docs/spec.md": "upstream-overwrite\n"},
    )
    try:
        plan = _plan(app, clone, work)
        plan["blocking_issues"] = []
        protected = plan.get("protected")
        if isinstance(protected, dict):
            protected.pop("docs/spec.md", None)
        try:
            UPDATE._apply_plan(plan)
        except UPDATE.UpdateError as exc:
            assert "KU-DENY-001" in str(exc)
        else:
            raise AssertionError("保護対象の改ざん plan が適用された")
        assert (app / "docs/spec.md").read_text(encoding="utf-8") == "domain-owned\n"
    finally:
        temp.cleanup()


def test_schema_mismatch_and_bad_relative_path_are_fatal() -> None:
    app, clone, work, temp = _fixture()
    try:
        plan = _plan(app, clone, work)
        plan["schema_version"] = 99
        plan["plan_digest"] = UPDATE._plan_digest(plan)
        try:
            UPDATE._validate_plan(plan, app, plan["plan_digest"])
        except UPDATE.FatalUpdateError as exc:
            assert exc.exit_code == 2
            assert "schema" in str(exc)
        else:
            raise AssertionError("schema 不一致が致命的エラーにならなかった")
    finally:
        temp.cleanup()
    try:
        UPDATE._safe_rel("../outside")
    except UPDATE.FatalUpdateError as exc:
        assert exc.exit_code == 2
        assert "KU-SCOPE-001" in str(exc)
    else:
        raise AssertionError("不正な相対パスが致命的エラーにならなかった")


def test_ephemeral_cleanup_rejects_symlink_root() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-ephemeral-link-") as temp_dir:
        base = Path(temp_dir)
        victim = base / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("keep\n", encoding="utf-8")
        (victim / UPDATE.OWNED_ROOT_MARKER).write_text("owned\n", encoding="utf-8")
        link = base / "link"
        link.symlink_to(victim, target_is_directory=True)
        try:
            UPDATE._cleanup_ephemeral_root({"ephemeral_root": str(link)})
        except UPDATE.UpdateError as exc:
            assert "symlink" in str(exc)
        else:
            raise AssertionError("symlink temp が削除された")
        assert (victim / "keep.txt").is_file()


def test_host_source_symlink_is_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-host-link-") as temp_dir:
        base = Path(temp_dir)
        source = base / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("skill\n", encoding="utf-8")
        link = base / "link"
        link.symlink_to(source)
        host = base / "host"
        try:
            UPDATE.stage_host_updater(link, host)
        except UPDATE.HostInstallError as exc:
            assert "symlink" in str(exc)
        else:
            raise AssertionError("symlink 正本が受理された")
        assert not (host / "agentic-workflow-update").exists()


def test_host_lock_rejects_symlink_and_serializes() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-host-lock-") as temp_dir:
        base = Path(temp_dir) / "host"
        base.mkdir()
        victim = Path(temp_dir) / "victim"
        victim.write_text("safe\n", encoding="utf-8")
        lock = base / ".agentic-workflow-update.lock"
        lock.symlink_to(victim)
        try:
            with UPDATE.host_install_lock(base):
                raise AssertionError("symlink host lock が受理された")
        except UPDATE.HostInstallError as exc:
            assert "symlink" in str(exc)
        assert victim.read_text(encoding="utf-8") == "safe\n"
        lock.unlink()

        held = threading.Event()
        release = threading.Event()
        acquired = threading.Event()

        def holder() -> None:
            with UPDATE.host_install_lock(base):
                held.set()
                assert release.wait(5)

        def waiter() -> None:
            with UPDATE.host_install_lock(base):
                acquired.set()

        first = threading.Thread(target=holder)
        second = threading.Thread(target=waiter)
        first.start()
        assert held.wait(2)
        second.start()
        assert acquired.wait(0.3) is False
        release.set()
        second.join(2)
        first.join(2)
        assert acquired.is_set()


def test_worker_contract_missing_step_docs_is_exit_2() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-missing-steps-") as temp_dir:
        work_root = Path(temp_dir)
        _install_worker_gate(work_root)
        env = dict(os.environ)
        env["AGENTIC_WORKFLOW_WORK_ROOT"] = str(work_root)
        result = subprocess.run(
            [sys.executable, str(HERE / "test_worker_contract.py")],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, result.stderr
        assert "FATAL" in result.stderr


def test_owned_temp_cleanup_requires_marker() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-cleanup-") as temp_dir:
        root = Path(temp_dir) / "owned"
        root.mkdir()
        plan = {"ephemeral_root": str(root)}
        try:
            UPDATE._cleanup_ephemeral_root(plan)
        except UPDATE.UpdateError as exc:
            assert "KU-SCOPE-001" in str(exc)
        else:
            raise AssertionError("marker なし temp が削除された")
        (root / UPDATE.OWNED_ROOT_MARKER).write_text("owned\n", encoding="utf-8")
        UPDATE._cleanup_ephemeral_root(plan)
        assert not root.exists()


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


def test_worker_contract_uses_work_root_and_exit_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-worker-contract-") as temp_dir:
        base = Path(temp_dir)
        clone_scripts, work_root = _worker_contract_fixture(base)
        enabled = {"agent_workflow": {"enabled": True}}
        disabled = {"agent_workflow": {"enabled": False}}

        with patch.object(RUNNER, "HERE", str(clone_scripts)):
            assert (
                RUNNER._run_worker_contract_validator(disabled, str(work_root))
                == 0
            )
            assert (
                RUNNER._run_worker_contract_validator(enabled, str(work_root))
                == 2
            )

            gate = _install_worker_gate(work_root)
            assert (
                RUNNER._run_worker_contract_validator(enabled, str(work_root))
                == 0
            )

            sample = (
                clone_scripts.parent
                / "fixtures"
                / "artifacts"
                / "sample-report--step1.md"
            )
            sample.write_text(
                "\n".join(
                    line
                    for line in sample.read_text(encoding="utf-8").splitlines()
                    if not line.startswith("requirements_digest:")
                )
                + "\n",
                encoding="utf-8",
            )
            assert (
                RUNNER._run_worker_contract_validator(enabled, str(work_root))
                == 1
            )
            assert gate.is_file()


def test_transaction_gate_failure_restores_app_and_leaves_host() -> None:
    app, clone, work, temp = _fixture()
    try:
        host = Path(temp.name) / "host"
        _write(host, "agentic-workflow-update/SKILL.md", "old-host\n")
        plan = _plan(app, clone, work)
        with (
            patch.dict(os.environ, {"AGENTIC_WORKFLOW_UPDATE_HOME": str(host)}),
            patch.object(
                UPDATE,
                "_run_application_validation",
                side_effect=UPDATE.UpdateError("gate failed"),
            ),
        ):
            try:
                UPDATE._apply_transaction(plan)
            except UPDATE.UpdateError as exc:
                assert "gate failed" in str(exc)
            else:
                raise AssertionError("quality gate 失敗が適用成功になった")
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v1\n"
        assert (app / "docs/spec.md").read_text(encoding="utf-8") == "domain-owned\n"
        assert (host / "agentic-workflow-update/SKILL.md").read_text(encoding="utf-8") == "old-host\n"
    finally:
        temp.cleanup()


def test_transaction_host_lock_failure_is_update_error() -> None:
    app, _clone, _work, temp = _fixture()
    try:
        host = Path(temp.name) / "host"
        plan = _plan(app, _clone, _work)
        with (
            patch.dict(os.environ, {"AGENTIC_WORKFLOW_UPDATE_HOME": str(host)}),
            patch.object(
                UPDATE,
                "host_install_lock",
                side_effect=UPDATE.HostInstallError("個人スキル配置先がsymlinkです"),
            ),
        ):
            try:
                UPDATE._apply_transaction(plan)
            except UPDATE.UpdateError as exc:
                assert "KU-HOST-001" in str(exc)
                assert "symlink" in str(exc)
            else:
                raise AssertionError("host lock 失敗が適用成功になった")
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v1\n"
    finally:
        temp.cleanup()


def test_min_context_window_rejects_truncated_numbers() -> None:
    for raw in (250000.5, True, "200000.7"):
        merged = {
            "project": {"context_budget": {"min_context_window_tokens": raw}},
            "framework": {},
        }
        try:
            RUNNER._apply_derived_budget_thresholds(merged)
        except SystemExit as exc:
            assert exc.code == 2, raw
        else:
            raise AssertionError(f"非整数が受理された: {raw!r}")

    merged = {
        "project": {"context_budget": {"min_context_window_tokens": "250000"}},
        "framework": {},
    }
    result = RUNNER._apply_derived_budget_thresholds(merged)
    assert result["framework"]["budget_thresholds"]["min_context_window_tokens"] == 250000


def test_transaction_host_stage_failure_restores_app_and_host() -> None:
    app, clone, work, temp = _fixture()
    try:
        host = Path(temp.name) / "host"
        _write(host, "agentic-workflow-update/SKILL.md", "old-host\n")
        plan = _plan(app, clone, work)
        real_stage = UPDATE._stage_host_updater

        def stage_then_drop_skill(clone_root: Path):
            result = real_stage(clone_root)
            (result.destination / "SKILL.md").unlink()
            return result

        with (
            patch.dict(os.environ, {"AGENTIC_WORKFLOW_UPDATE_HOME": str(host)}),
            patch.object(UPDATE, "_stage_host_updater", side_effect=stage_then_drop_skill),
        ):
            try:
                UPDATE._apply_transaction(plan)
            except UPDATE.UpdateError as exc:
                assert "KU-HOST-001" in str(exc)
            else:
                raise AssertionError("host 配置失敗が適用成功になった")
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v1\n"
        assert (host / "agentic-workflow-update/SKILL.md").read_text(encoding="utf-8") == "old-host\n"
        assert not list(host.glob(".agentic-workflow-update.previous.*"))
    finally:
        temp.cleanup()


def test_transaction_success_commits_app_and_host() -> None:
    app, clone, work, temp = _fixture()
    try:
        host = Path(temp.name) / "host"
        _write(host, "agentic-workflow-update/SKILL.md", "old-host\n")
        plan = _plan(app, clone, work)
        with patch.dict(os.environ, {"AGENTIC_WORKFLOW_UPDATE_HOME": str(host)}):
            UPDATE._apply_transaction(plan)
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v2\n"
        installed = (host / "agentic-workflow-update/SKILL.md").read_text(encoding="utf-8")
        assert installed == (clone / ".cursor/skills/agentic-workflow-update/SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "old-host" not in installed
        assert not list(host.glob(".agentic-workflow-update.previous.*"))
        assert (app / "docs/spec.md").read_text(encoding="utf-8") == "domain-owned\n"
    finally:
        temp.cleanup()


def test_skill_contract_excludes_vendor_flow() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    assert "固定public URL" in content
    assert "並置 kit の `origin`" not in content
    assert "foundation/engine" in content
    assert ".cursor/agentic-workflow-update.lock.yaml" in content
    assert "--root-manifest" in content
    assert "--retire" in content
    assert "AskQuestion" in content
    assert "bin/foundation-gate generate" not in content
    assert "--update-skill-home" in content

    readme = README_FILE.read_text(encoding="utf-8")
    update_section = readme.split("## 適用済みアプリへの kit 更新", 1)[1]
    update_section = update_section.split("## 手動実行", 1)[0]
    assert "並置された" not in update_section
    assert "--kit-root" not in update_section
    assert "bin/foundation-gate generate" not in update_section
    assert "対象アプリへ配置" not in update_section
    assert "--update-skill-home" in update_section


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


def test_fresh_clone_bootstrap_installs_host_updater() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-bootstrap-") as temp_dir:
        base = Path(temp_dir)
        candidate = base / "candidate"
        host = base / "host"
        missing_root_manifest = base / "fresh-clone" / "manifest.yaml"
        assert (
            RUNNER.main(
                [
                    "generate",
                    "--seed-manifest",
                    str(
                        ROOT
                        / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"
                    ),
                    "--root-manifest",
                    str(missing_root_manifest),
                    "--work-root",
                    str(candidate),
                    "--update-skill-home",
                    str(host),
                ]
            )
            == 0
        )
        assert not candidate.exists()
        assert (host / "agentic-workflow-update/SKILL.md").is_file()


def main() -> int:
    tests = (
        ("public fetch contract", test_public_fetch_contract),
        ("consumer plan and apply", test_consumer_plan_and_apply_exclude_kit_sources),
        ("lock without cursor dir", test_plan_creates_lock_when_cursor_directory_is_absent),
        ("resolved catalog", test_resolved_catalog_applies_overlay_features),
        ("initial adopt", test_initial_adopt_does_not_infer_orphans),
        ("lock orphan", test_lock_catalog_detects_removed_managed_output),
        ("retire keep", test_retire_keep_leaves_file_and_drops_lock),
        ("retire delete", test_retire_delete_removes_only_former_managed_file),
        ("retire rename", test_retire_delete_renames_by_removing_old_path_only),
        ("retire without targets", test_retire_without_targets_is_fatal),
        ("transaction gate failure", test_transaction_gate_failure_restores_app_and_leaves_host),
        ("transaction host failure", test_transaction_host_stage_failure_restores_app_and_host),
        ("transaction host lock failure", test_transaction_host_lock_failure_is_update_error),
        ("min context window integers", test_min_context_window_rejects_truncated_numbers),
        ("transaction success", test_transaction_success_commits_app_and_host),
        ("overlay preflight", test_overlay_preflight_happens_before_fetch),
        ("malformed overlay preflight", test_malformed_overlay_stops_before_fetch),
        ("divergent external overlay", test_divergent_external_overlay_stops_before_fetch),
        ("same digest overlay", test_same_digest_overlay_copies_work_tree_only),
        ("plan digest and preimage", test_plan_digest_and_preimage_reject_unapproved_apply),
        ("dirty clone updater", test_dirty_clone_updater_is_rejected_after_plan),
        ("root separation", test_root_separation_rejects_app_overlap),
        ("domain mode change", test_domain_path_mode_change_is_blocked),
        ("apply lock symlink", test_apply_lock_does_not_follow_symlink),
        ("unchanged catalog recheck", test_unchanged_catalog_is_rechecked_at_apply),
        ("tampered deny path", test_tampered_plan_cannot_apply_denied_path),
        ("fatal input contract", test_schema_mismatch_and_bad_relative_path_are_fatal),
        ("ephemeral symlink", test_ephemeral_cleanup_rejects_symlink_root),
        ("host source symlink", test_host_source_symlink_is_rejected),
        ("host lock", test_host_lock_rejects_symlink_and_serializes),
        ("missing step docs", test_worker_contract_missing_step_docs_is_exit_2),
        ("malformed plan schema", test_malformed_plan_root_is_exit_2),
        ("owned temp cleanup", test_owned_temp_cleanup_requires_marker),
        ("subprocess diagnostics", test_subprocess_error_keeps_exit_and_stderr),
        ("candidate validation audit scope", test_candidate_validation_scopes_seed_audit),
        ("candidate validation rehearsal", test_candidate_validation_rehearses_existing_seed),
        ("worker contract work root", test_worker_contract_uses_work_root_and_exit_boundaries),
        ("skill contract", test_skill_contract_excludes_vendor_flow),
        ("host install and check", test_host_install_and_check_do_not_update_host),
        ("generate host flags", test_generate_host_flags),
        ("fresh clone bootstrap", test_fresh_clone_bootstrap_installs_host_updater),
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
