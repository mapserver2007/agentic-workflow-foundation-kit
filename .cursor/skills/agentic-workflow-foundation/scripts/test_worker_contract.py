#!/usr/bin/env python3
"""Worker Contract 整合テスト。

gate-artifact.py の STEP_REQUIRED_FIELDS と step doc の Worker Contract 出力表の
機械検査必須フィールドの一致、および全状態パス（complete / incomplete / blocked / fatal）の
fixture 検証を行う。

検査対象:
  - STEP_REQUIRED_FIELDS ⊆ step doc 出力フィールド（静的検査）
  - 正常系 fixture (step1〜4,6 × complete) → exit 0
  - 異常系 fixture (blocked/fatal reason有無、complete必須フィールド欠落、不正status/step) → exit 1
  - 共通必須フィールド (status, step) の存在・値域チェック
  - blocked/fatal 時の reason 必須チェック
  - step3 complete 時の base_commit_sha SHA 形式チェック
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent

_gate_artifact_path = (
    ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "gate-artifact.py"
)
_spec = importlib.util.spec_from_file_location("gate_artifact", str(_gate_artifact_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

COMMON_REQUIRED = _mod.COMMON_REQUIRED
STEP_REQUIRED_FIELDS = _mod.STEP_REQUIRED_FIELDS
VALID_STATUSES = _mod.VALID_STATUSES
VALID_STEPS = _mod.VALID_STEPS
check_artifact = _mod.check_artifact

FIXTURES_DIR = HERE.parent / "fixtures" / "artifacts"

STEP_DOC_OUTPUT_FIELDS = {
    "step1": {
        "status", "step", "gate_result", "missing",
        "investigation_memo_path", "triage_result", "reason",
    },
    "step2": {
        "status", "step", "report_path", "report_digest",
        "gate_result", "missing", "reason",
    },
    "step3": {
        "status", "step", "changed_files", "untracked_files",
        "base_commit_sha", "impl_summary", "adr_needed",
        "reason", "decision_alternatives",
    },
    "step4": {
        "status", "step", "gate_results", "test_summary",
        "advisory_loop_count", "reason", "gate_id", "stderr_summary",
    },
    "step6": {
        "status", "step", "doc_maintenance_file", "archive_path",
        "archive_gate_result", "unchecked_items", "reason", "action",
    },
}


def test_step_required_fields_subset_of_doc():
    """gate-artifact STEP_REQUIRED_FIELDS ⊆ step doc 出力フィールド。"""
    for step, gate_fields in STEP_REQUIRED_FIELDS.items():
        doc_fields = STEP_DOC_OUTPUT_FIELDS.get(step)
        assert doc_fields is not None, f"step doc が未定義: {step}"
        gate_set = set(gate_fields)
        diff = gate_set - doc_fields
        assert not diff, (
            f"{step}: gate-artifact の必須フィールド {diff} が step doc に存在しない"
        )


def test_valid_steps_match_doc():
    """VALID_STEPS が step doc と一致する。"""
    assert VALID_STEPS == set(STEP_DOC_OUTPUT_FIELDS.keys()), (
        f"VALID_STEPS={sorted(VALID_STEPS)} vs "
        f"doc_steps={sorted(STEP_DOC_OUTPUT_FIELDS.keys())}"
    )


def test_valid_statuses():
    """VALID_STATUSES が 4 状態を含む。"""
    expected = {"complete", "incomplete", "blocked", "fatal"}
    assert VALID_STATUSES == expected, (
        f"VALID_STATUSES={sorted(VALID_STATUSES)} vs expected={sorted(expected)}"
    )


def test_common_required():
    """共通必須フィールドが status, step の 2 つ。"""
    assert set(COMMON_REQUIRED) == {"status", "step"}, (
        f"COMMON_REQUIRED={COMMON_REQUIRED}"
    )


def test_step1_complete():
    rc = check_artifact(str(FIXTURES_DIR / "step1-complete.md"), json_mode=True)
    assert rc == 0, "step1-complete should PASS"


def test_step2_complete():
    rc = check_artifact(str(FIXTURES_DIR / "step2-complete.md"), json_mode=True)
    assert rc == 0, "step2-complete should PASS"


def test_step3_complete():
    rc = check_artifact(str(FIXTURES_DIR / "step3-complete.md"), json_mode=True)
    assert rc == 0, "step3-complete should PASS"


def test_step4_complete():
    rc = check_artifact(str(FIXTURES_DIR / "step4-complete.md"), json_mode=True)
    assert rc == 0, "step4-complete should PASS"


def test_step6_complete():
    rc = check_artifact(str(FIXTURES_DIR / "step6-complete.md"), json_mode=True)
    assert rc == 0, "step6-complete should PASS"


def test_blocked_with_reason():
    rc = check_artifact(str(FIXTURES_DIR / "blocked-with-reason.md"), json_mode=True)
    assert rc == 0, "blocked with reason should PASS"


def test_blocked_no_reason_fails():
    rc = check_artifact(str(FIXTURES_DIR / "blocked-no-reason.md"), json_mode=True)
    assert rc == 1, "blocked without reason should FAIL (G-ARTIFACT-REASON-001)"


def test_fatal_with_reason():
    rc = check_artifact(str(FIXTURES_DIR / "fatal-with-reason.md"), json_mode=True)
    assert rc == 0, "fatal with reason should PASS"


def test_fatal_no_reason_fails():
    rc = check_artifact(str(FIXTURES_DIR / "fatal-no-reason.md"), json_mode=True)
    assert rc == 1, "fatal without reason should FAIL (G-ARTIFACT-REASON-001)"


def test_complete_missing_field_fails():
    rc = check_artifact(str(FIXTURES_DIR / "complete-missing-field.md"), json_mode=True)
    assert rc == 1, (
        "complete with missing investigation_memo_path should FAIL "
        "(G-ARTIFACT-STEP-FIELD-001)"
    )


def test_invalid_status_fails():
    rc = check_artifact(str(FIXTURES_DIR / "invalid-status.md"), json_mode=True)
    assert rc == 1, "invalid status 'success' should FAIL (G-ARTIFACT-STATUS-001)"


def test_invalid_step_fails():
    rc = check_artifact(str(FIXTURES_DIR / "invalid-step.md"), json_mode=True)
    assert rc == 1, "invalid step 'step5' should FAIL (G-ARTIFACT-STEP-001)"


def main() -> int:
    tests = [
        test_step_required_fields_subset_of_doc,
        test_valid_steps_match_doc,
        test_valid_statuses,
        test_common_required,
        test_step1_complete,
        test_step2_complete,
        test_step3_complete,
        test_step4_complete,
        test_step6_complete,
        test_blocked_with_reason,
        test_blocked_no_reason_fails,
        test_fatal_with_reason,
        test_fatal_no_reason_fails,
        test_complete_missing_field_fails,
        test_invalid_status_fails,
        test_invalid_step_fails,
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

    print(f"[test_worker_contract] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
