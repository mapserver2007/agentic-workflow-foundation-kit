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
SKILL_README = ROOT / ".cursor/skills/agentic-workflow-update/README.md"
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
    kit_body_roots: tuple[Path, ...] = (),
) -> dict:
    """既定は kit 本体の同期を無効（空のルート）にする。

    fixture の clone は実物の foundation scripts / engine scripts / updater を持つだけで、
    kit 本体の全ルートを備えない。kit 本体を検査するテストだけが、ルートを明示する。
    """
    return UPDATE._build_plan(
        app,
        clone,
        work,
        overlay or app / "manifest.yaml",
        validate=False,
        kit_revision=_revision(clone),
        retirement=retirement,
        kit_body_roots=kit_body_roots,
    )


ENGINE_SCRIPTS = Path(".cursor/skills/agentic-workflow-engine/scripts")
FOUNDATION_SKILL = Path(".cursor/skills/agentic-workflow-foundation")
UPDATER_SKILL = Path(".cursor/skills/agentic-workflow-update")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _read_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def test_public_fetch_contract() -> None:
    content = FETCH_SCRIPT.read_text(encoding="utf-8")
    assert 'https://github.com/mapserver2007/agentic-workflow-foundation-kit.git' in content
    assert "--kit-root" not in content
    assert "--app-root" not in content
    assert "init.yaml" not in content
    assert "_github-auth" not in content
    assert "credential.helper=" in content


def test_consumer_plan_and_apply_sync_kit_body_except_updater() -> None:
    app, clone, work, temp = _fixture()
    try:
        roots = (FOUNDATION_SKILL, Path(".cursor/skills/agentic-workflow-engine"))
        plan = _plan(app, clone, work, kit_body_roots=roots)
        paths = {item["path"] for item in plan["changes"]}
        assert "AGENTS.md" in paths
        assert ".gitignore" in paths
        assert ".cursor/agentic-workflow-update.lock.yaml" in paths
        kit_paths = {item["path"] for item in plan["changes"] if item["kind"] == "kit_body"}
        assert f"{FOUNDATION_SKILL}/scripts/run_resolved_engine.py" in kit_paths
        assert f"{ENGINE_SCRIPTS}/genlib.py" in kit_paths
        assert not any(path.startswith(str(UPDATER_SKILL)) for path in paths)
        assert plan["baseline"] == "adopt"
        assert plan["post_apply_check"] is True
        assert plan["schema_version"] == 2
        assert not plan["blocking_issues"], plan
        UPDATE._validate_plan(plan, app, plan["plan_digest"])
        UPDATE._apply_plan(plan)
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v2\n"
        assert (app / ".cursor/agentic-workflow-update.lock.yaml").is_file()
        assert _read_tree(app / FOUNDATION_SKILL) == _read_tree(clone / FOUNDATION_SKILL)
        assert _read_tree(app / ".cursor/skills/agentic-workflow-engine") == _read_tree(
            clone / ".cursor/skills/agentic-workflow-engine"
        )
        assert not (app / UPDATER_SKILL).exists()
        UPDATE._run_application_validation(app, clone, app / "manifest.yaml")
    finally:
        temp.cleanup()


def test_empty_kit_body_roots_leave_kit_body_untouched() -> None:
    app, clone, work, temp = _fixture()
    try:
        plan = _plan(app, clone, work)
        assert plan["kit_body_roots"] == []
        assert plan["post_apply_check"] is False
        assert not any(item["kind"] == "kit_body" for item in plan["changes"])
        UPDATE._apply_plan(plan)
        assert not (app / FOUNDATION_SKILL).exists()
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


def test_split_mode_is_not_in_catalog_and_blueprint_is_denied() -> None:
    """mode: split は updater の catalog に含めない（seed と同じく読み飛ばす）。"""
    manifest = {
        "outputs": [
            {"path": "AGENTS.md", "mode": "render"},
            {"path": "docs/tech-stack/", "mode": "split"},
            {"path": "docs/architecture.md", "mode": "seed"},
            {"path": ".gitignore", "mode": "marker"},
        ]
    }
    catalog = UPDATE._catalog_from_manifest(manifest)
    assert {str(path) for path in catalog} == {"AGENTS.md", ".gitignore"}, catalog
    assert Path(".cursor/docs/APP_DESIGN_BESTPRACTICE.md") in UPDATE.DENY_EXACT
    assert Path(".cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md") not in UPDATE.DENY_EXACT


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


def test_split_index_paths_come_only_from_split_outputs() -> None:
    manifest = {
        "outputs": [
            {"path": "docs/tech-stack/", "mode": "split", "index_path": "docs/tech-stack.md"},
            {"path": "AGENTS.md", "mode": "render", "index_path": "ignored.md"},
            {"path": "docs/other/", "mode": "split"},
            "not-a-mapping",
        ]
    }
    assert UPDATE._split_index_paths(manifest) == {Path("docs/tech-stack.md")}
    assert UPDATE._split_index_paths({}) == set()


def test_render_to_split_transfer_is_not_orphan() -> None:
    """以前の kit では docs/tech-stack.md が render だった。split の索引へ所有が移っただけなので orphan にしない。"""
    outputs = [("AGENTS.md", "render", None)]
    split_manifest = _manifest(outputs) + (
        '  - path: "docs/tech-stack/"\n'
        '    template: "docs/tech-stack.md.template"\n'
        "    mode: split\n"
        '    index_path: "docs/tech-stack.md"\n'
    )
    # 対照: split の出力が無ければ、旧 lock にだけあるパスは従来どおり orphan（検知の経路が生きている）。
    app, clone, work, temp = _fixture(outputs=outputs, candidate_updates={"AGENTS.md": "generated-v2\n"})
    try:
        _write(app, "docs/tech-stack.md", "old-render\n")
        _write_removed_lock(app, clone, "docs/tech-stack.md")
        plan = _plan(app, clone, work)
        assert plan["orphan"] == ["docs/tech-stack.md"], plan["orphan"]
        assert "KU-ORPHAN-001" in plan["blocking_issues"]
    finally:
        temp.cleanup()
    # split の索引になったパスは、orphan にも削除にもしない。
    app, clone, work, temp = _fixture(outputs=outputs, candidate_updates={"AGENTS.md": "generated-v2\n"})
    try:
        _write(app, "docs/tech-stack.md", "old-render\n")
        _write_removed_lock(app, clone, "docs/tech-stack.md")
        _write(clone, ".cursor/skills/agentic-workflow-foundation/manifest.yaml", split_manifest)
        plan = _plan(app, clone, work)
        assert plan["orphan"] == [], plan["orphan"]
        assert plan["rename_candidates"] == [], plan["rename_candidates"]
        assert "KU-ORPHAN-001" not in plan["blocking_issues"], plan["blocking_issues"]
        assert not any(item["path"] == "docs/tech-stack.md" for item in plan["changes"])
        assert not any(item["path"] == "docs/tech-stack.md" for item in plan["catalog"])
        UPDATE._validate_plan(plan, app, plan["plan_digest"])
        UPDATE._apply_plan(plan)
        assert (app / "docs/tech-stack.md").read_text(encoding="utf-8") == "old-render\n"
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v2\n"
        # 解消対象が無いので、retirement の指定は致命的エラー（delete でも新索引を消す変更は作らない）。
        try:
            _plan(app, clone, work, retirement="delete")
        except UPDATE.FatalUpdateError as exc:
            assert "KU-ORPHAN-001" in str(exc)
        else:
            raise AssertionError("所有移管のパスに retirement=delete が受理された")
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


def test_skill_contract_mirrors_kit_body_except_updater() -> None:
    content = SKILL_FILE.read_text(encoding="utf-8")
    assert "固定public URL" in content
    assert "並置 kit の `origin`" not in content
    assert "foundation / engine" in content
    assert "KIT_BODY_ROOTS" in content
    assert "cloneとの直接比較" in content
    assert "KU-KITBODY-001" in content
    assert "retirement=delete" in content
    assert "run_resolved_engine.py check" in content
    assert "agentic-workflow-update" in content
    assert "foundation/engineをvendorしない" not in content
    assert ".cursor/agentic-workflow-update.lock.yaml" in content
    assert "--root-manifest" in content
    assert "--retire" in content
    assert "AskQuestion" in content
    assert "bin/foundation-gate generate" not in content
    assert "--update-skill-home" in content
    assert "README.md" in content

    skill_readme = SKILL_README.read_text(encoding="utf-8")
    assert "seed" in skill_readme
    assert "保護" in skill_readme
    assert "render" in skill_readme
    assert "marker" in skill_readme

    readme = README_FILE.read_text(encoding="utf-8")
    update_section = readme.split("## 適用済みアプリへの kit 更新", 1)[1]
    update_section = update_section.split("## 手動実行", 1)[0]
    assert "並置された" not in update_section
    assert "--kit-root" not in update_section
    assert "bin/foundation-gate generate" not in update_section
    assert "対象アプリへ配置" not in update_section
    assert "対象アプリへ vendor しません" not in update_section
    assert "KU-KITBODY-001" in update_section
    assert "kit 本体" in update_section
    assert "run_resolved_engine.py check" in update_section
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


def _tamper_plan(plan: dict) -> dict:
    plan["plan_digest"] = UPDATE._plan_digest(plan)
    return plan


def _prepare_engine_app(app: Path, clone: Path) -> Path:
    """app の engine scripts を clone と同じにしたうえで、add / update / delete / mode の差を作る。"""
    _copy_tree(clone / ENGINE_SCRIPTS, app / ENGINE_SCRIPTS)
    scripts = app / ENGINE_SCRIPTS
    (scripts / "genlib.py").write_text("local-edit\n", encoding="utf-8")
    (scripts / "audit.py").unlink()
    (scripts / "extra.py").write_text("app-only\n", encoding="utf-8")
    clone_mode = UPDATE._mode(clone / ENGINE_SCRIPTS / "generate.py")
    (scripts / "generate.py").chmod(0o600 if clone_mode != 0o600 else 0o644)
    return scripts


def test_kit_body_add_update_delete_and_mode() -> None:
    app, clone, work, temp = _fixture()
    try:
        scripts = _prepare_engine_app(app, clone)
        roots = (ENGINE_SCRIPTS,)
        plan = _plan(app, clone, work, kit_body_roots=roots)
        kit_changes = {item["path"]: item for item in plan["changes"] if item["kind"] == "kit_body"}
        assert kit_changes[f"{ENGINE_SCRIPTS}/genlib.py"]["action"] == "update"
        assert kit_changes[f"{ENGINE_SCRIPTS}/audit.py"]["action"] == "add"
        assert kit_changes[f"{ENGINE_SCRIPTS}/generate.py"]["action"] == "update"
        assert f"{ENGINE_SCRIPTS}/extra.py" not in kit_changes
        assert plan["baseline"] == "adopt"
        assert plan["kit_body_removed"] == [f"{ENGINE_SCRIPTS}/extra.py"]
        assert plan["post_apply_check"] is False
        # 初回 adopt でも、kit 本体の余剰ファイルは計画に出る。未承認では停止する。
        assert "KU-ORPHAN-001" in plan["blocking_issues"]
        for retirement in (None, "keep"):
            blocked = _plan(app, clone, work, retirement=retirement, kit_body_roots=roots)
            assert "KU-ORPHAN-001" in blocked["blocking_issues"], retirement
            assert not any(item["action"] == "delete" for item in blocked["changes"])
        assert (scripts / "extra.py").is_file()

        deleting = _plan(app, clone, work, retirement="delete", kit_body_roots=roots)
        assert "KU-ORPHAN-001" not in deleting["blocking_issues"], deleting["blocking_issues"]
        assert any(
            item["path"] == f"{ENGINE_SCRIPTS}/extra.py"
            and item["kind"] == "kit_body"
            and item["action"] == "delete"
            for item in deleting["changes"]
        )
        UPDATE._validate_plan(deleting, app, deleting["plan_digest"])
        UPDATE._apply_plan(deleting)
        assert not (scripts / "extra.py").exists()
        assert _read_tree(scripts) == _read_tree(clone / ENGINE_SCRIPTS)
        assert UPDATE._mode(scripts / "generate.py") == UPDATE._mode(
            clone / ENGINE_SCRIPTS / "generate.py"
        )
        assert not (app / UPDATER_SKILL).exists()
    finally:
        temp.cleanup()


def test_kit_body_deletion_without_delete_approval_cannot_apply() -> None:
    app, clone, work, temp = _fixture()
    try:
        scripts = _prepare_engine_app(app, clone)
        plan = _plan(app, clone, work, retirement="keep", kit_body_roots=(ENGINE_SCRIPTS,))
        plan["blocking_issues"] = []
        _tamper_plan(plan)
        try:
            UPDATE._validate_plan(plan, app, plan["plan_digest"])
        except UPDATE.UpdateError as exc:
            assert "KU-ORPHAN-001" in str(exc)
            assert "retirement=delete" in str(exc)
        else:
            raise AssertionError("keep のまま kit 本体の削除が受理された")
        assert (scripts / "extra.py").is_file()
    finally:
        temp.cleanup()


def test_kit_body_never_includes_updater_or_outside_roots() -> None:
    app, clone, work, temp = _fixture()
    try:
        for bad in (UPDATER_SKILL, Path("docs"), Path(".cursor/docs/APP_DESIGN_BESTPRACTICE.md")):
            try:
                _plan(app, clone, work, kit_body_roots=(bad,))
            except UPDATE.FatalUpdateError as exc:
                assert "KU-KITBODY-001" in str(exc), bad
            else:
                raise AssertionError(f"同期できない範囲が受理された: {bad}")
        _write(app, f"{UPDATER_SKILL}/SKILL.md", "app-copy\n")
        plan = _plan(app, clone, work)
        assert any("KU-HOST-001" in item for item in plan["warnings"]), plan["warnings"]
        assert not any(item["path"].startswith(str(UPDATER_SKILL)) for item in plan["changes"])
        UPDATE._apply_plan(plan)
        assert (app / UPDATER_SKILL / "SKILL.md").read_text(encoding="utf-8") == "app-copy\n"
        # 改ざんされた plan でも、updater の change は適用できない。
        tampered = _plan(app, clone, work)
        tampered["changes"].append({
            "path": f"{UPDATER_SKILL}/SKILL.md",
            "kind": "kit_body",
            "mode": "kit_body",
            "action": "delete",
            "candidate_path": "",
            "candidate_sha256": "",
            "candidate_mode": None,
            "preimage_sha256": UPDATE._sha256(app / UPDATER_SKILL / "SKILL.md"),
            "preimage_mode": UPDATE._mode(app / UPDATER_SKILL / "SKILL.md"),
        })
        try:
            UPDATE._apply_plan(tampered)
        except UPDATE.UpdateError as exc:
            assert "KU-KITBODY-001" in str(exc)
        else:
            raise AssertionError("updater を含む plan が適用された")
        assert (app / UPDATER_SKILL / "SKILL.md").is_file()
    finally:
        temp.cleanup()


def test_kit_body_catalog_rejects_kit_roots() -> None:
    for root in (FOUNDATION_SKILL / "x.md", UPDATER_SKILL / "x.md"):
        try:
            UPDATE._catalog_from_manifest({"outputs": [{"path": str(root), "mode": "render"}]})
        except UPDATE.FatalUpdateError as exc:
            assert "KU-KITBODY-001" in str(exc)
        else:
            raise AssertionError(f"kit 本体の範囲の出力が catalog に入った: {root}")


def test_kit_body_clone_root_missing_is_fatal() -> None:
    app, clone, work, temp = _fixture()
    try:
        try:
            _plan(
                app,
                clone,
                work,
                kit_body_roots=(Path(".cursor/skills/technology-stack-unified-design"),),
            )
        except UPDATE.FatalUpdateError as exc:
            assert "KU-KITBODY-001" in str(exc)
        else:
            raise AssertionError("clone に無い kit 本体のルートが受理された")
        assert not (app / ".cursor/skills/technology-stack-unified-design").exists()
    finally:
        temp.cleanup()


def test_kit_body_ignores_bytecode_and_rejects_symlinks() -> None:
    app, clone, work, temp = _fixture()
    try:
        scripts = app / ENGINE_SCRIPTS
        _copy_tree(clone / ENGINE_SCRIPTS, scripts)
        (scripts / "__pycache__").mkdir()
        (scripts / "__pycache__" / "genlib.cpython-311.pyc").write_bytes(b"\x00")
        (scripts / "stale.pyc").write_bytes(b"\x00")
        (clone / ENGINE_SCRIPTS / "__pycache__").mkdir()
        (clone / ENGINE_SCRIPTS / "__pycache__" / "only-clone.pyc").write_bytes(b"\x01")
        plan = _plan(app, clone, work, kit_body_roots=(ENGINE_SCRIPTS,))
        assert plan["kit_body_removed"] == []
        assert not any(item["kind"] == "kit_body" for item in plan["changes"]), plan["changes"]
        assert not plan["blocking_issues"], plan["blocking_issues"]

        (scripts / "link.py").symlink_to(scripts / "genlib.py")
        try:
            _plan(app, clone, work, kit_body_roots=(ENGINE_SCRIPTS,))
        except UPDATE.UpdateError as exc:
            assert "KU-KITBODY-001" in str(exc)
        else:
            raise AssertionError("kit 本体の symlink が受理された")
    finally:
        temp.cleanup()


def test_plan_kit_body_changes_must_stay_inside_plan_roots() -> None:
    app, clone, work, temp = _fixture()
    try:
        _prepare_engine_app(app, clone)
        plan = _plan(app, clone, work, retirement="delete", kit_body_roots=(ENGINE_SCRIPTS,))
        outside = Path(f"{FOUNDATION_SKILL}/scripts/run_resolved_engine.py")
        plan["changes"].append({
            "path": str(outside),
            "kind": "kit_body",
            "mode": "kit_body",
            "action": "add",
            "candidate_path": str(clone / outside),
            "candidate_sha256": UPDATE._sha256(clone / outside),
            "candidate_mode": UPDATE._mode(clone / outside),
            "preimage_sha256": None,
            "preimage_mode": None,
        })
        _tamper_plan(plan)
        try:
            UPDATE._validate_plan(plan, app, plan["plan_digest"])
        except UPDATE.UpdateError as exc:
            assert "KU-KITBODY-001" in str(exc)
        else:
            raise AssertionError("plan のルート外の kit_body change が受理された")
    finally:
        temp.cleanup()


def test_mirror_kit_body_makes_work_equal_to_clone() -> None:
    app, clone, work, temp = _fixture()
    try:
        _copy_tree(clone / ENGINE_SCRIPTS, work / ENGINE_SCRIPTS)
        (work / ENGINE_SCRIPTS / "extra.py").write_text("work-only\n", encoding="utf-8")
        (work / ENGINE_SCRIPTS / "genlib.py").write_text("stale\n", encoding="utf-8")
        UPDATE._mirror_kit_body(clone, work, (ENGINE_SCRIPTS,))
        assert _read_tree(work / ENGINE_SCRIPTS) == _read_tree(clone / ENGINE_SCRIPTS)
        try:
            UPDATE._mirror_kit_body(
                clone, work, (Path(".cursor/skills/technology-stack-unified-design"),)
            )
        except UPDATE.FatalUpdateError as exc:
            assert "KU-KITBODY-001" in str(exc)
        else:
            raise AssertionError("clone に無いルートのミラーが受理された")
    finally:
        temp.cleanup()


def _split_manifest(outputs: list[tuple[str, str, str | None]]) -> str:
    return _manifest(outputs) + (
        '  - path: "docs/tech-stack/"\n'
        '    template: "docs/tech-stack.md.template"\n'
        "    mode: split\n"
        '    index_path: "docs/tech-stack.md"\n'
    )


def _split_fixture() -> tuple[Path, Path, Path, tempfile.TemporaryDirectory[str]]:
    outputs = [("AGENTS.md", "render", None)]
    app, clone, work, temp = _fixture(
        outputs=outputs, candidate_updates={"AGENTS.md": "generated-v2\n"}
    )
    _write(clone, ".cursor/skills/agentic-workflow-foundation/manifest.yaml", _split_manifest(outputs))
    # kit 自身のブループリントから生成された split 出力。対象アプリの比較には使わない。
    _write(clone, "docs/tech-stack/from-kit.md", "kit-doc\n")
    _write(clone, "docs/tech-stack.md", "kit-index\n")
    _write(work, "docs/tech-stack/01-a.md", "A\n")
    _write(work, "docs/tech-stack/02-b.md", "B\n")
    _write(work, "docs/tech-stack.md", "app-index-new\n")
    _write(app, ".cursor/docs/APP_DESIGN_BESTPRACTICE.md", "blueprint\n")
    _write(app, "docs/tech-stack/02-b.md", "B-old\n")
    _write(app, "docs/tech-stack/stale.md", "stale\n")
    _write(app, "docs/tech-stack.md", "app-index-old\n")
    return app, clone, work, temp


def test_split_output_follows_work_result_not_clone() -> None:
    app, clone, work, temp = _split_fixture()
    try:
        plan = _plan(app, clone, work)
        split = {item["path"]: item for item in plan["changes"] if item["kind"] == "split"}
        assert split["docs/tech-stack/01-a.md"]["action"] == "add"
        assert split["docs/tech-stack/02-b.md"]["action"] == "update"
        assert split["docs/tech-stack.md"]["action"] == "update"
        assert "docs/tech-stack/from-kit.md" not in split
        assert plan["split_removed"] == ["docs/tech-stack/stale.md"]
        assert "KU-ORPHAN-001" in plan["blocking_issues"]
        assert not any(item["path"].startswith("docs/tech-stack") for item in plan["catalog"])
        assert plan["orphan"] == []

        keep = _plan(app, clone, work, retirement="keep")
        assert "KU-ORPHAN-001" in keep["blocking_issues"]

        approved = _plan(app, clone, work, retirement="delete")
        assert not approved["blocking_issues"], approved["blocking_issues"]
        UPDATE._validate_plan(approved, app, approved["plan_digest"])
        UPDATE._apply_plan(approved)
        assert _read_tree(app / "docs/tech-stack") == {
            "01-a.md": b"A\n",
            "02-b.md": b"B\n",
        }
        assert (app / "docs/tech-stack.md").read_text(encoding="utf-8") == "app-index-new\n"
        assert (app / ".cursor/docs/APP_DESIGN_BESTPRACTICE.md").read_text(encoding="utf-8") == "blueprint\n"
    finally:
        temp.cleanup()


def test_split_output_directory_with_subdirectory_is_a_plan_failure() -> None:
    app, clone, work, temp = _split_fixture()
    try:
        _write(app, "docs/tech-stack/sub/x.md", "nested\n")
        try:
            _plan(app, clone, work)
        except UPDATE.UpdateError as exc:
            assert "KU-KITBODY-001" in str(exc)
        else:
            raise AssertionError("split 出力ディレクトリの下位ディレクトリが受理された")
        assert (app / "docs/tech-stack/sub/x.md").is_file()
    finally:
        temp.cleanup()


def test_split_without_work_output_is_not_compared() -> None:
    outputs = [("AGENTS.md", "render", None)]
    app, clone, work, temp = _fixture(
        outputs=outputs, candidate_updates={"AGENTS.md": "generated-v2\n"}
    )
    try:
        _write(clone, ".cursor/skills/agentic-workflow-foundation/manifest.yaml", _split_manifest(outputs))
        _write(app, "docs/tech-stack/keep.md", "app\n")
        plan = _plan(app, clone, work)
        assert plan["split_removed"] == []
        assert not any(item["kind"] == "split" for item in plan["changes"])
    finally:
        temp.cleanup()


def test_plan_schema_v2_and_lock_stays_v1() -> None:
    assert UPDATE.SCHEMA_VERSION == 2
    assert UPDATE.LOCK_SCHEMA_VERSION == 1
    app, clone, work, temp = _fixture()
    try:
        plan = _plan(app, clone, work)
        assert plan["schema_version"] == 2
        lock = (work / ".cursor/agentic-workflow-update.lock.yaml").read_text(encoding="utf-8")
        assert lock.startswith("version: 1\n")
        assert "kit_body" not in lock
        assert not any(
            item["path"].startswith(str(FOUNDATION_SKILL)) for item in plan["catalog"]
        )
        UPDATE._validate_plan(plan, app, plan["plan_digest"])
        UPDATE._apply_plan(plan)
        loaded = UPDATE._load_lock(app, clone)
        assert loaded is not None and loaded["kit_revision"] == _revision(clone)
    finally:
        temp.cleanup()


def _write_stub_runner(app: Path) -> None:
    runner = app / UPDATE.POST_APPLY_RUNNER
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_text(
        "import json, os, sys\n"
        "with open('seen.json', 'w', encoding='utf-8') as stream:\n"
        "    json.dump({'argv': sys.argv[1:], 'bytecode': os.environ.get('PYTHONDONTWRITEBYTECODE'),"
        " 'cwd': os.getcwd()}, stream)\n"
        "sys.exit(int(os.environ.get('STUB_EXIT', '0')))\n",
        encoding="utf-8",
    )


def test_post_apply_check_runs_check_only_in_app() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-post-check-") as temp_dir:
        app = Path(temp_dir) / "app"
        app.mkdir()
        try:
            UPDATE._run_post_apply_check(app)
        except UPDATE.UpdateError as exc:
            assert "KU-KITBODY-001" in str(exc)
        else:
            raise AssertionError("runner が無いのに post-apply check が成功した")
        _write_stub_runner(app)
        UPDATE._run_post_apply_check(app)
        seen = json.loads((app / "seen.json").read_text(encoding="utf-8"))
        assert seen["argv"] == ["check"], seen
        assert seen["bytecode"] == "1", seen
        assert Path(seen["cwd"]).resolve() == app.resolve(), seen
        for exit_code, expected in (("1", 1), ("2", 2)):
            with patch.dict(os.environ, {"STUB_EXIT": exit_code}):
                try:
                    UPDATE._run_post_apply_check(app)
                except UPDATE.CommandUpdateError as exc:
                    assert exc.exit_code == expected
                else:
                    raise AssertionError(f"check の exit {exit_code} が成功になった")


def test_post_apply_check_failure_restores_app_and_leaves_host() -> None:
    app, clone, work, temp = _fixture()
    try:
        host = Path(temp.name) / "host"
        _write(host, "agentic-workflow-update/SKILL.md", "old-host\n")
        plan = _plan(app, clone, work)
        plan["post_apply_check"] = True
        with (
            patch.dict(os.environ, {"AGENTIC_WORKFLOW_UPDATE_HOME": str(host)}),
            patch.object(
                UPDATE, "_run_post_apply_check", side_effect=UPDATE.UpdateError("drift detected")
            ),
            patch.object(
                UPDATE, "_stage_host_updater", side_effect=AssertionError("host に触れた")
            ),
            patch.object(
                UPDATE, "_run_application_validation", side_effect=AssertionError("gate に進んだ")
            ),
        ):
            try:
                UPDATE._apply_transaction(plan)
            except UPDATE.UpdateError as exc:
                assert "drift detected" in str(exc)
            else:
                raise AssertionError("check 失敗が適用成功になった")
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v1\n"
        assert (host / "agentic-workflow-update/SKILL.md").read_text(encoding="utf-8") == "old-host\n"
        assert not list(host.glob(".agentic-workflow-update.previous.*"))
    finally:
        temp.cleanup()


def test_post_apply_check_runs_before_gate_and_host() -> None:
    app, clone, work, temp = _fixture()
    try:
        host = Path(temp.name) / "host"
        plan = _plan(app, clone, work)
        plan["post_apply_check"] = True
        calls: list[str] = []
        real_gate = UPDATE._run_application_validation

        def gate(*args, **kwargs):
            calls.append("gate")
            return real_gate(*args, **kwargs)

        with (
            patch.dict(os.environ, {"AGENTIC_WORKFLOW_UPDATE_HOME": str(host)}),
            patch.object(
                UPDATE, "_run_post_apply_check", side_effect=lambda root: calls.append(f"check:{root}")
            ),
            patch.object(UPDATE, "_run_application_validation", side_effect=gate),
        ):
            UPDATE._apply_transaction(plan)
        assert calls == [f"check:{app.resolve()}", "gate"], calls
        assert (app / "AGENTS.md").read_text(encoding="utf-8") == "generated-v2\n"
        assert (host / "agentic-workflow-update/SKILL.md").is_file()
    finally:
        temp.cleanup()


def test_install_update_skill_skips_only_when_source_absent_and_implicit() -> None:
    with tempfile.TemporaryDirectory(prefix="kit-update-no-updater-") as temp_dir:
        base = Path(temp_dir)
        skill_dir = base / ".cursor/skills/agentic-workflow-foundation"
        skill_dir.mkdir(parents=True)
        host = base / "host"
        with patch.object(RUNNER, "SKILL_DIR", str(skill_dir)):
            assert RUNNER._install_update_skill(str(host), skip_if_source_absent=True) == 0
            assert not host.exists()
            assert RUNNER._install_update_skill(str(host)) == 2
            assert not (host / "agentic-workflow-update").exists()


def test_generate_passes_skip_flag_only_without_explicit_host() -> None:
    def run(extra: list[str]) -> object:
        install = patch.object(RUNNER, "_install_update_skill", return_value=0)
        with (
            patch.object(RUNNER, "_migrate_root_manifest_file", return_value=0),
            patch.object(RUNNER, "_cleanup_legacy_workflow_docs", return_value=0),
            patch.object(RUNNER, "_cleanup_legacy_skill_dir", return_value=0),
            patch.object(RUNNER, "_cleanup_legacy_decisions_record", return_value=0),
            patch.object(RUNNER, "_cleanup_legacy_workflow_triage", return_value=0),
            patch.object(RUNNER, "run_engine", return_value=0),
            patch.object(RUNNER, "resolved_manifest", return_value={}),
            patch.object(RUNNER, "prepare_skill_dir", side_effect=lambda path, manifest: path),
            install as mocked,
        ):
            # root manifest は存在するファイルを指す（bootstrap 専用経路に入らないため）。
            assert RUNNER.main(["generate", "--root-manifest", __file__, *extra]) == 0
        return mocked

    implicit = run([])
    implicit.assert_called_once_with(None, skip_if_source_absent=True)
    explicit = run(["--update-skill-home", "/tmp/host-home-for-test"])
    explicit.assert_called_once_with("/tmp/host-home-for-test", skip_if_source_absent=False)


def main() -> int:
    tests = (
        ("public fetch contract", test_public_fetch_contract),
        ("consumer plan and apply", test_consumer_plan_and_apply_sync_kit_body_except_updater),
        ("empty kit body roots", test_empty_kit_body_roots_leave_kit_body_untouched),
        ("kit body add update delete", test_kit_body_add_update_delete_and_mode),
        ("kit body deletion needs delete", test_kit_body_deletion_without_delete_approval_cannot_apply),
        ("kit body excludes updater", test_kit_body_never_includes_updater_or_outside_roots),
        ("kit body catalog roots", test_kit_body_catalog_rejects_kit_roots),
        ("kit body clone root missing", test_kit_body_clone_root_missing_is_fatal),
        ("kit body bytecode and symlink", test_kit_body_ignores_bytecode_and_rejects_symlinks),
        ("kit body plan roots", test_plan_kit_body_changes_must_stay_inside_plan_roots),
        ("kit body mirror work", test_mirror_kit_body_makes_work_equal_to_clone),
        ("split follows work", test_split_output_follows_work_result_not_clone),
        ("split subdirectory", test_split_output_directory_with_subdirectory_is_a_plan_failure),
        ("split without work output", test_split_without_work_output_is_not_compared),
        ("plan schema v2 lock v1", test_plan_schema_v2_and_lock_stays_v1),
        ("post apply check", test_post_apply_check_runs_check_only_in_app),
        ("post apply check failure", test_post_apply_check_failure_restores_app_and_leaves_host),
        ("post apply check order", test_post_apply_check_runs_before_gate_and_host),
        ("install update skill skip", test_install_update_skill_skips_only_when_source_absent_and_implicit),
        ("generate skip flag", test_generate_passes_skip_flag_only_without_explicit_host),
        ("lock without cursor dir", test_plan_creates_lock_when_cursor_directory_is_absent),
        ("resolved catalog", test_resolved_catalog_applies_overlay_features),
        ("split mode catalog", test_split_mode_is_not_in_catalog_and_blueprint_is_denied),
        ("initial adopt", test_initial_adopt_does_not_infer_orphans),
        ("lock orphan", test_lock_catalog_detects_removed_managed_output),
        ("retire keep", test_retire_keep_leaves_file_and_drops_lock),
        ("retire delete", test_retire_delete_removes_only_former_managed_file),
        ("retire rename", test_retire_delete_renames_by_removing_old_path_only),
        ("retire without targets", test_retire_without_targets_is_fatal),
        ("split index paths", test_split_index_paths_come_only_from_split_outputs),
        ("render to split transfer", test_render_to_split_transfer_is_not_orphan),
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
        ("skill contract", test_skill_contract_mirrors_kit_body_except_updater),
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
