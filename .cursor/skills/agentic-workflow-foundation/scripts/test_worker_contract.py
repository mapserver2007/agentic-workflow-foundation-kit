#!/usr/bin/env python3
"""Worker Contract 整合テスト。

gate-artifact.py の STEP_REQUIRED_FIELDS と step doc の Worker Contract 出力表の
機械検査必須フィールドの一致、および全状態パス（complete / incomplete / blocked / fatal）の
fixture 検証を行う。

検査対象:
  - STEP_REQUIRED_FIELDS ⊆ step doc 出力フィールド（静的検査）
  - 正常系 fixture (step1〜4 × complete) → exit 0
  - 異常系 fixture (blocked/fatal reason有無、complete必須フィールド欠落、不正status/step) → exit 1
  - 共通必須フィールド (status, step) の存在・値域チェック
  - blocked/fatal 時の reason 必須チェック
  - step3 complete 時の base_commit_sha SHA 形式チェック
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
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
        "investigation_memo_path", "analysis_depth",
        "requirement_gate", "spec_consistency_gate", "feasibility_gate",
        "blocking_open_issues", "non_blocking_issues",
        "acceptance_criteria_status", "resolved_issues", "reason",
        "normalize_artifact_path", "depth_triage_artifact_path",
        "depth_fallback_reason",
        "requirements_digest", "campaign_slug",
    },
    "step2": {
        "status", "step", "campaign_slug", "report_slug", "report_path", "report_digest",
        "gate_result", "missing", "reason", "implementation_approval",
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
    rc = check_artifact(str(FIXTURES_DIR / "sample-report--step1.md"), json_mode=True)
    assert rc == 0, "sample-report--step1 should PASS"


def test_step2_complete():
    rc = check_artifact(str(FIXTURES_DIR / "step2-complete--step2.md"), json_mode=True)
    assert rc == 0, "step2-complete should PASS"


def test_step3_complete():
    rc = check_artifact(str(FIXTURES_DIR / "step3-complete.md"), json_mode=True)
    assert rc == 0, "step3-complete should PASS"


def test_step3_missing_untracked_fails():
    rc, check_ids = _check_artifact_json(
        FIXTURES_DIR / "step3-complete-missing-untracked.md"
    )
    assert rc == 1, "step3 complete without untracked_files should FAIL"
    assert "G-ARTIFACT-STEP3-UNTRACKED-001" in check_ids


def test_step4_complete():
    rc = check_artifact(str(FIXTURES_DIR / "step4-complete.md"), json_mode=True)
    assert rc == 0, "step4-complete should PASS"


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


def test_step1_blocking_issues_fails():
    rc = check_artifact(str(FIXTURES_DIR / "step1-blocking-issues.md"), json_mode=True)
    assert rc == 1, (
        "step1 complete with non-empty blocking_open_issues should FAIL "
        "(G-ARTIFACT-RA-BLOCKING-001)"
    )


def test_step1_deferred_exit_fails():
    rc = check_artifact(str(FIXTURES_DIR / "step1-deferred-exit.md"), json_mode=True)
    assert rc == 1, (
        "step1 complete with analysis_depth=deferred should FAIL "
        "(G-ARTIFACT-RA-DEPTH-001)"
    )


def test_step1_missing_gate_fails():
    rc = check_artifact(str(FIXTURES_DIR / "step1-missing-gate.md"), json_mode=True)
    assert rc == 1, (
        "step1 complete with missing requirement_gate should FAIL "
        "(G-ARTIFACT-STEP-FIELD-001)"
    )


def test_invalid_status_fails():
    rc = check_artifact(str(FIXTURES_DIR / "invalid-status.md"), json_mode=True)
    assert rc == 1, "invalid status 'success' should FAIL (G-ARTIFACT-STATUS-001)"


def test_invalid_step_fails():
    rc = check_artifact(str(FIXTURES_DIR / "invalid-step.md"), json_mode=True)
    assert rc == 1, "invalid step 'step5' should FAIL (G-ARTIFACT-STEP-001)"


def test_step3_blocked_adr_valid():
    rc = check_artifact(str(FIXTURES_DIR / "step3-blocked-adr-valid.md"), json_mode=True)
    assert rc == 0, "step3 blocked: adr_required with SHA + 2 alts should PASS"


def test_step3_blocked_adr_no_sha_fails():
    rc = check_artifact(str(FIXTURES_DIR / "step3-blocked-adr-no-sha.md"), json_mode=True)
    assert rc == 1, (
        "step3 blocked: adr_required without base_commit_sha should FAIL "
        "(G-ARTIFACT-ADR-SHA-001)"
    )


def test_step3_blocked_adr_few_alts_fails():
    rc = check_artifact(str(FIXTURES_DIR / "step3-blocked-adr-few-alts.md"), json_mode=True)
    assert rc == 1, (
        "step3 blocked: adr_required with <2 alternatives should FAIL "
        "(G-ARTIFACT-ADR-ALTS-001)"
    )


import tempfile


_BASE_NORM_FM = (
    "status: complete\n"
    "step: step1-normalize\n"
    "campaign_slug: T-1\n"
    "gate_a: PASS\n"
    "blocking_open_issues: []\n"
    "task_type: bug_fix\n"
    "fields:\n"
    "  - name: target_component\n"
    "    value: test-component\n"
    "    provenance: user_confirmed\n"
    "    evidence_ref: user input\n"
)

_BASE_DEPTH_FM = (
    "status: complete\n"
    "step: step1-depth-triage\n"
    "campaign_slug: T-1\n"
    "gate_b: PASS\n"
    "analysis_depth: standard\n"
    "depth_reason: test\n"
)

_DIGEST_FIXTURE = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"

_VALID_MEMO_BODY = """\
## 正規化済み要求
fixture の要求

## 確定済み受入条件
AC-001: artifact gate が正常系 fixture を受理する

## 根本原因分析 / 実装方針候補
fixture の正常系を検証する。

## 争点と判断根拠
自己参照 Memo とする。

## 影響範囲
テスト fixture のみ。

## 変更対象ファイル
AC-001 を test fixture で検証する。

## 実装手順
AC-001 の fixture を検証する。

## テスト観点
AC-001 で gate が PASS する。

## ADR 起票判定結果
不要。

## docs-first 参照記録
要求分析契約を参照。

## Issue Ledger
なし。

## non-blocking issues
なし。
"""

_BASE_MAIN_FM = (
    "status: complete\n"
    "step: step1\n"
    "campaign_slug: T-1\n"
    "gate_result: PASS\n"
    "analysis_depth: standard\n"
    "requirement_gate: PASS\n"
    "spec_consistency_gate: PASS\n"
    "feasibility_gate: PASS\n"
    "blocking_open_issues: []\n"
    "non_blocking_issues: []\n"
    "acceptance_criteria_status: complete\n"
    "resolved_issues: []\n"
    f"requirements_digest: \"{_DIGEST_FIXTURE}\"\n"
)


def _write_artifact(directory: Path, name: str, fm_text: str, body: str = "# body\n"):
    p = directory / name
    p.write_text(f"---\n{fm_text}---\n\n{body}", encoding="utf-8")
    return p


def _build_step1_suite(tmp: Path, slug: str = "T-1",
                       main_extra: str = "",
                       norm_fm: str | None = None,
                       depth_fm: str | None = None,
                       skip_norm_file: bool = False,
                       skip_depth_file: bool = False,
                       memo_path: str | None = None,
                       memo_body: str | None = None):
    """Build a step1 envelope + intermediate artifacts in tmp dir."""
    norm_name = f"{slug}--step1-normalize.md"
    depth_name = f"{slug}--step1-depth-triage.md"
    memo_ref = memo_path or f".cursor/.artifacts/{slug}--step1.md"
    main_fm = (
        _BASE_MAIN_FM
        + f"investigation_memo_path: {memo_ref}\n"
        + f"normalize_artifact_path: .cursor/.artifacts/{norm_name}\n"
        + f"depth_triage_artifact_path: .cursor/.artifacts/{depth_name}\n"
        + main_extra
    )
    main_path = _write_artifact(
        tmp,
        f"{slug}--step1.md",
        main_fm,
        body=memo_body if memo_body is not None else _VALID_MEMO_BODY,
    )
    if not skip_norm_file:
        _write_artifact(tmp, norm_name, norm_fm or _BASE_NORM_FM)
    if not skip_depth_file:
        _write_artifact(tmp, depth_name, depth_fm or _BASE_DEPTH_FM)
    return main_path


def _check_artifact_json(path: Path) -> tuple[int, set[str]]:
    """JSON 診断を捕捉し、exit code と検査 ID 集合を返す。"""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = check_artifact(str(path), json_mode=True)
    payload = json.loads(output.getvalue())
    return rc, {check["id"] for check in payload["checks"]}


def _write_step4_artifact(directory: Path, gate_results_yaml: str) -> Path:
    fm = (
        "status: complete\n"
        "step: step4\n"
        "gate_results:\n"
        f"{gate_results_yaml}"
        "test_summary: fixture\n"
        "advisory_loop_count: 1\n"
    )
    return _write_artifact(directory, "T-4--step4.md", fm)


def test_step4_gate_results_form_b_passes():
    """PASS: Form B の4キーがすべて YAML 整数 0。"""
    with tempfile.TemporaryDirectory() as td:
        artifact = _write_step4_artifact(
            Path(td),
            "  gen: 0\n  build: 0\n  lint: 0\n  test: 0\n",
        )
        rc = check_artifact(str(artifact), json_mode=True)
        assert rc == 0, "Form B gate_results should PASS"


def test_step4_gate_results_invalid_values_fail():
    """FAIL: 文字列、非0、bool の値を拒否し、検査 ID を返す。"""
    cases = (
        "  gen: PASS\n  build: 0\n  lint: 0\n  test: 0\n",
        "  gen: 0\n  build: SKIP\n  lint: 0\n  test: 0\n",
        "  gen: 0\n  build: 0\n  lint: SKIPPED\n  test: 0\n",
        '  gen: "0"\n  build: 0\n  lint: 0\n  test: 0\n',
        "  gen: 0\n  build: 0\n  lint: 0\n  test: 1\n",
        "  gen: true\n  build: 0\n  lint: 0\n  test: 0\n",
    )
    for gate_results_yaml in cases:
        with tempfile.TemporaryDirectory() as td:
            artifact = _write_step4_artifact(Path(td), gate_results_yaml)
            rc, check_ids = _check_artifact_json(artifact)
            assert rc == 1, f"invalid gate_results should FAIL: {gate_results_yaml!r}"
            assert "G-ARTIFACT-STEP4-GATES-001" in check_ids, (
                f"expected Step4 gate finding, got {sorted(check_ids)}"
            )


def test_step4_gate_results_key_set_fails():
    """FAIL: 4キーの欠落と余分なキーを拒否する。"""
    cases = (
        "  build: 0\n  lint: 0\n  test: 0\n",
        "  gen: 0\n  build: 0\n  lint: 0\n  test: 0\n  deploy: 0\n",
    )
    for gate_results_yaml in cases:
        with tempfile.TemporaryDirectory() as td:
            artifact = _write_step4_artifact(Path(td), gate_results_yaml)
            rc, check_ids = _check_artifact_json(artifact)
            assert rc == 1, f"invalid gate key set should FAIL: {gate_results_yaml!r}"
            assert "G-ARTIFACT-STEP4-GATES-001" in check_ids, (
                f"expected Step4 gate finding, got {sorted(check_ids)}"
            )


def test_step1_intermediate_pass():
    """正常系: standard 経路で中間 artifact が整合 → PASS。"""
    with tempfile.TemporaryDirectory() as td:
        main = _build_step1_suite(Path(td))
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 0, "standard path with valid intermediates should PASS"


def test_step1_deep_fallback_pass():
    """正常系: deep → standard フォールバック (depth_fallback_reason あり) → PASS。"""
    with tempfile.TemporaryDirectory() as td:
        depth_fm = (
            "status: complete\n"
            "step: step1-depth-triage\n"
            "campaign_slug: T-1\n"
            "gate_b: PASS\n"
            "analysis_depth: deep\n"
            "depth_reason: test\n"
        )
        main = _build_step1_suite(
            Path(td),
            main_extra="depth_fallback_reason: model unavailable\n",
            depth_fm=depth_fm,
        )
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 0, "deep fallback with reason should PASS"


def test_step1_norm_file_missing_fails():
    """FAIL: normalize artifact ファイル不在。"""
    with tempfile.TemporaryDirectory() as td:
        main = _build_step1_suite(Path(td), skip_norm_file=True)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "missing normalize file should FAIL (G-ARTIFACT-RA-REF-001)"


def test_step1_depth_file_missing_fails():
    """FAIL: depth_triage artifact ファイル不在。"""
    with tempfile.TemporaryDirectory() as td:
        main = _build_step1_suite(Path(td), skip_depth_file=True)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "missing depth file should FAIL (G-ARTIFACT-RA-REF-001)"


def test_step1_wrong_slug_fails():
    """FAIL: 中間 artifact の slug が最終 envelope と不一致。"""
    with tempfile.TemporaryDirectory() as td:
        wrong_slug = "WRONG"
        slug = "T-1"
        main_fm = (
            _BASE_MAIN_FM
            + f"investigation_memo_path: .cursor/.artifacts/{slug}--step1.md\n"
            + f"normalize_artifact_path: .cursor/.artifacts/{wrong_slug}--step1-normalize.md\n"
            + f"depth_triage_artifact_path: .cursor/.artifacts/{slug}--step1-depth-triage.md\n"
        )
        main = _write_artifact(
            Path(td), f"{slug}--step1.md", main_fm, body=_VALID_MEMO_BODY
        )
        _write_artifact(Path(td), f"{wrong_slug}--step1-normalize.md", _BASE_NORM_FM)
        _write_artifact(Path(td), f"{slug}--step1-depth-triage.md", _BASE_DEPTH_FM)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "wrong slug in normalize path should FAIL (G-ARTIFACT-RA-REF-001)"


def test_step1_norm_schema_invalid_fails():
    """FAIL: normalize artifact の schema 不正 (gate_a != PASS)。"""
    with tempfile.TemporaryDirectory() as td:
        bad_norm = (
            "status: complete\n"
            "step: step1-normalize\n"
            "gate_a: INCOMPLETE\n"
            "blocking_open_issues: []\n"
        )
        main = _build_step1_suite(Path(td), norm_fm=bad_norm)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "normalize gate_a=INCOMPLETE should FAIL (G-ARTIFACT-RA-NORM-SCHEMA-001)"


def test_step1_depth_schema_invalid_fails():
    """FAIL: depth_triage artifact の schema 不正 (step 不一致)。"""
    with tempfile.TemporaryDirectory() as td:
        bad_depth = (
            "status: complete\n"
            "step: wrong-step\n"
            "gate_b: PASS\n"
            "analysis_depth: standard\n"
            "depth_reason: test\n"
        )
        main = _build_step1_suite(Path(td), depth_fm=bad_depth)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "depth step mismatch should FAIL (G-ARTIFACT-RA-DEPTH-SCHEMA-001)"


def test_step1_gate_source_mismatch_fails():
    """FAIL: requirement_gate と normalize.gate_a が不一致。"""
    with tempfile.TemporaryDirectory() as td:
        bad_norm = (
            "status: complete\n"
            "step: step1-normalize\n"
            "gate_a: INCOMPLETE\n"
            "blocking_open_issues: []\n"
        )
        main = _build_step1_suite(Path(td), norm_fm=bad_norm)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "gate source mismatch should FAIL (G-ARTIFACT-RA-GATE-SOURCE-001)"


def test_step1_depth_consistency_fails():
    """FAIL: depth_triage=standard なのに最終 depth=deep。"""
    with tempfile.TemporaryDirectory() as td:
        main_fm = (
            "status: complete\n"
            "step: step1\n"
            "gate_result: PASS\n"
            "investigation_memo_path: .cursor/.artifacts/T-1--step1.md\n"
            "analysis_depth: deep\n"
            "requirement_gate: PASS\n"
            "spec_consistency_gate: PASS\n"
            "feasibility_gate: PASS\n"
            "blocking_open_issues: []\n"
            "non_blocking_issues: []\n"
            "acceptance_criteria_status: complete\n"
            "resolved_issues: []\n"
            "normalize_artifact_path: .cursor/.artifacts/T-1--step1-normalize.md\n"
            "depth_triage_artifact_path: .cursor/.artifacts/T-1--step1-depth-triage.md\n"
        )
        main = _write_artifact(
            Path(td), "T-1--step1.md", main_fm, body=_VALID_MEMO_BODY
        )
        _write_artifact(Path(td), "T-1--step1-normalize.md", _BASE_NORM_FM)
        _write_artifact(Path(td), "T-1--step1-depth-triage.md", _BASE_DEPTH_FM)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "standard triage → deep final should FAIL (G-ARTIFACT-RA-DEPTH-CONSIST-001)"


def test_step1_deep_fallback_no_reason_fails():
    """FAIL: depth_triage=deep → 最終=standard だが depth_fallback_reason なし。"""
    with tempfile.TemporaryDirectory() as td:
        depth_fm = (
            "status: complete\n"
            "step: step1-depth-triage\n"
            "gate_b: PASS\n"
            "analysis_depth: deep\n"
            "depth_reason: test\n"
        )
        main = _build_step1_suite(Path(td), depth_fm=depth_fm)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "deep fallback without reason should FAIL (G-ARTIFACT-RA-DEPTH-CONSIST-001)"


def test_step1_deferred_to_standard_pass():
    """PASS: triage=deferred → final=standard。"""
    with tempfile.TemporaryDirectory() as td:
        depth_fm = (
            "status: complete\n"
            "step: step1-depth-triage\n"
            "campaign_slug: T-1\n"
            "gate_b: PASS\n"
            "analysis_depth: deferred\n"
            "depth_reason: test\n"
        )
        main = _build_step1_suite(Path(td), depth_fm=depth_fm)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 0, "deferred triage → standard final should PASS"


def test_step1_deferred_to_deep_pass():
    """PASS: triage=deferred → final=deep。"""
    with tempfile.TemporaryDirectory() as td:
        depth_fm = (
            "status: complete\n"
            "step: step1-depth-triage\n"
            "campaign_slug: T-1\n"
            "gate_b: PASS\n"
            "analysis_depth: deferred\n"
            "depth_reason: test\n"
        )
        main = _build_step1_suite(
            Path(td),
            main_extra="analysis_depth: deep\n",
            depth_fm=depth_fm,
        )
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 0, "deferred triage → deep final should PASS"


def test_step1_ack_missing_passes():
    """PASS: requirements_ack なしでも digest があれば新規 artifact を受理する。"""
    with tempfile.TemporaryDirectory() as td:
        fm = (
            "status: complete\n"
            "step: step1\n"
            "campaign_slug: T-1\n"
            "gate_result: PASS\n"
            "investigation_memo_path: .cursor/.artifacts/T-1--step1.md\n"
            "analysis_depth: standard\n"
            "requirement_gate: PASS\n"
            "spec_consistency_gate: PASS\n"
            "feasibility_gate: PASS\n"
            "blocking_open_issues: []\n"
            "non_blocking_issues: []\n"
            "acceptance_criteria_status: complete\n"
            "resolved_issues: []\n"
            f'requirements_digest: "{_DIGEST_FIXTURE}"\n'
            "normalize_artifact_path: .cursor/.artifacts/T-1--step1-normalize.md\n"
            "depth_triage_artifact_path: .cursor/.artifacts/T-1--step1-depth-triage.md\n"
        )
        main = _write_artifact(
            Path(td), "T-1--step1.md", fm, body=_VALID_MEMO_BODY
        )
        _write_artifact(Path(td), "T-1--step1-normalize.md", _BASE_NORM_FM)
        _write_artifact(Path(td), "T-1--step1-depth-triage.md", _BASE_DEPTH_FM)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 0, "missing requirements_ack should PASS"


def test_step1_ack_explicit_null_fails():
    """FAIL: 明示された requirements_ack: null は旧 artifact 互換の対象外。"""
    with tempfile.TemporaryDirectory() as td:
        main = _build_step1_suite(
            Path(td),
            main_extra="requirements_ack: null\n",
        )
        rc, check_ids = _check_artifact_json(main)
        assert rc == 1, "explicit null requirements_ack should FAIL"
        assert "G-ARTIFACT-RA-ACK-002" in check_ids


def test_step1_ack_digest_mismatch_fails():
    """FAIL: 旧 requirements_ack が存在して digest と不一致。"""
    with tempfile.TemporaryDirectory() as td:
        wrong_digest = "0000000000000000000000000000000000000000000000000000000000000000"
        main = _build_step1_suite(
            Path(td),
            main_extra=(
                "requirements_ack:\n"
                "  status: acknowledged\n"
                f'  digest: "{wrong_digest}"\n'
            ),
        )
        content = main.read_text(encoding="utf-8")
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "ack digest mismatch should FAIL (G-ARTIFACT-RA-ACK-004)"


def test_step1_ack_digest_case_difference_passes():
    """PASS: 旧 requirements_ack.digest の大文字小文字差は許容する。"""
    with tempfile.TemporaryDirectory() as td:
        main = _build_step1_suite(
            Path(td),
            main_extra=(
                "requirements_ack:\n"
                "  status: acknowledged\n"
                f'  digest: "{_DIGEST_FIXTURE.upper()}"\n'
            ),
        )
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 0, "ack digest differing only by case should PASS"


def test_step1_digest_malformed_fails():
    """FAIL: requirements_digest と ack が同値でも SHA-256 形式ではない。"""
    with tempfile.TemporaryDirectory() as td:
        main = _build_step1_suite(Path(td))
        content = main.read_text(encoding="utf-8")
        main.write_text(
            content.replace(_DIGEST_FIXTURE, "not-a-sha256"),
            encoding="utf-8",
        )
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "malformed digest should FAIL (G-ARTIFACT-RA-ACK-001)"


def test_step1_campaign_slug_prefix_mismatch_fails():
    """FAIL: campaign_slug と --step1 より前の prefix が異なる。"""
    with tempfile.TemporaryDirectory() as td:
        main = _build_step1_suite(Path(td), slug="OTHER")
        rc, check_ids = _check_artifact_json(main)
        assert rc == 1
        assert "G-ARTIFACT-CAMPAIGN-SLUG-001" in check_ids


def test_step1_campaign_slug_suffix_passes():
    """PASS: step filename の後続 suffix は prefix 一致なら許容する。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        main = _build_step1_suite(tmp)
        renamed = tmp / "T-1--step1-retry.md"
        main.rename(renamed)
        renamed.write_text(
            renamed.read_text(encoding="utf-8").replace(
                "investigation_memo_path: .cursor/.artifacts/T-1--step1.md",
                "investigation_memo_path: .cursor/.artifacts/T-1--step1-retry.md",
            ),
            encoding="utf-8",
        )
        rc = check_artifact(str(renamed), json_mode=True)
        assert rc == 0


def test_step2_report_slug_must_match_campaign_slug():
    """Step② report_slug は campaign_slug と完全一致する。"""
    with tempfile.TemporaryDirectory() as td:
        path = _write_artifact(
            Path(td),
            "T-2--step2.md",
            (
                "status: complete\n"
                "step: step2\n"
                "campaign_slug: T-2\n"
                "report_slug: T-2\n"
                "report_path: docs/agent-tasks/reports/T-2.md\n"
                "implementation_approval:\n"
                "  status: pending\n"
                f'  approved_plan_digest: "{_DIGEST_FIXTURE}"\n'
                "  decider: PO\n"
            ),
        )
        assert check_artifact(str(path), json_mode=True) == 0
        path.write_text(
            path.read_text(encoding="utf-8").replace("report_slug: T-2", "report_slug: OTHER"),
            encoding="utf-8",
        )
        rc, check_ids = _check_artifact_json(path)
        assert rc == 1
        assert "G-ARTIFACT-STEP2-REPORT-SLUG-001" in check_ids


def test_step1_memo_unresolvable_fails():
    """FAIL: investigation_memo_path の参照先が解決不能。"""
    with tempfile.TemporaryDirectory() as td:
        main = _build_step1_suite(
            Path(td),
            memo_path=".cursor/.tracking/nonexistent.md",
        )
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, (
            "unresolvable memo path should FAIL (G-ARTIFACT-RA-MEMO-002)"
        )


def test_step1_memo_list_ac_definition_passes():
    """PASS: dash-prefixed AC-NNN 定義を受理する。"""
    with tempfile.TemporaryDirectory() as td:
        memo_body = _VALID_MEMO_BODY.replace(
            "AC-001: artifact gate",
            "- AC-001: artifact gate",
            1,
        )
        main = _build_step1_suite(Path(td), memo_body=memo_body)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 0, "dash-prefixed AC definition should PASS"


def test_step1_memo_near_ac_reference_fails():
    """FAIL: AC-0011 は AC-001 の完全一致参照ではない。"""
    with tempfile.TemporaryDirectory() as td:
        memo_body = _VALID_MEMO_BODY.replace(
            "AC-001 で gate が PASS する。",
            "AC-0011 で gate が PASS する。",
            1,
        )
        main = _build_step1_suite(Path(td), memo_body=memo_body)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "near AC-ID must not satisfy exact AC reference"


def test_step1_memo_ac_identifier_suffix_fails():
    """FAIL: 文字・ハイフンが続く AC-ID は完全一致参照ではない。"""
    cases = (
        _VALID_MEMO_BODY.replace(
            "AC-001 で gate が PASS する。",
            "AC-001foo で gate が PASS する。",
            1,
        ),
        _VALID_MEMO_BODY.replace(
            "AC-001 で gate が PASS する。",
            "AC-001-foo で gate が PASS する。",
            1,
        ),
        _VALID_MEMO_BODY.replace(
            "AC-001 を test fixture で検証する。",
            "AC-001foo を test fixture で検証する。",
            1,
        ).replace(
            "AC-001 の fixture を検証する。",
            "AC-001foo の fixture を検証する。",
            1,
        ),
        _VALID_MEMO_BODY.replace(
            "AC-001 を test fixture で検証する。",
            "AC-001-foo を test fixture で検証する。",
            1,
        ).replace(
            "AC-001 の fixture を検証する。",
            "AC-001-foo の fixture を検証する。",
            1,
        ),
    )
    for memo_body in cases:
        with tempfile.TemporaryDirectory() as td:
            main = _build_step1_suite(Path(td), memo_body=memo_body)
            rc = check_artifact(str(main), json_mode=True)
            assert rc == 1, "AC-ID with identifier suffix must not satisfy exact reference"


def test_step1_memo_ac_outside_acceptance_section_fails():
    """FAIL: 他節だけの AC-NNN: は受入条件の定義として扱わない。"""
    with tempfile.TemporaryDirectory() as td:
        memo_body = _VALID_MEMO_BODY.replace(
            "AC-001: artifact gate が正常系 fixture を受理する",
            "受入条件を確認する。",
            1,
        )
        main = _build_step1_suite(Path(td), memo_body=memo_body)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "AC definition outside acceptance section should FAIL"


def test_step1_issue_schema_fails():
    """FAIL: Issue 要素は mapping かつ RA-NNN 形式の id が必須。"""
    cases = (
        ("resolved_issues:\n  - bad\n", "G-ARTIFACT-RA-ISSUE-001"),
        ("non_blocking_issues:\n  - id: RA-1\n", "G-ARTIFACT-RA-ISSUE-001"),
        ("resolved_issues:\n  - id: ISSUE-001\n", "G-ARTIFACT-RA-ISSUE-001"),
    )
    with tempfile.TemporaryDirectory() as td:
        for case, expected_check_id in cases:
            main = _build_step1_suite(Path(td), main_extra=case)
            rc, check_ids = _check_artifact_json(main)
            assert rc == 1, f"invalid issue schema should FAIL: {case!r}"
            assert expected_check_id in check_ids, (
                f"expected {expected_check_id} for {case!r}, got {sorted(check_ids)}"
            )


def test_step1_issue_container_schema_fails():
    """FAIL: Issue コンテナは配列でなければならない。"""
    cases = (
        "resolved_issues: bad\n",
        "resolved_issues: {id: RA-001}\n",
        "non_blocking_issues: bad\n",
        "non_blocking_issues: {id: RA-001}\n",
    )
    with tempfile.TemporaryDirectory() as td:
        for case in cases:
            main = _build_step1_suite(Path(td), main_extra=case)
            rc = check_artifact(str(main), json_mode=True)
            assert rc == 1, f"non-list issue container should FAIL: {case!r}"


def test_step1_provenance_undecided_fails():
    """FAIL: normalize fields に provenance=undecided が残存。"""
    with tempfile.TemporaryDirectory() as td:
        bad_norm = (
            "status: complete\n"
            "step: step1-normalize\n"
            "gate_a: PASS\n"
            "blocking_open_issues: []\n"
            "task_type: bug_fix\n"
            "fields:\n"
            "  - name: target\n"
            "    value: foo\n"
            "    provenance: undecided\n"
            "    evidence_ref: none\n"
        )
        main = _build_step1_suite(Path(td), norm_fm=bad_norm)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "provenance=undecided should FAIL (G-ARTIFACT-RA-NORM-PROV-004)"


def test_step1_provenance_external_complete_fails():
    """FAIL: provenance=external のまま complete は不可。"""
    with tempfile.TemporaryDirectory() as td:
        bad_norm = (
            "status: complete\n"
            "step: step1-normalize\n"
            "gate_a: PASS\n"
            "blocking_open_issues: []\n"
            "task_type: new_feature\n"
            "fields:\n"
            "  - name: api_spec\n"
            "    value: pending\n"
            "    provenance: external\n"
            "    evidence_ref: awaiting vendor\n"
        )
        main = _build_step1_suite(Path(td), norm_fm=bad_norm)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "provenance=external on complete should FAIL (G-ARTIFACT-RA-NORM-PROV-005)"


def test_step1_docs_derived_evidence_missing_fails():
    """FAIL: provenance=docs_derived には非空 evidence_ref が必須。"""
    with tempfile.TemporaryDirectory() as td:
        bad_norm = (
            "status: complete\n"
            "step: step1-normalize\n"
            "gate_a: PASS\n"
            "blocking_open_issues: []\n"
            "task_type: bug_fix\n"
            "fields:\n"
            "  - name: spec\n"
            "    value: confirmed\n"
            "    provenance: docs_derived\n"
            '    evidence_ref: ""\n'
        )
        main = _build_step1_suite(Path(td), norm_fm=bad_norm)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, (
            "docs_derived without evidence_ref should FAIL "
            "(G-ARTIFACT-RA-NORM-PROV-006)"
        )


def test_step1_invalid_task_type_fails():
    """FAIL: normalize の task_type が不正値。"""
    with tempfile.TemporaryDirectory() as td:
        bad_norm = (
            "status: complete\n"
            "step: step1-normalize\n"
            "gate_a: PASS\n"
            "blocking_open_issues: []\n"
            "task_type: unknown_type\n"
            "fields:\n"
            "  - name: x\n"
            "    value: y\n"
            "    provenance: user_confirmed\n"
            "    evidence_ref: test\n"
        )
        main = _build_step1_suite(Path(td), norm_fm=bad_norm)
        rc = check_artifact(str(main), json_mode=True)
        assert rc == 1, "invalid task_type should FAIL (G-ARTIFACT-RA-NORM-PROV-001)"


def test_step1_provenance_non_mapping_field_fails():
    """FAIL: fields[] の非 mapping 要素は PROV-003 で拒否する。"""
    with tempfile.TemporaryDirectory() as td:
        bad_norm = (
            "status: complete\n"
            "step: step1-normalize\n"
            "gate_a: PASS\n"
            "task_type: bug_fix\n"
            "fields:\n"
            "  - bad\n"
        )
        main = _build_step1_suite(Path(td), norm_fm=bad_norm)
        rc, check_ids = _check_artifact_json(main)
        assert rc == 1, "non-mapping fields item should FAIL (G-ARTIFACT-RA-NORM-PROV-003)"
        assert "G-ARTIFACT-RA-NORM-PROV-003" in check_ids, (
            f"expected G-ARTIFACT-RA-NORM-PROV-003, got {sorted(check_ids)}"
        )


def main() -> int:
    tests = [
        test_step_required_fields_subset_of_doc,
        test_valid_steps_match_doc,
        test_valid_statuses,
        test_common_required,
        test_step1_complete,
        test_step2_complete,
        test_step3_complete,
        test_step3_missing_untracked_fails,
        test_step4_complete,
        test_blocked_with_reason,
        test_blocked_no_reason_fails,
        test_fatal_with_reason,
        test_fatal_no_reason_fails,
        test_complete_missing_field_fails,
        test_step1_blocking_issues_fails,
        test_step1_deferred_exit_fails,
        test_step1_missing_gate_fails,
        test_invalid_status_fails,
        test_invalid_step_fails,
        test_step3_blocked_adr_valid,
        test_step3_blocked_adr_no_sha_fails,
        test_step3_blocked_adr_few_alts_fails,
        test_step4_gate_results_form_b_passes,
        test_step4_gate_results_invalid_values_fail,
        test_step4_gate_results_key_set_fails,
        test_step1_intermediate_pass,
        test_step1_deep_fallback_pass,
        test_step1_norm_file_missing_fails,
        test_step1_depth_file_missing_fails,
        test_step1_wrong_slug_fails,
        test_step1_norm_schema_invalid_fails,
        test_step1_depth_schema_invalid_fails,
        test_step1_gate_source_mismatch_fails,
        test_step1_depth_consistency_fails,
        test_step1_deep_fallback_no_reason_fails,
        test_step1_deferred_to_standard_pass,
        test_step1_deferred_to_deep_pass,
        test_step1_ack_missing_passes,
        test_step1_ack_explicit_null_fails,
        test_step1_ack_digest_mismatch_fails,
        test_step1_ack_digest_case_difference_passes,
        test_step1_digest_malformed_fails,
        test_step1_campaign_slug_prefix_mismatch_fails,
        test_step1_campaign_slug_suffix_passes,
        test_step2_report_slug_must_match_campaign_slug,
        test_step1_memo_unresolvable_fails,
        test_step1_memo_list_ac_definition_passes,
        test_step1_memo_near_ac_reference_fails,
        test_step1_memo_ac_identifier_suffix_fails,
        test_step1_memo_ac_outside_acceptance_section_fails,
        test_step1_issue_schema_fails,
        test_step1_issue_container_schema_fails,
        test_step1_provenance_undecided_fails,
        test_step1_provenance_external_complete_fails,
        test_step1_docs_derived_evidence_missing_fails,
        test_step1_invalid_task_type_fails,
        test_step1_provenance_non_mapping_field_fails,
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
