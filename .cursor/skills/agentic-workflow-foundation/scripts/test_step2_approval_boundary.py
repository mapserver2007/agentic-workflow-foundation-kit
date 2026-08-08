#!/usr/bin/env python3
"""Step②→③ 承認境界と digest の契約テスト。"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
GATE = ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "gate-artifact.py"
TEMPLATE_ROOT = HERE.parent / "templates"
GENERATED_PATHS = [
    ROOT / ".cursor/skills/workflow-orchestrator/SKILL.md",
    ROOT / ".cursor/skills/workflow-orchestrator/references/worker-dispatch.md",
    ROOT / ".cursor/skills/requirement-analysis/SKILL.md",
    ROOT / ".cursor/skills/requirement-analysis/references/requirement-contract.md",
    ROOT / "docs/agent-tasks/agent-workflow/02-report-creation.md",
    ROOT / "docs/agent-tasks/agent-workflow/03-implementation.md",
    ROOT / "docs/QUALITY_GATE.md",
]


def _gate():
    spec = importlib.util.spec_from_file_location("gate_artifact", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REPORT = """\
## 2. 問題・要件の詳細
- **対象**: API
- **対象外**: UI
- **requirements_digest**: abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789

## 5. 実装方針
既存の API 契約を維持して検証を追加する。

## 6. コード変更の詳細
| 変更対象ファイル | 変更箇所 | 変更内容 |
| --- | --- | --- |
| src/api.py | handler | 入力検証を追加 |

## 7. テスト計画
- [ ] 正常系を検証する
- [x] 不正入力を検証する

## 10. 完了チェック
- [ ] 実装完了
"""


def _approved_envelope(digest: str, report_path: Path, **overrides) -> dict:
    envelope = {
        "step": "step2",
        "status": "complete",
        "report_path": str(report_path),
        "implementation_approval": {
            "status": "approved",
            "approved_plan_digest": digest,
            "decider": "PO",
        },
    }
    envelope.update(overrides)
    return envelope


def test_payload_changes_invalidate_digest() -> None:
    gate = _gate()
    payload = gate.extract_approved_plan_payload(REPORT)
    assert payload == {
        "requirements_digest": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "scope_in": ["API"],
        "scope_out": ["UI"],
        "implementation_plan": "既存の API 契約を維持して検証を追加する。",
        "change_files": [{"path": "src/api.py", "change": "入力検証を追加"}],
        "test_plan": ["正常系を検証する", "不正入力を検証する"],
    }
    baseline = gate.compute_approved_plan_digest(REPORT)
    for changed in (
        REPORT.replace("既存の API 契約", "新しい API 契約"),
        REPORT.replace("src/api.py", "src/other.py"),
        REPORT.replace("正常系を検証する", "境界値を検証する"),
        REPORT.replace("- **対象**: API", "- **対象**: API と管理画面"),
    ):
        assert gate.compute_approved_plan_digest(changed) != baseline


def test_r3_text_preserves_digest() -> None:
    gate = _gate()
    assert gate.compute_approved_plan_digest(REPORT) == gate.compute_approved_plan_digest(
        REPORT.replace("- [ ] 実装完了", "- [x] 実装完了\n\n補足: 実装後の非ブロッキング記録")
    )


def test_pre_dispatch_fails_closed() -> None:
    gate = _gate()
    digest = gate.compute_approved_plan_digest(REPORT)
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "report.md"
        report_path.write_text(REPORT, encoding="utf-8")
        approved = _approved_envelope(digest, report_path)
        assert gate.validate_implementation_approval(approved, REPORT, report_path)[0]
        for approval in (
            _approved_envelope(
                digest,
                report_path,
                implementation_approval={
                    "status": "pending",
                    "approved_plan_digest": digest,
                    "decider": "PO",
                },
            ),
            _approved_envelope(
                digest,
                report_path,
                implementation_approval={
                    "status": "approved",
                    "approved_plan_digest": "bad",
                    "decider": "PO",
                },
            ),
            _approved_envelope(
                digest,
                report_path,
                implementation_approval={
                    "status": "approved",
                    "approved_plan_digest": digest,
                    "decider": "agent",
                },
            ),
            {"step": "step2", "status": "complete", "report_path": str(report_path)},
        ):
            assert not gate.validate_implementation_approval(approval, REPORT, report_path)[0]
        for malformed in (
            REPORT.replace("- **対象外**: UI\n", ""),
            REPORT.replace("既存の API 契約を維持して検証を追加する。", ""),
            REPORT.replace("| src/api.py | handler | 入力検証を追加 |\n", ""),
            REPORT.replace("- [ ] 正常系を検証する\n- [x] 不正入力を検証する\n", ""),
            REPORT.replace("abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789", "bad", 1),
        ):
            assert not gate.validate_implementation_approval(approved, malformed, report_path)[0]


def test_step_status_report_path_binding() -> None:
    """#1: 誤 step / 非 complete / report_path 不一致は FAIL。"""
    gate = _gate()
    digest = gate.compute_approved_plan_digest(REPORT)
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "report.md"
        other_path = Path(tmp) / "other.md"
        report_path.write_text(REPORT, encoding="utf-8")
        other_path.write_text(REPORT, encoding="utf-8")
        ok = _approved_envelope(digest, report_path)
        assert gate.validate_implementation_approval(ok, REPORT, report_path)[0]

        wrong_step = _approved_envelope(digest, report_path, step="step1")
        assert not gate.validate_implementation_approval(wrong_step, REPORT, report_path)[0]

        wrong_status = _approved_envelope(digest, report_path, status="incomplete")
        assert not gate.validate_implementation_approval(wrong_status, REPORT, report_path)[0]

        mismatched = _approved_envelope(digest, other_path)
        assert not gate.validate_implementation_approval(mismatched, REPORT, report_path)[0]


def test_pre_dispatch_subcommand_rejects_wrong_position() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(GATE),
            str(GATE),
            "--check-implementation-approval",
            str(GATE),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 2
    assert "--check-implementation-approval" in result.stdout


def test_validated_report_snapshot_binds_worker_input() -> None:
    """検証後に report が変わっても worker 入力 snapshot は変化しない。"""
    gate = _gate()
    digest = gate.compute_approved_plan_digest(REPORT)
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "report.md"
        envelope_path = Path(tmp) / "step2.md"
        report_path.write_text(REPORT, encoding="utf-8")
        envelope_path.write_text(
            "---\n"
            + json.dumps(
                _approved_envelope(digest, report_path),
                ensure_ascii=False,
            )
            + "\n---\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(GATE),
                "--check-implementation-approval",
                str(envelope_path),
                str(report_path),
                "--emit-validated-report-json",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        assert result.returncode == 0, result.stdout
        payload = json.loads(result.stdout)
        assert payload["valid"] is True
        assert payload["approved_plan_digest"] == digest
        assert payload["validated_report_snapshot"] == REPORT

        report_path.write_text(
            REPORT.replace("既存の API 契約", "未承認の API 契約"),
            encoding="utf-8",
        )
        assert payload["validated_report_snapshot"] != report_path.read_text(encoding="utf-8")
        assert gate.compute_approved_plan_digest(payload["validated_report_snapshot"]) == digest


def test_template_and_generated_boundary_contract() -> None:
    template_paths = [
        TEMPLATE_ROOT / "skills/workflow-orchestrator/SKILL.md.template",
        TEMPLATE_ROOT / "skills/workflow-orchestrator/references/worker-dispatch.md.template",
        TEMPLATE_ROOT / "skills/requirement-analysis/SKILL.md.template",
        TEMPLATE_ROOT / "skills/requirement-analysis/references/requirement-contract.md.template",
        TEMPLATE_ROOT / "docs/agent-tasks/agent-workflow/02-report-creation.md.template",
        TEMPLATE_ROOT / "docs/agent-tasks/agent-workflow/03-implementation.md.template",
        TEMPLATE_ROOT / "docs/QUALITY_GATE.md.template",
    ]
    legacy = (
        "Step②内承認",
        "この内容で実装を進めてよろしいですか？",
        "Step②承認後",
        "全て `[ ]` | Step ③",
        "step2-report PASS 後に削除",
        "step2-report PASS 後に step1 envelope と同時に削除",
        "Advisory fail-closed",
    )
    required = (
        "必須の親 pre-dispatch fail-closed 検査",
        "例外（Step①系）",
        "dispatch 前の強制削除義務はない",
        "状態を書き換えず",
        "R1/R2",
        "pending",
        "approved_plan_digest",
        "validated_report_snapshot",
        "POレビュー待ち",
        "implementation_approval.status: approved",
    )
    for paths in (template_paths, GENERATED_PATHS):
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for phrase in required:
            assert phrase in text, f"契約文言が欠落: {phrase}"
        for phrase in legacy:
            assert phrase not in text, f"旧契約が残存: {phrase}"

    impl_template = (
        TEMPLATE_ROOT / "docs/agent-tasks/agent-workflow/03-implementation.md.template"
    ).read_text(encoding="utf-8")
    impl_generated = (
        ROOT / "docs/agent-tasks/agent-workflow/03-implementation.md"
    ).read_text(encoding="utf-8")
    for content in (impl_template, impl_generated):
        assert "| `approved_plan` |" not in content
        assert "| `approved_plan_digest` |" in content
        assert "| `validated_report_snapshot` |" in content
        assert "実装方針の唯一入力" in content
        assert "実装方針の入力として再読込しない" in content


def test_approval_copy_remains_within_ten_required_sections() -> None:
    """実装開始承認は完了チェックのsubsectionであり、第11必須節ではない。"""
    paths = (
        TEMPLATE_ROOT / "docs/agent-tasks/agent-workflow/02-report-creation.md.template",
        ROOT / "docs/agent-tasks/agent-workflow/02-report-creation.md",
    )
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "11. **実装開始承認**" not in content
        assert "## 11. 実装開始承認" not in content
        assert "### 実装開始承認（人間可読同期コピー）" in content
        assert content.count("## 10. 完了チェック") == 1


def main() -> int:
    tests = [
        test_payload_changes_invalidate_digest,
        test_r3_text_preserves_digest,
        test_pre_dispatch_fails_closed,
        test_step_status_report_path_binding,
        test_pre_dispatch_subcommand_rejects_wrong_position,
        test_validated_report_snapshot_binds_worker_input,
        test_template_and_generated_boundary_contract,
        test_approval_copy_remains_within_ten_required_sections,
    ]
    for test in tests:
        test()
    print(f"[test_step2_approval_boundary] {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
