#!/usr/bin/env python3
"""review-start gate の prompt/session/PR/write/readback 境界を回帰検査する。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
GATE_TEMPLATE = (
    SKILL_DIR
    / "templates"
    / "skills"
    / "session-handover"
    / "scripts"
    / "review-start-gate.sh.template"
)
WRITER_TEMPLATE = SKILL_DIR / "templates" / "hooks" / "session-progress-append.sh.template"
WORKFLOW_TEMPLATE = (
    SKILL_DIR
    / "templates"
    / "skills"
    / "workflow-orchestrator"
    / "SKILL.md.template"
)
PR_REVIEW_TEMPLATE = (
    SKILL_DIR
    / "templates"
    / "docs"
    / "agent-tasks"
    / "agent-workflow"
    / "05-pr-review.md.template"
)
REAL_GATE_DIR = SKILL_DIR.parent / "session-handover" / "scripts"
FIXTURES = SKILL_DIR / "fixtures" / "artifacts"
BASH = "/bin/bash"
PR = "https://github.com/owner/repo/pull/1"
CAMPAIGN = "TICKET-1-example"


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)


def _setup() -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    temporary = tempfile.TemporaryDirectory(prefix="review-start-")
    root = Path(temporary.name)
    scripts = root / ".cursor" / "skills" / "session-handover" / "scripts"
    gate_text = GATE_TEMPLATE.read_text(encoding="utf-8").replace(
        "{{framework.review_start.prompt_max_age_seconds}}",
        "600",
    )
    _write_executable(scripts / "review-start-gate.sh", gate_text)
    _write_executable(
        scripts / "workflow-gate.sh",
        """#!/usr/bin/env bash
set -u
[[ "${1:-}" == "step4" ]] || exit 2
printf '%s\n' "$*" >> "${CURSOR_PROJECT_DIR}/step4.calls"
exit "${STEP4_EXIT:-0}"
""",
    )
    _write_executable(
        root / ".cursor" / "hooks" / "session-progress-append.sh",
        WRITER_TEMPLATE.read_text(encoding="utf-8"),
    )
    report = root / "docs" / "agent-tasks" / "reports" / f"{CAMPAIGN}.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "# Report\n\n## 10. 完了チェック\n\n"
        "- [x] 実装完了\n"
        "- [x] テスト完了\n"
        "- [x] コードゲート通過\n"
        f"- review-pr-url: {PR}\n",
        encoding="utf-8",
    )
    (root / ".cursor" / ".session").mkdir(parents=True)
    return temporary, root, report


def _prompt_event(
    session_id: str,
    *,
    pr_urls: list[str] | None = None,
    at: str | None = None,
    prompt: str = PR,
) -> dict:
    timestamp = at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "at": timestamp,
        "session_id": session_id,
        "kind": "prompt",
        "bytes": min(len(prompt.encode("utf-8")), 1000),
        "summary": prompt[:1000],
        "extra": {
            "hook_event_name": "beforeSubmitPrompt",
            "pr_urls": [PR] if pr_urls is None else pr_urls,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        },
    }


def _write_progress(root: Path, session_id: str, events: list[dict]) -> Path:
    path = root / ".cursor" / ".session" / f"{session_id}.progress.jsonl"
    path.write_text(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
    )
    return path


def _run(
    root: Path,
    report: Path,
    *,
    pr: str = PR,
    step4_exit: int = 0,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CURSOR_PROJECT_DIR"] = str(root)
    env["STEP4_EXIT"] = str(step4_exit)
    env.pop("CTX_BUDGET_SESSION_ID", None)
    return subprocess.run(
        [
            BASH,
            str(root / ".cursor" / "skills" / "session-handover" / "scripts" / "review-start-gate.sh"),
            "--report",
            str(report),
            "--pr",
            pr,
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _append_event(path: Path, event: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def test_success_without_agent_shell_session_and_idempotency() -> None:
    temporary, root, report = _setup()
    with temporary:
        progress = _write_progress(root, "hook-session-1", [_prompt_event("hook-session-1")])
        first = _run(
            root,
            report,
            pr="https://GitHub.com/Owner/Repo/pull/0001/?ignored=yes#fragment",
        )
        assert first.returncode == 0, first.stderr
        rows = _rows(progress)
        review_rows = [row for row in rows if row["kind"] == "review_start"]
        assert len(review_rows) == 1
        review = review_rows[0]
        assert review["session_id"] == "hook-session-1"
        assert review["extra"]["gate_id"] == "review"
        assert review["extra"]["campaign"] == CAMPAIGN
        assert review["extra"]["pr"] == PR
        assert review["extra"]["source"] == "review-start-gate"
        assert len(review["extra"]["review_go_id"]) == 64

        second = _run(root, report)
        assert second.returncode == 0, second.stderr
        assert "G-REVIEW-START-IDEMPOTENCY-001" in second.stdout
        assert len([row for row in _rows(progress) if row["kind"] == "review_start"]) == 1

        _append_event(progress, _prompt_event("hook-session-1", prompt=f"再送 {PR}"))
        third = _run(root, report)
        assert third.returncode == 0, third.stderr
        review_rows = [row for row in _rows(progress) if row["kind"] == "review_start"]
        assert len(review_rows) == 2
        assert len({row["extra"]["review_go_id"] for row in review_rows}) == 2


def test_prompt_and_session_failures() -> None:
    cases: list[tuple[str, callable]] = []

    def missing(root: Path) -> None:
        return None

    def mismatch(root: Path) -> None:
        _write_progress(root, "s1", [_prompt_event("s1", pr_urls=["https://github.com/owner/repo/pull/2"])])

    def multiple(root: Path) -> None:
        _write_progress(root, "s1", [_prompt_event("s1")])
        _write_progress(root, "s2", [_prompt_event("s2")])

    def expired(root: Path) -> None:
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_progress(root, "s1", [_prompt_event("s1", at=old)])

    def retired(root: Path) -> None:
        _write_progress(root, "s1", [_prompt_event("s1")])
        (root / ".cursor" / ".session" / "handoff-s1.md").write_text("# retired\n", encoding="utf-8")

    def red_state(root: Path) -> None:
        _write_progress(root, "s1", [_prompt_event("s1")])
        (root / ".cursor" / ".session" / "s1.json").write_text(
            '{"session_id":"s1","last_warning_level":"red"}\n',
            encoding="utf-8",
        )

    def filename_mismatch(root: Path) -> None:
        _write_progress(root, "s1", [_prompt_event("other")])

    def old_review_only(root: Path) -> None:
        _write_progress(
            root,
            "s1",
            [{
                "at": "2026-01-01T00:00:00Z",
                "session_id": "s1",
                "kind": "review_start",
                "bytes": 0,
                "summary": "old",
                "extra": {
                    "gate_id": "review",
                    "campaign": CAMPAIGN,
                    "pr": PR,
                    "review_go_id": "a" * 64,
                    "source": "review-start-gate",
                },
            }],
        )

    cases.extend([
        ("missing", missing),
        ("mismatch", mismatch),
        ("multiple", multiple),
        ("expired", expired),
        ("retired", retired),
        ("red-state", red_state),
        ("filename-mismatch", filename_mismatch),
        ("old-review-only", old_review_only),
    ])
    for label, prepare in cases:
        temporary, root, report = _setup()
        with temporary:
            prepare(root)
            before_review_count = sum(
                row.get("kind") == "review_start"
                for path in (root / ".cursor" / ".session").glob("*.progress.jsonl")
                for row in _rows(path)
            )
            result = _run(root, report)
            expected = 2 if label == "filename-mismatch" else 1
            assert result.returncode == expected, (label, result.stdout, result.stderr)
            after_review_count = sum(
                row.get("kind") == "review_start"
                for path in (root / ".cursor" / ".session").glob("*.progress.jsonl")
                for row in _rows(path)
            )
            assert after_review_count == before_review_count, label


def test_report_step4_and_writer_fail_closed() -> None:
    temporary, root, report = _setup()
    with temporary:
        progress = _write_progress(root, "s1", [_prompt_event("s1")])
        report.write_text("# Report\n\n## 10. 完了チェック\n\n- review-pr-url:\n", encoding="utf-8")
        marker = _run(root, report)
        assert marker.returncode == 1
        assert "G-REVIEW-START-BIND-001" in marker.stderr

        report.write_text(
            "# Report\n\n## 10. 完了チェック\n\n"
            f"- review-pr-url: {PR}\n"
            f"- review-pr-url: {PR}\n",
            encoding="utf-8",
        )
        duplicate_marker = _run(root, report)
        assert duplicate_marker.returncode == 1
        assert "G-REVIEW-START-BIND-001" in duplicate_marker.stderr

        report.write_text(
            "# Report\n\n## 10. 完了チェック\n\n"
            "- review-pr-url: https://github.com/owner/repo/pull/2\n",
            encoding="utf-8",
        )
        marker_mismatch = _run(root, report)
        assert marker_mismatch.returncode == 1
        assert "G-REVIEW-START-BIND-001" in marker_mismatch.stderr

        report.write_text(
            "# Report\n\n## 10. 完了チェック\n\n"
            f"- review-pr-url: {PR}\n",
            encoding="utf-8",
        )
        for code in (1, 2):
            step4 = _run(root, report, step4_exit=code)
            assert step4.returncode == code
            assert "G-REVIEW-START-STEP4-001" in step4.stderr
            assert not any(row["kind"] == "review_start" for row in _rows(progress))

        writer = root / ".cursor" / "hooks" / "session-progress-append.sh"
        writer.write_text("#!/usr/bin/env bash\nexit 2\n", encoding="utf-8")
        writer.chmod(0o700)
        failed_write = _run(root, report)
        assert failed_write.returncode == 2
        assert "G-REVIEW-START-WRITE-001" in failed_write.stderr
        assert not any(row["kind"] == "review_start" for row in _rows(progress))

        writer.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        writer.chmod(0o700)
        failed_lock = _run(root, report)
        assert failed_lock.returncode == 1
        assert "G-REVIEW-START-LOCK-001" in failed_lock.stderr
        assert not any(row["kind"] == "review_start" for row in _rows(progress))

        writer.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        writer.chmod(0o700)
        failed_readback = _run(root, report)
        assert failed_readback.returncode == 2
        assert "G-REVIEW-START-READBACK-001" in failed_readback.stderr
        assert not any(row["kind"] == "review_start" for row in _rows(progress))


def test_conflicting_id_and_handoff_resend() -> None:
    temporary, root, report = _setup()
    with temporary:
        old_progress = _write_progress(root, "old", [_prompt_event("old")])
        first = _run(root, report)
        assert first.returncode == 0, first.stderr
        rows = _rows(old_progress)
        rows[-1]["extra"]["campaign"] = "wrong"
        _write_progress(root, "old", rows)
        conflict = _run(root, report)
        assert conflict.returncode == 2
        assert "G-REVIEW-START-IDEMPOTENCY-001" in conflict.stderr

    temporary, root, report = _setup()
    with temporary:
        _write_progress(root, "old", [_prompt_event("old")])
        (root / ".cursor" / ".session" / "handoff-consumed-old-1.md").write_text(
            "# consumed\n",
            encoding="utf-8",
        )
        new_progress = _write_progress(root, "new", [_prompt_event("new", prompt=f"再送 {PR}")])
        result = _run(root, report)
        assert result.returncode == 0, result.stderr
        assert any(row["kind"] == "review_start" for row in _rows(new_progress))


def _setup_dispatch_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path, Path, Path]:
    temporary = tempfile.TemporaryDirectory(prefix="review-start-dispatch-")
    root = Path(temporary.name)
    gate_dir = root / ".cursor" / "skills" / "session-handover" / "scripts"
    gate_dir.mkdir(parents=True)
    for name in (
        "workflow-gate.sh",
        "review-start-gate.sh",
        "gate-artifact.py",
        "gate-test.py",
    ):
        shutil.copy2(REAL_GATE_DIR / name, gate_dir / name)
    for path in gate_dir.iterdir():
        path.chmod(0o755)
    writer = root / ".cursor" / "hooks" / "session-progress-append.sh"
    _write_executable(writer, WRITER_TEMPLATE.read_text(encoding="utf-8"))

    foundation_log = root / "foundation-gate.calls"
    _write_executable(
        root / "bin" / "foundation-gate",
        f"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "{foundation_log}"
exit "${{STUB_FOUNDATION_EXIT:-0}}"
""",
    )
    report = root / "docs" / "agent-tasks" / "reports" / f"{CAMPAIGN}.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "## 10. 完了チェック\n"
        "- [x] 実装完了\n"
        "- [x] テスト完了\n"
        "- [x] コードゲート通過\n"
        f"- review-pr-url: {PR}\n",
        encoding="utf-8",
    )
    artifacts = root / ".cursor" / ".artifacts"
    artifacts.mkdir(parents=True)
    shutil.copy2(FIXTURES / "step3-complete.md", artifacts / f"{CAMPAIGN}--step3.md")
    shutil.copy2(FIXTURES / "step4-complete.md", artifacts / f"{CAMPAIGN}--step4.md")
    (root / ".cursor" / ".session").mkdir(parents=True)
    progress = _write_progress(root, "dispatch-session", [_prompt_event("dispatch-session")])
    return temporary, root, report, progress


def _run_dispatch(
    root: Path,
    report: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CURSOR_PROJECT_DIR"] = str(root)
    env.pop("CTX_BUDGET_SESSION_ID", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [
            BASH,
            str(root / ".cursor" / "skills" / "session-handover" / "scripts" / "workflow-gate.sh"),
            "review-start",
            "--report",
            str(report),
            "--pr",
            PR,
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )


def test_workflow_dispatch_with_real_step4_contract() -> None:
    temporary, root, report, progress = _setup_dispatch_fixture()
    with temporary:
        result = _run_dispatch(root, report)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (root / "foundation-gate.calls").read_text(encoding="utf-8").splitlines() == ["self"]
        review_rows = [row for row in _rows(progress) if row["kind"] == "review_start"]
        assert len(review_rows) == 1

    failures = (
        ("missing-step3", 1, lambda root, report: (
            root / ".cursor" / ".artifacts" / f"{CAMPAIGN}--step3.md"
        ).unlink()),
        ("missing-step4", 1, lambda root, report: (
            root / ".cursor" / ".artifacts" / f"{CAMPAIGN}--step4.md"
        ).unlink()),
        ("invalid-step4-gates", 1, lambda root, report: (
            root / ".cursor" / ".artifacts" / f"{CAMPAIGN}--step4.md"
        ).write_text(
            (root / ".cursor" / ".artifacts" / f"{CAMPAIGN}--step4.md")
            .read_text(encoding="utf-8")
            .replace("  gen: 0", "  gen: PASS"),
            encoding="utf-8",
        )),
        ("incomplete-report", 1, lambda root, report: report.write_text(
            "## 10. 完了チェック\n"
            "- [ ] 実装完了\n"
            "- [x] テスト完了\n"
            "- [x] コードゲート通過\n"
            f"- review-pr-url: {PR}\n",
            encoding="utf-8",
        )),
    )
    for label, expected, mutate in failures:
        temporary, root, report, progress = _setup_dispatch_fixture()
        with temporary:
            mutate(root, report)
            result = _run_dispatch(root, report)
            assert result.returncode == expected, (label, result.stdout, result.stderr)
            assert not any(row["kind"] == "review_start" for row in _rows(progress)), label

    for exit_code in ("1", "2"):
        temporary, root, report, progress = _setup_dispatch_fixture()
        with temporary:
            result = _run_dispatch(root, report, extra_env={"STUB_FOUNDATION_EXIT": exit_code})
            assert result.returncode == int(exit_code), result.stdout + result.stderr
            assert not any(row["kind"] == "review_start" for row in _rows(progress))


def test_caller_simulation_invokes_review_only_after_pass() -> None:
    caller = """#!/usr/bin/env bash
set -u
workflow_gate="$1"
report="$2"
pr="$3"
review="$4"
"$workflow_gate" review-start --report "$report" --pr "$pr" || exit $?
exec "$review"
"""
    temporary, root, report, _ = _setup_dispatch_fixture()
    with temporary:
        caller_path = root / "caller.sh"
        review_log = root / "review.calls"
        review = root / "mock-review.sh"
        _write_executable(caller_path, caller)
        _write_executable(review, f"#!/usr/bin/env bash\nprintf 'called\\n' >> \"{review_log}\"\n")
        result = subprocess.run(
            [
                BASH,
                str(caller_path),
                str(root / ".cursor" / "skills" / "session-handover" / "scripts" / "workflow-gate.sh"),
                str(report),
                PR,
                str(review),
            ],
            cwd=root,
            env=dict(os.environ, CURSOR_PROJECT_DIR=str(root)),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert review_log.read_text(encoding="utf-8").splitlines() == ["called"]

    temporary, root, report, _ = _setup_dispatch_fixture()
    with temporary:
        caller_path = root / "caller.sh"
        review_log = root / "review.calls"
        review = root / "mock-review.sh"
        _write_executable(caller_path, caller)
        _write_executable(review, f"#!/usr/bin/env bash\nprintf 'called\\n' >> \"{review_log}\"\n")
        (root / ".cursor" / ".artifacts" / f"{CAMPAIGN}--step3.md").unlink()
        result = subprocess.run(
            [
                BASH,
                str(caller_path),
                str(root / ".cursor" / "skills" / "session-handover" / "scripts" / "workflow-gate.sh"),
                str(report),
                PR,
                str(review),
            ],
            cwd=root,
            env=dict(os.environ, CURSOR_PROJECT_DIR=str(root)),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert not review_log.exists()


def test_static_caller_stop_contract() -> None:
    orchestrator = WORKFLOW_TEMPLATE.read_text(encoding="utf-8")
    step5 = orchestrator.split("### Step ⑤: PR レビュー検証", 1)[1].split("### Step ⑥", 1)[0]
    assert "workflow-gate.sh review-start" in step5
    assert "exit 0 を確認できた場合だけレビューを委譲" in step5
    assert step5.find("workflow-gate.sh review-start") < step5.find("レビュー指摘を取得")
    assert "Mode B" in step5 and "standalone" in step5
    pr_doc = PR_REVIEW_TEMPLATE.read_text(encoding="utf-8")
    assert "review-pr-url" in pr_doc
    assert "session-progress-append.sh" not in pr_doc
    assert "review_start" in pr_doc


def main() -> int:
    tests = (
        test_success_without_agent_shell_session_and_idempotency,
        test_prompt_and_session_failures,
        test_report_step4_and_writer_fail_closed,
        test_conflicting_id_and_handoff_resend,
        test_workflow_dispatch_with_real_step4_contract,
        test_caller_simulation_invokes_review_only_after_pass,
        test_static_caller_stop_contract,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_review_start_gate] FAIL: {test.__name__}: {exc}")
            return 1
    print(f"[test_review_start_gate] PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
