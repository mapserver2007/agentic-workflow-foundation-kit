#!/usr/bin/env python3
"""Envelope 必須検査の回帰テスト。

orchestrator_envelope_force 計画に基づき、以下を検証する:

gate-artifact.py:
  - --expect-step / --expect-status 一致で PASS (exit 0)
  - --expect-step 不一致で FAIL (exit 1)
  - --expect-status 不一致で FAIL (exit 1)
  - オプションなしの既存検査は維持（complete / incomplete / blocked / fatal 全対応）

workflow-gate.sh step2-report:
  - step1/step2 envelope 欠落で exit 1
  - 有効な step1/step2 + report_path 一致で gate-report.py へ進む

workflow-gate.sh step4:
  - step3/step4 envelope 欠落で verify 未実行・exit 1
  - report-file 省略時の単一解決と 0件/複数件の exit 2
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent

_gate_artifact_path = (
    ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "gate-artifact.py"
)
_gate_report_path = (
    ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "gate-report.py"
)

FIXTURES_DIR = HERE.parent / "fixtures" / "artifacts"
REPORT_FIXTURES_DIR = HERE.parent / "fixtures" / "reports"


def _load_gate_artifact():
    spec = importlib.util.spec_from_file_location("gate_artifact", str(_gate_artifact_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_gate_report():
    spec = importlib.util.spec_from_file_location("gate_report", str(_gate_report_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_gate_artifact_cli(args: list[str]) -> int:
    """gate-artifact.py を CLI として実行し exit code を返す。"""
    result = subprocess.run(
        [sys.executable, str(_gate_artifact_path)] + args,
        capture_output=True, text=True,
    )
    return result.returncode


# === gate-artifact.py の --expect-step / --expect-status テスト ===

def test_expect_step_match():
    """--expect-step step1 が step1 envelope に対して PASS。"""
    fixture = str(FIXTURES_DIR / "step1-complete.md")
    rc = _run_gate_artifact_cli([fixture, "--expect-step", "step1", "--format=json"])
    assert rc == 0, f"step1 envelope + --expect-step step1 should PASS (got {rc})"


def test_expect_step_mismatch():
    """--expect-step step2 が step1 envelope に対して FAIL。"""
    fixture = str(FIXTURES_DIR / "step1-complete.md")
    rc = _run_gate_artifact_cli([fixture, "--expect-step", "step2", "--format=json"])
    assert rc == 1, f"step1 envelope + --expect-step step2 should FAIL (got {rc})"


def test_expect_status_match():
    """--expect-status complete が complete envelope に対して PASS。"""
    fixture = str(FIXTURES_DIR / "step2-complete.md")
    rc = _run_gate_artifact_cli([fixture, "--expect-status", "complete", "--format=json"])
    assert rc == 0, f"complete envelope + --expect-status complete should PASS (got {rc})"


def test_expect_status_mismatch():
    """--expect-status incomplete が complete envelope に対して FAIL。"""
    fixture = str(FIXTURES_DIR / "step2-complete.md")
    rc = _run_gate_artifact_cli([fixture, "--expect-status", "incomplete", "--format=json"])
    assert rc == 1, f"complete envelope + --expect-status incomplete should FAIL (got {rc})"


def test_expect_both_match():
    """--expect-step step3 --expect-status complete が step3/complete に対して PASS。"""
    fixture = str(FIXTURES_DIR / "step3-complete.md")
    rc = _run_gate_artifact_cli([
        fixture, "--expect-step", "step3", "--expect-status", "complete", "--format=json",
    ])
    assert rc == 0, f"step3/complete + both expect should PASS (got {rc})"


def test_expect_both_step_mismatch():
    """--expect-step step4 が step3 envelope に対して FAIL（status は一致）。"""
    fixture = str(FIXTURES_DIR / "step3-complete.md")
    rc = _run_gate_artifact_cli([
        fixture, "--expect-step", "step4", "--expect-status", "complete", "--format=json",
    ])
    assert rc == 1, f"step3 + --expect-step step4 should FAIL (got {rc})"


def test_no_expect_options_backward_compatible():
    """オプションなしの既存動作が維持される（complete → PASS）。"""
    fixture = str(FIXTURES_DIR / "step4-complete.md")
    rc = _run_gate_artifact_cli([fixture, "--format=json"])
    assert rc == 0, f"existing complete fixture should still PASS (got {rc})"


def test_no_expect_options_blocked_with_reason():
    """オプションなしで blocked+reason が引き続き PASS。"""
    fixture = str(FIXTURES_DIR / "blocked-with-reason.md")
    rc = _run_gate_artifact_cli([fixture, "--format=json"])
    assert rc == 0, f"blocked+reason should still PASS without expect options (got {rc})"


def test_expect_function_api():
    """check_artifact() の関数 API で expect_step/expect_status を渡せること。"""
    mod = _load_gate_artifact()
    fixture = str(FIXTURES_DIR / "step1-complete.md")
    rc = mod.check_artifact(fixture, json_mode=True, expect_step="step1", expect_status="complete")
    assert rc == 0, f"function API with matching expect should PASS (got {rc})"

    rc = mod.check_artifact(fixture, json_mode=True, expect_step="step2")
    assert rc == 1, f"function API with mismatching step should FAIL (got {rc})"


def test_file_not_found_still_exit_2():
    """ファイル不在は引き続き exit 2。"""
    rc = _run_gate_artifact_cli(["/nonexistent/path.md", "--format=json"])
    assert rc == 2, f"file not found should exit 2 (got {rc})"


# === workflow-gate.sh テスト（step2-report / step4）===

def _find_workflow_gate() -> Path:
    p = ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "workflow-gate.sh"
    return p


def _stage_gate(tmp: Path) -> Path:
    """workflow-gate.sh と依存スクリプトを tmp 配下の同一相対位置へ複製する。

    workflow-gate.sh は SCRIPT_DIR 基準で ROOT_DIR を解決するため、
    cwd を変えても ARTIFACT_DIR / REPORTS_DIR は実リポジトリを指す。
    tmp 配下にコピーすることで ROOT_DIR が tmp を指すようになる。
    """
    src_dir = _find_workflow_gate().parent
    dst = tmp / ".cursor" / "skills" / "session-handover" / "scripts"
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("workflow-gate.sh", "gate-artifact.py", "gate-report.py"):
        src = src_dir / name
        if src.exists():
            shutil.copy2(str(src), str(dst / name))
    return dst / "workflow-gate.sh"


def _setup_envelope_dir(tmp: Path, slug: str, steps: dict[str, str]):
    """steps: {step_name: fixture_file_name or None} の envelope 構成を作る。"""
    artifact_dir = tmp / ".cursor" / ".artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for step_name, fixture_name in steps.items():
        target = artifact_dir / f"{slug}--{step_name}.md"
        if fixture_name is not None:
            src = FIXTURES_DIR / fixture_name
            shutil.copy2(str(src), str(target))
    return artifact_dir


def _setup_report(tmp: Path, slug: str, content: str = "# Test Report\n"):
    reports_dir = tmp / "docs" / "agent-tasks" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = reports_dir / f"{slug}.md"
    report.write_text(content, encoding="utf-8")
    return report


def _run_workflow_gate(step: str, args: list[str] = None, env_override: dict = None) -> subprocess.CompletedProcess:
    gate = _find_workflow_gate()
    if not gate.exists():
        return None
    cmd = ["bash", str(gate), step] + (args or [])
    env = dict(os.environ)
    if env_override:
        env.update(env_override)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_step2_report_envelope_missing_step1():
    """step2-report: step1 envelope 欠落で exit 1。"""
    gate = _find_workflow_gate()
    if not gate.exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        staged = _stage_gate(tmp)
        slug = "TEST-001-envelope-test"
        _setup_report(tmp, slug)
        _setup_envelope_dir(tmp, slug, {"step2": "step2-complete.md"})

        report_path = tmp / "docs" / "agent-tasks" / "reports" / f"{slug}.md"
        step2_env = tmp / ".cursor" / ".artifacts" / f"{slug}--step2.md"
        step2_env.write_text(
            f"---\nstatus: complete\nstep: step2\nreport_path: {report_path}\n---\n\n# Step 2\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", str(staged), "step2-report", str(report_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, (
            f"step2-report with missing step1 envelope should exit 1 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_step2_report_envelope_missing_step2():
    """step2-report: step2 envelope 欠落で exit 1。"""
    gate = _find_workflow_gate()
    if not gate.exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        staged = _stage_gate(tmp)
        slug = "TEST-002-envelope-test"
        _setup_report(tmp, slug)
        _setup_envelope_dir(tmp, slug, {"step1": "step1-complete.md"})

        report_path = tmp / "docs" / "agent-tasks" / "reports" / f"{slug}.md"

        result = subprocess.run(
            ["bash", str(staged), "step2-report", str(report_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, (
            f"step2-report with missing step2 envelope should exit 1 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_step4_envelope_missing_step3():
    """step4: step3 envelope 欠落で verify 未実行・exit 1。"""
    gate = _find_workflow_gate()
    if not gate.exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        staged = _stage_gate(tmp)
        slug = "TEST-003-envelope-test"
        _setup_report(tmp, slug)
        _setup_envelope_dir(tmp, slug, {"step4": "step4-complete.md"})

        report_path = tmp / "docs" / "agent-tasks" / "reports" / f"{slug}.md"

        result = subprocess.run(
            ["bash", str(staged), "step4", str(report_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, (
            f"step4 with missing step3 envelope should exit 1 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "envelope 検査失敗" in result.stdout, (
            f"expected envelope failure message\nstdout: {result.stdout}"
        )
        assert "--- verify ---" not in result.stdout, "verify block must not be reached"


def test_step4_envelope_missing_step4():
    """step4: step4 envelope 欠落で verify 未実行・exit 1。"""
    gate = _find_workflow_gate()
    if not gate.exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        staged = _stage_gate(tmp)
        slug = "TEST-004-envelope-test"
        _setup_report(tmp, slug)
        _setup_envelope_dir(tmp, slug, {"step3": "step3-complete.md"})

        report_path = tmp / "docs" / "agent-tasks" / "reports" / f"{slug}.md"

        result = subprocess.run(
            ["bash", str(staged), "step4", str(report_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, (
            f"step4 with missing step4 envelope should exit 1 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_step4_no_reports_exit_2():
    """step4: report-file 省略・0件で exit 2。"""
    gate = _find_workflow_gate()
    if not gate.exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        staged = _stage_gate(tmp)
        (tmp / "docs" / "agent-tasks" / "reports").mkdir(parents=True)
        (tmp / ".cursor" / ".artifacts").mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["bash", str(staged), "step4"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2, (
            f"step4 with 0 reports and no explicit file should exit 2 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_step4_multiple_reports_exit_2():
    """step4: report-file 省略・複数件で exit 2。"""
    gate = _find_workflow_gate()
    if not gate.exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        staged = _stage_gate(tmp)
        reports_dir = tmp / "docs" / "agent-tasks" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "report-a.md").write_text("# A\n")
        (reports_dir / "report-b.md").write_text("# B\n")
        (tmp / ".cursor" / ".artifacts").mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["bash", str(staged), "step4"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2, (
            f"step4 with 2 reports and no explicit file should exit 2 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_report_digest_matches_step1():
    """PASS: report の digest が Step1 envelope と完全一致する。"""
    mod = _load_gate_report()
    result = mod.check_report(
        str(REPORT_FIXTURES_DIR / "sample-report.md"),
        str(FIXTURES_DIR / "step1-complete.md"),
    )
    assert not result["fail"], f"matching report digest should PASS: {result}"


def test_report_digest_mismatch_fails():
    """FAIL: report の digest が Step1 envelope と不一致。"""
    mod = _load_gate_report()
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "sample-report.md"
        content = (REPORT_FIXTURES_DIR / "sample-report.md").read_text(
            encoding="utf-8"
        )
        report.write_text(
            content.replace(
                "a1b2c3d4e5f67890a1b2c3d4e5f67890"
                "a1b2c3d4e5f67890a1b2c3d4e5f67890",
                "00000000000000000000000000000000"
                "00000000000000000000000000000000",
            ),
            encoding="utf-8",
        )
        result = mod.check_report(
            str(report),
            str(FIXTURES_DIR / "step1-complete.md"),
        )
        assert result["fail"], "digest mismatch should FAIL"
        assert any(
            check["id"] == "G-REPORT-RA-DIGEST-001"
            and check["status"] == "FAIL"
            for check in result["checks"]
        ), f"digest mismatch gate result missing: {result}"


def test_gate_report_artifact_dir_cli():
    """PASS: --artifact-dir から report slug 対応の Step1 を解決する。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        artifact_dir = tmp / "artifacts"
        artifact_dir.mkdir()
        report = tmp / "sample-report.md"
        shutil.copy2(REPORT_FIXTURES_DIR / "sample-report.md", report)
        shutil.copy2(
            FIXTURES_DIR / "step1-complete.md",
            artifact_dir / "sample-report--step1.md",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(_gate_report_path),
                "--artifact-dir",
                str(artifact_dir),
                str(report),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"gate-report --artifact-dir should PASS (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


def main() -> int:
    tests = [
        # gate-artifact.py expect options
        test_expect_step_match,
        test_expect_step_mismatch,
        test_expect_status_match,
        test_expect_status_mismatch,
        test_expect_both_match,
        test_expect_both_step_mismatch,
        test_no_expect_options_backward_compatible,
        test_no_expect_options_blocked_with_reason,
        test_expect_function_api,
        test_file_not_found_still_exit_2,
        # workflow-gate.sh envelope enforcement
        test_step2_report_envelope_missing_step1,
        test_step2_report_envelope_missing_step2,
        test_step4_envelope_missing_step3,
        test_step4_envelope_missing_step4,
        test_step4_no_reports_exit_2,
        test_step4_multiple_reports_exit_2,
        # gate-report.py requirements_digest binding
        test_report_digest_matches_step1,
        test_report_digest_mismatch_fails,
        test_gate_report_artifact_dir_cli,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}", file=sys.stderr)
            failed += 1
        except Exception as e:
            print(f"  ERROR: {t.__name__}: {e}", file=sys.stderr)
            failed += 1

    print(f"[test_envelope_enforcement] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
