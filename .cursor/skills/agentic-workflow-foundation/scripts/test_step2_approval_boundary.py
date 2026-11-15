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
sys.path.insert(0, str(HERE))
import _contract_markers as cm  # noqa: E402
GENERATED_PATHS = [
    ROOT / ".cursor/skills/workflow-orchestrator/SKILL.md",
    ROOT / ".cursor/skills/workflow-orchestrator/references/worker-dispatch.md",
    ROOT / ".cursor/skills/requirement-analysis/SKILL.md",
    ROOT / ".cursor/skills/requirement-analysis/references/requirement-contract.md",
    ROOT / ".cursor/skills/requirement-analysis/references/user-presentation.md",
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


def _contract_sources() -> list:
    """(label, template_path, generated_path) を返す。契約マーカーは両方に存在する。"""
    pairs = [
        ("skills/workflow-orchestrator/SKILL.md", ".cursor/skills/workflow-orchestrator/SKILL.md"),
        (
            "skills/workflow-orchestrator/references/worker-dispatch.md",
            ".cursor/skills/workflow-orchestrator/references/worker-dispatch.md",
        ),
        ("skills/requirement-analysis/SKILL.md", ".cursor/skills/requirement-analysis/SKILL.md"),
        (
            "skills/requirement-analysis/references/requirement-contract.md",
            ".cursor/skills/requirement-analysis/references/requirement-contract.md",
        ),
        (
            "docs/agent-tasks/agent-workflow/02-report-creation.md",
            "docs/agent-tasks/agent-workflow/02-report-creation.md",
        ),
        (
            "docs/agent-tasks/agent-workflow/03-implementation.md",
            "docs/agent-tasks/agent-workflow/03-implementation.md",
        ),
    ]
    return [
        (label, TEMPLATE_ROOT / f"{label}.template", ROOT / generated)
        for label, generated in pairs
    ]


# 契約マーカー: (対象 label, marker id, 同一行に存在すべき安定トークン)
# 文言ではなく「その契約が、その文書に1箇所だけ存在すること」を固定する。
BOUNDARY_MARKERS = (
    (
        "skills/workflow-orchestrator/SKILL.md",
        "step3-parent-pre-dispatch-fail-closed",
        ("implementation_approval.status: approved", "digest", "pending", "R1/R2"),
    ),
    (
        "skills/workflow-orchestrator/SKILL.md",
        "resume-pending-approval",
        ("implementation_approval.status: pending",),
    ),
    (
        "skills/workflow-orchestrator/SKILL.md",
        "step1-pass-dispatches-step2-immediately",
        ("campaign_slug", "dispatch"),
    ),
    (
        "skills/workflow-orchestrator/references/worker-dispatch.md",
        "step1-artifact-retention-exception",
        ("implementation_approval.status: approved", "digest"),
    ),
    (
        "skills/workflow-orchestrator/references/worker-dispatch.md",
        "step1-pass-dispatches-step2-immediately",
        ("dispatch",),
    ),
    (
        "skills/requirement-analysis/SKILL.md",
        "step1-pass-dispatches-step2-immediately",
        ("dispatch",),
    ),
    (
        "skills/requirement-analysis/references/requirement-contract.md",
        "step1-pass-dispatches-step2-immediately",
        ("dispatch",),
    ),
    (
        "docs/agent-tasks/agent-workflow/02-report-creation.md",
        "step3-checker-does-not-mutate-state",
        ("--check-implementation-approval", "pending", "R1/R2"),
    ),
)


def test_template_and_generated_boundary_contract() -> None:
    template_paths = [
        TEMPLATE_ROOT / "skills/workflow-orchestrator/SKILL.md.template",
        TEMPLATE_ROOT / "skills/workflow-orchestrator/references/worker-dispatch.md.template",
        TEMPLATE_ROOT / "skills/requirement-analysis/SKILL.md.template",
        TEMPLATE_ROOT / "skills/requirement-analysis/references/requirement-contract.md.template",
        TEMPLATE_ROOT / "skills/requirement-analysis/references/user-presentation.md.template",
        TEMPLATE_ROOT / "docs/agent-tasks/agent-workflow/02-report-creation.md.template",
        TEMPLATE_ROOT / "docs/agent-tasks/agent-workflow/03-implementation.md.template",
        TEMPLATE_ROOT / "docs/QUALITY_GATE.md.template",
    ]
    # 旧契約の再混入防止（旧文言そのものを禁止するため固定文字列で検査する）
    legacy = (
        "Step②内承認",
        "この内容で実装を進めてよろしいですか？",
        "Step②承認後",
        "全て `[ ]` | Step ③",
        "step2-report PASS 後に削除",
        "step2-report PASS 後に step1 envelope と同時に削除",
        "Advisory fail-closed",
        "再ack",
        "Step ② レポート作成に進んでよろしいですか？",
    )
    # 状態値・識別子（機械が解釈するトークン）は固定文字列で検査する。
    required_tokens = (
        "R1/R2",
        "pending",
        "approved_plan_digest",
        "validated_report_snapshot",
        "implementation_approval.status: approved",
    )
    for paths in (template_paths, GENERATED_PATHS):
        text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for token in required_tokens:
            assert token in text, f"契約トークンが欠落: {token}"
        for phrase in legacy:
            assert phrase not in text, f"旧契約が残存: {phrase}"

    for label, template_path, generated_path in _contract_sources():
        for kind, path in (("template", template_path), ("generated", generated_path)):
            text = path.read_text(encoding="utf-8")
            for marker_label, marker, tokens in BOUNDARY_MARKERS:
                if marker_label != label:
                    continue
                cm.require_tokens_on_line(
                    text,
                    marker,
                    tokens,
                    label=f"{kind}:{label}",
                )

    impl_template = (
        TEMPLATE_ROOT / "docs/agent-tasks/agent-workflow/03-implementation.md.template"
    ).read_text(encoding="utf-8")
    impl_generated = (
        ROOT / "docs/agent-tasks/agent-workflow/03-implementation.md"
    ).read_text(encoding="utf-8")
    for kind, content in (("template", impl_template), ("generated", impl_generated)):
        assert "| `approved_plan` |" not in content  # 旧 payload 名の再混入防止
        assert "| `approved_plan_digest` |" in content
        assert "| `validated_report_snapshot` |" in content
        cm.require_tokens_on_line(
            content,
            "payload-snapshot-sole-input",
            ("validated_report_snapshot",),
            label=f"{kind}:03-implementation snapshot",
        )
        cm.require_tokens_on_line(
            content,
            "payload-report-path-no-reread",
            ("report_path",),
            label=f"{kind}:03-implementation report_path",
        )


def test_approval_copy_remains_within_ten_required_sections() -> None:
    """実装開始承認は完了チェックのsubsectionであり、第11必須節ではない。"""
    paths = (
        TEMPLATE_ROOT / "docs/agent-tasks/agent-workflow/02-report-creation.md.template",
        ROOT / "docs/agent-tasks/agent-workflow/02-report-creation.md",
    )
    for path in paths:
        content = path.read_text(encoding="utf-8")
        # 旧形式（独立した第11必須節）の再混入防止
        assert "11. **実装開始承認**" not in content
        assert "## 11. 実装開始承認" not in content
        # 完了チェック節（## 10.）の後ろに、承認コピー subsection が1個だけ存在する
        marker = cm.require(content, "approval-copy-subsection", label=str(path.name))
        assert content.count("## 10. 完了チェック") == 1
        assert content.index("## 10. 完了チェック") < marker.start


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
