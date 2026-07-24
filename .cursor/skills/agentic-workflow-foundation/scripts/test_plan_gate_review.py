#!/usr/bin/env python3
"""plan-gate.sh review の G-PLAN-REVIEW-001 回帰テスト。

tracker fixture を使い、レビュー承認判定が「## レビュー完了承認」節のみを
対象にしていることを検証する。

テストケース:
  - compact 生成骨格: report=PASS（7節存在）/ review=FAIL（承認未取得）
  - review-approved: review=PASS（承認取得済み、未対応0件）
  - review-pending: review=FAIL（未対応マーカー残存）
  - review-false-positive-exception: review=FAIL（例外承認節の「承認取得済み」で誤通過しない）
  - review-approved-with-hold-elsewhere: review=PASS（他節の「保留」で誤失敗しない）
"""
from __future__ import annotations

import os
import subprocess
import sys
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
FIXTURES_DIR = HERE.parent / "fixtures" / "trackers"
PLAN_GATE = ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "plan-gate.sh"
TMPDIR = ROOT / ".cursor" / ".test-tmp-plan-gate"


def run_plan_gate(tracker_fixture: str, phase: str) -> int:
    """Run plan-gate.sh against a fixture in a workspace-internal temp directory."""
    fixture_path = FIXTURES_DIR / tracker_fixture
    if not fixture_path.exists():
        raise FileNotFoundError(f"fixture not found: {fixture_path}")

    if TMPDIR.exists():
        shutil.rmtree(TMPDIR)
    tracking_dir = TMPDIR / ".cursor" / ".tracking"
    tracking_dir.mkdir(parents=True)
    dest = tracking_dir / "tracker-test-session.md"
    shutil.copy2(fixture_path, dest)

    env = os.environ.copy()
    env["CURSOR_PROJECT_DIR"] = str(TMPDIR)

    try:
        result = subprocess.run(
            ["bash", str(PLAN_GATE), phase],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        return result.returncode
    finally:
        shutil.rmtree(TMPDIR, ignore_errors=True)


def test_compact_generated_report_pass():
    """compact 生成骨格は必須7節を含むため report=PASS。"""
    rc = run_plan_gate("compact-generated.md", "report")
    assert rc == 0, f"compact-generated.md report should PASS, got exit {rc}"


def test_compact_generated_review_fail():
    """compact 生成骨格は承認未取得のため review=FAIL。"""
    rc = run_plan_gate("compact-generated.md", "review")
    assert rc == 1, f"compact-generated.md review should FAIL, got exit {rc}"


def test_review_approved_pass():
    """承認取得済み + 未対応0件 → review=PASS。"""
    rc = run_plan_gate("review-approved.md", "review")
    assert rc == 0, f"review-approved.md review should PASS, got exit {rc}"


def test_review_pending_fail():
    """未対応マーカー残存 → review=FAIL。"""
    rc = run_plan_gate("review-pending.md", "review")
    assert rc == 1, f"review-pending.md review should FAIL, got exit {rc}"


def test_false_positive_exception_section():
    """例外承認節に「承認取得済み」があってもレビュー承認節が未承認なら review=FAIL。"""
    rc = run_plan_gate("review-false-positive-exception.md", "review")
    assert rc == 1, (
        f"review-false-positive-exception.md review should FAIL "
        f"(例外承認節の「承認取得済み」で誤通過してはならない), got exit {rc}"
    )


def test_hold_elsewhere_no_false_failure():
    """他節に「保留」があってもレビュー承認節が承認取得済みなら review=PASS。"""
    rc = run_plan_gate("review-approved-with-hold-elsewhere.md", "review")
    assert rc == 0, (
        f"review-approved-with-hold-elsewhere.md review should PASS "
        f"(他節の「保留」で誤失敗してはならない), got exit {rc}"
    )


def main() -> int:
    tests = [
        test_compact_generated_report_pass,
        test_compact_generated_review_fail,
        test_review_approved_pass,
        test_review_pending_fail,
        test_false_positive_exception_section,
        test_hold_elsewhere_no_false_failure,
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

    print(f"[test_plan_gate_review] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
