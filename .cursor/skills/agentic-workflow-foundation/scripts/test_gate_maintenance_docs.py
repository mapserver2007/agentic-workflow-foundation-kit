#!/usr/bin/env python3
"""gate-maintenance-docs.py の回帰テスト。

検査対象:
  - required + 正常queue → exit 0
  - required + queue欠落 → exit 1 (G-MDOCS-QUEUE-001)
  - required + source_report不一致 → exit 1 (G-MDOCS-QUEUE-001)
  - required + 空target_docs → exit 1 (G-MDOCS-QUEUE-001)
  - required + status != pending → exit 1 (G-MDOCS-QUEUE-001)
  - required + queue_file=なし → exit 1 (G-MDOCS-QUEUE-001)
  - not_required + 理由あり → exit 0
  - not_required + 理由なし → exit 1 (G-MDOCS-REASON-001)
  - not_required + 矛盾queueあり → exit 1 (G-MDOCS-REASON-001)
  - pending → exit 1 (G-MDOCS-JUDGMENT-001)
  - 判定セクション欠落 → exit 1 (G-MDOCS-JUDGMENT-001)
  - manual queueは突合対象外 → not_required PASS に影響しない
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
ROOT = SKILL_DIR.parent.parent.parent

GATE_SCRIPT = ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "gate-maintenance-docs.py"
REPORTS_FIXTURES = SKILL_DIR / "fixtures" / "reports-mdocs"
QUEUE_FIXTURES = SKILL_DIR / "fixtures" / "maintenance-docs"


def _setup_project(tmp: Path, queue_files: list[str] = None, report_file: str = None):
    """一時プロジェクトを作り、queue fixtures をコピーし report を配置する。"""
    queue_dir = tmp / "docs" / "agent-tasks" / "maintenance-docs"
    queue_dir.mkdir(parents=True)
    reports_dir = tmp / "docs" / "agent-tasks" / "reports"
    reports_dir.mkdir(parents=True)

    if queue_files:
        for qf in queue_files:
            src = QUEUE_FIXTURES / qf
            if src.exists():
                shutil.copy2(src, queue_dir / qf)

    report_path = None
    if report_file:
        src = REPORTS_FIXTURES / report_file
        dst = reports_dir / report_file
        shutil.copy2(src, dst)
        report_path = dst

    return report_path


def _run_gate(report_path: Path, project_dir: Path) -> int:
    cmd = [sys.executable, str(GATE_SCRIPT), str(report_path)]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        env={**os.environ, "CURSOR_PROJECT_DIR": str(project_dir)}
    )
    return result.returncode


def test_required_valid():
    """required + 正常queue → PASS"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=["valid-queue.md"],
            report_file="report-required-valid.md"
        )
        # queue の source_report がレポートファイル名と一致するようファイル名変換
        # fixture では source_report: "TICKET-100-add-feature.md" なので、
        # テスト用にレポートファイル名を一致させる
        final_report = report_path.parent / "TICKET-100-add-feature.md"
        shutil.copy2(report_path, final_report)
        rc = _run_gate(final_report, tmp_path)
        assert rc == 0, f"required + valid queue should PASS (got exit {rc})"


def test_required_no_queue():
    """required + queue不在 → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=[],
            report_file="report-required-no-queue.md"
        )
        rc = _run_gate(report_path, tmp_path)
        assert rc == 1, f"required + missing queue should FAIL (got exit {rc})"


def test_required_source_mismatch():
    """required + source_report不一致 → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=["wrong-source-queue.md"],
            report_file="report-required-source-mismatch.md"
        )
        rc = _run_gate(report_path, tmp_path)
        assert rc == 1, f"required + source mismatch should FAIL (got exit {rc})"


def test_required_empty_target():
    """required + 空target_docs → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=["empty-target-queue.md"],
            report_file="report-required-empty-target.md"
        )
        # queue の source_report と一致させる
        final_report = report_path.parent / "TICKET-100-add-feature.md"
        shutil.copy2(report_path, final_report)
        rc = _run_gate(final_report, tmp_path)
        assert rc == 1, f"required + empty target_docs should FAIL (got exit {rc})"


def test_required_done_status():
    """required + queue status != pending → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=["done-status-queue.md"],
            report_file="report-required-done-status.md"
        )
        final_report = report_path.parent / "TICKET-100-add-feature.md"
        shutil.copy2(report_path, final_report)
        rc = _run_gate(final_report, tmp_path)
        assert rc == 1, f"required + done status queue should FAIL (got exit {rc})"


def test_required_no_queuefile():
    """required + queue_file=なし → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=[],
            report_file="report-required-no-queuefile.md"
        )
        rc = _run_gate(report_path, tmp_path)
        assert rc == 1, f"required + queue_file=なし should FAIL (got exit {rc})"


def test_not_required_valid():
    """not_required + 理由あり → PASS"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=[],
            report_file="report-not-required-valid.md"
        )
        # queue_dir を作る（空でよい）
        (tmp_path / "docs" / "agent-tasks" / "maintenance-docs").mkdir(parents=True, exist_ok=True)
        rc = _run_gate(report_path, tmp_path)
        assert rc == 0, f"not_required + reason should PASS (got exit {rc})"


def test_not_required_no_reason():
    """not_required + 理由なし → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=[],
            report_file="report-not-required-no-reason.md"
        )
        rc = _run_gate(report_path, tmp_path)
        assert rc == 1, f"not_required + no reason should FAIL (got exit {rc})"


def test_not_required_conflicting_queue():
    """not_required + 矛盾queue存在 → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=["conflicting-queue.md"],
            report_file="report-not-required-conflicting.md"
        )
        # レポートファイル名を queue の source_report と一致させる
        final_report = report_path.parent / "TICKET-300-conflict-test.md"
        shutil.copy2(report_path, final_report)
        rc = _run_gate(final_report, tmp_path)
        assert rc == 1, f"not_required + conflicting queue should FAIL (got exit {rc})"


def test_pending():
    """pending → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=[],
            report_file="report-pending.md"
        )
        rc = _run_gate(report_path, tmp_path)
        assert rc == 1, f"pending should FAIL (got exit {rc})"


def test_no_judgment_section():
    """判定セクション欠落 → FAIL"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=[],
            report_file="report-no-judgment-section.md"
        )
        rc = _run_gate(report_path, tmp_path)
        assert rc == 1, f"no judgment section should FAIL (got exit {rc})"


def test_manual_queue_excluded():
    """manual queueは突合対象外 — not_required のレポートに影響しない"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = _setup_project(
            tmp_path,
            queue_files=["manual-queue.md"],
            report_file="report-not-required-valid.md"
        )
        rc = _run_gate(report_path, tmp_path)
        assert rc == 0, f"manual queue should not affect not_required PASS (got exit {rc})"


def main() -> int:
    tests = [
        test_required_valid,
        test_required_no_queue,
        test_required_source_mismatch,
        test_required_empty_target,
        test_required_done_status,
        test_required_no_queuefile,
        test_not_required_valid,
        test_not_required_no_reason,
        test_not_required_conflicting_queue,
        test_pending,
        test_no_judgment_section,
        test_manual_queue_excluded,
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

    print(f"[test_gate_maintenance_docs] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
