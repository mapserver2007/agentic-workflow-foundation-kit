#!/usr/bin/env python3
"""session-progress-append helper の契約・flock・生成カタログを検査する。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
ROOT = SKILL_DIR.parent.parent.parent
TEMPLATE = SKILL_DIR / "templates" / "hooks" / "session-progress-append.sh.template"
EMITTER_TEMPLATE = SKILL_DIR / "templates" / "hooks" / "session-progress-emitter.sh.template"
HOOKS_TEMPLATE = SKILL_DIR / "templates" / "hooks.json.template"
README_TEMPLATE = SKILL_DIR / "templates" / "hooks" / "README.md.template"
MANIFEST = SKILL_DIR / "manifest.yaml"
PR_REVIEW_TEMPLATE = SKILL_DIR / "templates" / "docs" / "agent-tasks" / "agent-workflow" / "05-pr-review.md.template"
ORCHESTRATOR_TEMPLATE = SKILL_DIR / "templates" / "skills" / "workflow-orchestrator" / "SKILL.md.template"
CODE_REVIEW_TEMPLATE = SKILL_DIR / "templates" / "skills" / "agent-code-review" / "SKILL.md.template"
MAINT_DOCS_TEMPLATE = SKILL_DIR / "templates" / "skills" / "maintenance-docs-workflow" / "SKILL.md.template"
MAINT_GOTCHAS_TEMPLATE = SKILL_DIR / "templates" / "skills" / "maintenance-gotchas-workflow" / "SKILL.md.template"
BASH_EXECUTABLE = "/bin/bash"
DEFAULT_SUMMARY = "PRレビュー検証開始"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def run_helper(
    script: Path,
    root: Path,
    args: list[str],
    *,
    session_id: str | None = "test-append-001",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CURSOR_PROJECT_DIR"] = str(root)
    if session_id is None:
        env.pop("CTX_BUDGET_SESSION_ID", None)
    else:
        env["CTX_BUDGET_SESSION_ID"] = session_id
    if extra_env:
        env.update(extra_env)
    return subprocess.run(  # noqa: S603 - Runs a controlled temporary test fixture.
        [BASH_EXECUTABLE, str(script), *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _install_script(root: Path, name: str, source: Path) -> Path:
    script = root / name
    script.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o700)
    return script


def _progress_path(root: Path, session_id: str) -> Path:
    return root / ".cursor" / ".session" / f"{session_id}.progress.jsonl"


def test_invalid_session_is_noop() -> None:
    with tempfile.TemporaryDirectory(prefix="progress-append-invalid-") as tmp:
        root = Path(tmp)
        (root / ".cursor" / ".session").mkdir(parents=True)
        script = _install_script(root, "session-progress-append.sh", TEMPLATE)
        args = ["--kind", "review_start", "--extra", '{"gate_id":"review"}']

        missing = run_helper(script, root, args, session_id=None)
        assert_equal(missing.returncode, 0, "missing session exit")
        assert_equal(missing.stdout, "{}\n", "missing session stdout")
        assert not any(_progress_path(root, ".").parent.glob("*.progress.jsonl")), "missing session wrote"

        fallback = run_helper(
            script,
            root,
            [*args, "--session-id", "cli-fallback-001"],
            session_id=None,
        )
        assert_equal(fallback.returncode, 0, "CLI fallback exit")
        assert_equal(fallback.stdout, "{}\n", "CLI fallback stdout")
        assert not (_progress_path(root, "cli-fallback-001")).exists(), "CLI session ID must not write"

        unsafe = run_helper(script, root, args, session_id="../unsafe")
        assert_equal(unsafe.returncode, 0, "unsafe session exit")
        assert_equal(unsafe.stdout, "{}\n", "unsafe session stdout")
        assert not any((root / ".cursor" / ".session").rglob("*.progress.jsonl")), "unsafe session wrote"


def test_valid_append_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="progress-append-valid-") as tmp:
        root = Path(tmp)
        (root / ".cursor" / ".session").mkdir(parents=True)
        script = _install_script(root, "session-progress-append.sh", TEMPLATE)
        result = run_helper(
            script,
            root,
            ["--kind", "review_start", "--extra", '{"gate_id":"review"}'],
        )
        assert_equal(result.returncode, 0, "valid exit")
        assert_equal(result.stdout, "{}\n", "valid stdout")
        rows = [
            json.loads(line)
            for line in _progress_path(root, "test-append-001").read_text(encoding="utf-8").splitlines()
        ]
        assert_equal(len(rows), 1, "row count")
        row = rows[0]
        assert set(("at", "session_id", "kind", "bytes", "summary", "extra")).issubset(row)
        assert_equal(row["kind"], "review_start", "kind")
        assert_equal(row["session_id"], "test-append-001", "session_id")
        assert_equal(row["summary"], DEFAULT_SUMMARY, "default summary")
        assert_equal(row["bytes"], len(DEFAULT_SUMMARY.encode("utf-8")), "bytes")
        assert_equal(row["extra"], {"gate_id": "review"}, "extra")
        assert "skill" not in row["extra"]
        assert "mode" not in row["extra"]

        custom = run_helper(
            script,
            root,
            [
                "--kind",
                "review_start",
                "--summary",
                "開始",
                "--extra",
                '{"gate_id":"review","campaign":"c1","pr":"https://example.invalid/pr/1"}',
            ],
            session_id="test-append-002",
        )
        assert_equal(custom.returncode, 0, "custom exit")
        custom_row = json.loads(_progress_path(root, "test-append-002").read_text(encoding="utf-8").splitlines()[0])
        assert_equal(custom_row["summary"], "開始", "custom summary")
        assert_equal(custom_row["bytes"], len("開始".encode("utf-8")), "custom bytes")
        assert_equal(custom_row["extra"]["gate_id"], "review", "custom gate_id")
        assert_equal(custom_row["extra"]["campaign"], "c1", "campaign")
        assert_equal(custom_row["extra"]["pr"], "https://example.invalid/pr/1", "pr")


def test_invalid_schema_is_noop() -> None:
    with tempfile.TemporaryDirectory(prefix="progress-append-schema-") as tmp:
        root = Path(tmp)
        (root / ".cursor" / ".session").mkdir(parents=True)
        script = _install_script(root, "session-progress-append.sh", TEMPLATE)
        cases = (
            ["--kind", "prompt", "--extra", '{"gate_id":"review"}'],
            ["--kind", "review_start", "--extra", '{"gate_id":"other"}'],
            ["--kind", "review_start", "--extra", "[]"],
            ["--kind", "review_start", "--extra", '{"gate_id":"review","skill":"agent-code-review"}'],
            ["--kind", "review_start", "--extra", '{"gate_id":"review","mode":"A"}'],
            ["--kind", "review_start"],
        )
        for index, args in enumerate(cases):
            result = run_helper(script, root, args, session_id=f"schema-{index}")
            assert_equal(result.returncode, 0, f"schema {index} exit")
            assert_equal(result.stdout, "{}\n", f"schema {index} stdout")
            assert not _progress_path(root, f"schema-{index}").exists(), f"schema {index} wrote"


def test_shared_flock_with_emitter() -> None:
    if shutil.which("flock") is None:
        return

    with tempfile.TemporaryDirectory(prefix="progress-append-flock-") as tmp:
        root = Path(tmp)
        (root / ".cursor" / ".session").mkdir(parents=True)
        helper = _install_script(root, "session-progress-append.sh", TEMPLATE)
        emitter = _install_script(root, "session-progress-emitter.sh", EMITTER_TEMPLATE)
        env = dict(os.environ)
        env.update({
            "CURSOR_PROJECT_DIR": str(root),
            "CTX_BUDGET_SESSION_ID": "shared-001",
        })
        processes: list[subprocess.Popen[str]] = []
        for index in range(16):
            processes.append(subprocess.Popen(  # noqa: S603
                [BASH_EXECUTABLE, str(helper), "--kind", "review_start", "--extra", '{"gate_id":"review"}',
                 "--summary", f"helper-{index}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            ))
            emitter_proc = subprocess.Popen(  # noqa: S603
                [BASH_EXECUTABLE, str(emitter)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            assert emitter_proc.stdin is not None
            emitter_proc.stdin.write(json.dumps({"prompt": f"emitter-{index}"}))
            emitter_proc.stdin.close()
            processes.append(emitter_proc)

        for process in processes:
            process.wait(timeout=5)
            assert_equal(process.returncode, 0, "shared flock exit")
            assert process.stdout is not None
            assert_equal(process.stdout.read(), "{}\n", "shared flock stdout")

        rows = [
            json.loads(line)
            for line in _progress_path(root, "shared-001").read_text(encoding="utf-8").splitlines()
        ]
        assert_equal(len(rows), 32, "shared flock row count")
        kinds = {row["kind"] for row in rows}
        assert kinds == {"review_start", "prompt"}, f"unexpected kinds: {kinds}"


def test_generation_catalog_and_hooks_json() -> None:
    manifest = MANIFEST.read_text(encoding="utf-8")
    for needle in (
        ".cursor/hooks/session-progress-append.sh",
        "hooks/session-progress-append.sh.template",
        "executable: true",
        "review_start",
        "kind=review_start",
    ):
        assert needle in manifest, f"manifest missing {needle}"

    block_start = manifest.find("path: .cursor/hooks/session-progress-append.sh")
    assert block_start != -1, "append helper output missing"
    block = manifest[block_start:block_start + 400]
    assert "template: hooks/session-progress-append.sh.template" in block
    assert "executable: true" in block
    assert "review_start" in block

    hooks = HOOKS_TEMPLATE.read_text(encoding="utf-8")
    assert "session-progress-append.sh" not in hooks, "helper must not be registered in hooks.json"

    readme = README_TEMPLATE.read_text(encoding="utf-8")
    assert "review_start" in readme, "README missing review_start"
    assert "helper 検証チェックリスト" in readme, "README missing helper checklist"
    assert "Step ⑤" in readme and "親境界" in readme, "README missing Step ⑤ parent boundary"


def test_workflow_boundary_contract() -> None:
    pr_review = PR_REVIEW_TEMPLATE.read_text(encoding="utf-8")
    for needle in (
        "session-progress-append.sh",
        "kind=review_start",
        "PR URL 受領後",
        "workflow-orchestrator",
        "単独起動の `agent-code-review`",
        "maintenance-docs-workflow",
        "maintenance-gotchas-workflow",
    ):
        assert needle in pr_review, f"05-pr-review template missing {needle}"

    orchestrator = ORCHESTRATOR_TEMPLATE.read_text(encoding="utf-8")
    assert "session-progress-append.sh" in orchestrator, "orchestrator missing helper"
    assert "kind=review_start" in orchestrator, "orchestrator missing kind"
    assert "PR URL 受領後" in orchestrator, "orchestrator missing PR URL order"
    step5 = orchestrator.split("### Step ⑤: PR レビュー検証", 1)[1].split("### Step ⑥", 1)[0]
    helper_at = step5.find("session-progress-append.sh")
    review_at = step5.find("レビュー指摘を取得")
    assert helper_at != -1 and review_at != -1 and helper_at < review_at, (
        "orchestrator Step ⑤ must emit before review delegation"
    )

    for path, label in (
        (CODE_REVIEW_TEMPLATE, "agent-code-review"),
        (MAINT_DOCS_TEMPLATE, "maintenance-docs-workflow"),
        (MAINT_GOTCHAS_TEMPLATE, "maintenance-gotchas-workflow"),
    ):
        text = path.read_text(encoding="utf-8")
        assert "session-progress-append.sh" not in text, f"{label} must not own append helper"
        assert "kind=review_start" not in text, f"{label} must not own review_start"


def main() -> int:
    tests = (
        test_invalid_session_is_noop,
        test_valid_append_contract,
        test_invalid_schema_is_noop,
        test_shared_flock_with_emitter,
        test_generation_catalog_and_hooks_json,
        test_workflow_boundary_contract,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_session_progress_append] FAIL: {test.__name__}: {exc}")
            return 1
    print(f"[test_session_progress_append] PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
