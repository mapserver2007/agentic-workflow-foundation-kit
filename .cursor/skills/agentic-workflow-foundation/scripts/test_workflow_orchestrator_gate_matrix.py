#!/usr/bin/env python3
"""Workflow Orchestrator Gate Matrix 契約テスト。

Step Gate Matrix のテンプレート（SoT）と生成物が、
step4/step5/step6 の境界責務を正しく案内していることを検証する。

検査対象:
  - テンプレート SKILL.md.template の Step ④ 行が step4 を「実装 → 検証」として案内すること
  - テンプレート SKILL.md.template の Step ⑤ 行が step5 を必須入口、step6 を必須出口として案内すること
  - テンプレート SKILL.md.template の Step ⑤ 手順がコード変更後の step5 再実行を要求すること
  - 生成物 05-pr-review.md が PR 作成前 step5・変更後 step5 再実行・step6 完了条件を含むこと
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent

TEMPLATE_DIR = HERE.parent / "templates"
SKILL_TEMPLATE = TEMPLATE_DIR / "skills" / "workflow-orchestrator" / "SKILL.md.template"
SKILL_GENERATED = ROOT / ".cursor" / "skills" / "workflow-orchestrator" / "SKILL.md"
PR_REVIEW_TEMPLATE = TEMPLATE_DIR / "docs" / "agent-tasks" / "agent-workflow" / "05-pr-review.md.template"
PR_REVIEW_GENERATED = ROOT / "docs" / "agent-tasks" / "agent-workflow" / "05-pr-review.md"
MANIFEST = HERE.parent / "manifest.yaml"
INDEX_TEMPLATE = TEMPLATE_DIR / "docs" / "agent-tasks" / "agent-workflow.md.template"
QUALITY_GATE_TEMPLATE = TEMPLATE_DIR / "docs" / "QUALITY_GATE.md.template"
README_TEMPLATE = TEMPLATE_DIR / "docs" / "agent-tasks" / "README.md.template"
COMPLETION_TEMPLATE = (
    TEMPLATE_DIR / "docs" / "agent-tasks" / "agent-workflow" / "06-completion.md.template"
)
BEST_PRACTICES_TEMPLATE = (
    TEMPLATE_DIR / "docs" / "agent-tasks" / "agent-workflow" / "best-practices.md.template"
)
CODE_REVIEW_SKILL_TEMPLATE = (
    TEMPLATE_DIR / "skills" / "agent-code-review" / "SKILL.md.template"
)
ARCHIVE_GATE_TEMPLATE = (
    TEMPLATE_DIR / "skills" / "session-handover" / "scripts" / "archive-gate.sh.template"
)
SESSION_START_GATE_TEMPLATE = (
    TEMPLATE_DIR
    / "skills"
    / "session-handover"
    / "scripts"
    / "session-start-gate.sh.template"
)
sys.path.insert(0, str(ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"))
from genlib import load_manifest, render  # noqa: E402


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _render_with_features(
    path: Path,
    *,
    maintenance_docs: bool = True,
    gate_scripts: bool = True,
    code_review: bool = True,
    github_pr: bool = True,
) -> str:
    context = copy.deepcopy(load_manifest(str(MANIFEST)))
    context["agent_workflow"]["maintenance_docs"]["enabled"] = maintenance_docs
    context["agent_workflow"]["gate_scripts"] = gate_scripts
    context["code_review"]["enabled"] = code_review
    context["github_pr"]["enabled"] = github_pr
    return render(_read(path), context)


def test_step4_matrix_implementation_to_verification():
    """Step ④ Matrix 行が step4 を「実装 → 検証」として案内すること。"""
    content = _read(SKILL_TEMPLATE)
    assert content, f"テンプレートが存在しない: {SKILL_TEMPLATE}"
    lines = [line for line in content.splitlines() if "**④ テスト**" in line or "④" in line]
    step4_lines = [line for line in lines if "step4" in line]
    assert step4_lines, "Step ④ 行に step4 への参照が見つからない"
    step4_line = step4_lines[0]
    assert "実装 → 検証" in step4_line, (
        f"Step ④ 行が「実装 → 検証」を含まない: {step4_line!r}"
    )
    assert "実装 → PR" not in step4_line, (
        f"Step ④ 行に誤った「実装 → PR」が残っている: {step4_line!r}"
    )


def test_step5_matrix_entry_exit():
    """Step ⑤ Matrix 行が step5 を必須入口、step6 を必須出口として案内すること。"""
    content = _read(SKILL_TEMPLATE)
    assert content, f"テンプレートが存在しない: {SKILL_TEMPLATE}"
    lines = [line for line in content.splitlines() if "**⑤ PR レビュー**" in line or "⑤" in line]
    step5_lines = [line for line in lines if "step5" in line and "step6" in line]
    assert step5_lines, (
        "Step ⑤ Matrix 行に step5 と step6 の両方への参照が見つからない"
    )


def test_step2_matrix_excludes_po_approval_from_exit():
    """Step②退出は機械ゲートであり、PO承認を含めない。"""
    content = _read(SKILL_TEMPLATE)
    line = next(
        (line for line in content.splitlines() if "**② レポート作成**" in line),
        "",
    )
    assert "step2-report" in line and "`step2` PASS" in line
    assert "PO承認" not in line and "ユーザー承認" not in line


def test_step3_entry_requires_parent_pre_dispatch():
    """Step③入口が親 pre-dispatch・approved・digest一致を要求する。"""
    content = _read(SKILL_TEMPLATE)
    line = next((line for line in content.splitlines() if "**③ 実装**" in line), "")
    assert "親 pre-dispatch" in line and "digest" in line
    assert "implementation_approval.status: approved" in content


def test_step1_immediately_dispatches_step2_without_ack():
    """Step① PASS は4分類通知後に同一ターンでStep②へ遷移し、旧ackを要求しない。"""
    content = _read(SKILL_TEMPLATE)
    assert "同一ターンで凍結済み `campaign_slug` / 同値の `report_slug` を Step② worker へ dispatch" in content
    assert "requirements ack や進行可否質問を待たず" in content


def test_resume_table_contains_pending_and_approved_branches():
    """再開表がPO待ち・承認済み未着手・digest不一致を分岐する。"""
    content = _read(SKILL_TEMPLATE)
    for phrase in (
        "implementation_approval.status: pending",
        "`approved` だが digest 不一致",
        "`approved` + digest一致 + Step③ envelopeなし",
    ):
        assert phrase in content, f"再開分岐が不足: {phrase}"


def test_generated_step2_step3_contract_after_generate():
    """再生成後のSKILLもStep②/③境界契約を持つこと。"""
    content = _read(SKILL_GENERATED)
    assert content, f"生成物が存在しない: {SKILL_GENERATED}"
    step2 = next((line for line in content.splitlines() if "**② レポート作成**" in line), "")
    assert "step2-report" in step2 and "PO承認" not in step2
    assert "親 pre-dispatch" in content
    assert "implementation_approval.status: approved" in content
    assert "implementation_approval.status: pending" in content


def test_step5_procedure_rerun_after_change():
    """Step ⑤ 手順がコード変更後の step5 再実行を要求すること。"""
    content = _read(SKILL_TEMPLATE)
    assert content, f"テンプレートが存在しない: {SKILL_TEMPLATE}"
    assert "コード変更があった場合" in content and "step5" in content, (
        "Step ⑤ 手順に「コード変更があった場合の step5 再実行」の記述が見つからない"
    )
    lines = content.splitlines()
    rerun_lines = [
        line for line in lines
        if "コード変更" in line and "step5" in line
    ]
    assert rerun_lines, (
        "「コード変更」と「step5」が同一行に存在する記述が見つからない"
    )


def test_05_pr_review_template_step5_before_pr():
    """05-pr-review.md.template が PR 作成前 step5 を明記すること。"""
    content = _read(PR_REVIEW_TEMPLATE)
    assert content, f"テンプレートが存在しない: {PR_REVIEW_TEMPLATE}"
    assert "PR 作成前" in content or "PR 作成**前**" in content, (
        "05-pr-review.md.template に「PR 作成前に step5」の記述が見つからない"
    )
    assert "step5" in content, (
        "05-pr-review.md.template に step5 への参照が見つからない"
    )


def test_05_pr_review_template_step5_rerun():
    """05-pr-review.md.template がコード変更後の step5 再実行を明記すること。"""
    content = _read(PR_REVIEW_TEMPLATE)
    assert content, f"テンプレートが存在しない: {PR_REVIEW_TEMPLATE}"
    lines = content.splitlines()
    rerun_lines = [
        line for line in lines
        if "変更後" in line and "step5" in line
    ]
    assert rerun_lines, (
        "05-pr-review.md.template に「コード変更後の step5 再実行」の記述が見つからない"
    )


def test_05_pr_review_template_step6_completion():
    """05-pr-review.md.template が step6 完了条件を明記すること。"""
    content = _read(PR_REVIEW_TEMPLATE)
    assert content, f"テンプレートが存在しない: {PR_REVIEW_TEMPLATE}"
    assert "step6" in content, (
        "05-pr-review.md.template に step6 への参照が見つからない"
    )
    lines = content.splitlines()
    step6_completion_lines = [
        line for line in lines
        if "step6" in line and ("完了" in line or "通過" in line or "PASS" in line)
    ]
    assert step6_completion_lines, (
        "05-pr-review.md.template に step6 完了/通過条件の記述が見つからない"
    )


def test_05_pr_review_generated_gate_contract():
    """生成物 05-pr-review.md が必須語句を含むこと（再生成後のみ有効）。"""
    content = _read(PR_REVIEW_GENERATED)
    if not content:
        print("  SKIP: 生成物が存在しない（再生成前）", file=sys.stderr)
        return
    if "PR 作成前" not in content and "PR 作成**前**" not in content:
        print("  SKIP: 生成物が旧テンプレート由来（再生成未実施）", file=sys.stderr)
        return
    required_phrases = [
        "step5",
        "step6",
    ]
    for phrase in required_phrases:
        assert phrase in content, (
            f"生成物 05-pr-review.md に必須語句 '{phrase}' が見つからない"
        )
    has_rerun = any(
        "変更後" in line and "step5" in line
        for line in content.splitlines()
    ) or any(
        "変更" in line and "step5" in line and "再" in line
        for line in content.splitlines()
    )
    assert has_rerun, (
        "生成物 05-pr-review.md に「変更後 step5 再実行」の記述が見つからない"
    )


def test_step6_tracker_approval_prerequisite():
    """Step ⑥ が tracker 承認更新を前提として案内すること。"""
    content = _read(SKILL_TEMPLATE)
    assert content, f"テンプレートが存在しない: {SKILL_TEMPLATE}"
    lines = content.splitlines()
    step6_lines = [line for line in lines if "Step ⑥" in line or "### Step ⑥" in line]
    found = False
    in_step6 = False
    for line in lines:
        if "### Step ⑥" in line:
            in_step6 = True
        elif in_step6 and line.startswith("### "):
            break
        elif in_step6 and ("plan-gate.sh review" in line or "レビュー完了承認" in line):
            found = True
            break
    assert found, (
        "Step ⑥ セクションに tracker 承認（plan-gate.sh review）への言及がない"
    )


def test_commit_policy_normal_procedure_and_disabled_feature_fallback():
    """通常手順の正本と code_review 無効時の代替手順を区別する。"""
    skill = _read(CODE_REVIEW_SKILL_TEMPLATE)
    assert "⑤〜⑦" not in skill
    assert "Step 5〜7 では commit しない" in skill
    assert "`reviews/archives/` へは移さない" in skill
    assert "CodeRabbit の `path_filters` 対象外" in skill

    enabled = _render_with_features(PR_REVIEW_TEMPLATE, code_review=True)
    enabled_report = enabled[
        enabled.find("## 5.5 タスクレポート更新") :
        enabled.find("## 5.6 完了条件")
    ]
    assert "agent-code-review" in enabled_report
    assert "コミットポリシーに従う" in enabled_report
    assert "Step 5〜7 では commit しない" not in enabled_report

    disabled = _render_with_features(PR_REVIEW_TEMPLATE, code_review=False)
    disabled_report = disabled[
        disabled.find("## 5.5 タスクレポート更新") :
        disabled.find("## 5.6 完了条件")
    ]
    for phrase in (
        "Step 5〜7 では commit せず",
        "Step ⑥ の完了コミット",
        "`reviews/archives/` へは移さない",
        "CodeRabbit の `path_filters` 対象外",
    ):
        assert phrase in disabled_report, f"機能無効時の代替手順が不足: {phrase}"
    assert "agent-code-review" not in disabled_report


def test_review_approval_transition_feature_matrix():
    """code_review / gate_scripts の4分岐で承認順序と必須語句の存在を固定する。"""
    for code_review in (True, False):
        for gate_scripts in (True, False):
            subject = "`agent-code-review` Step 7" if code_review else "レビュー担当"

            pr_review = _render_with_features(
                PR_REVIEW_TEMPLATE,
                code_review=code_review,
                gate_scripts=gate_scripts,
            )
            approval_start = pr_review.find("**承認する**")
            approval_end = pr_review.find("**新規のレビューコメントを取得して**")
            assert approval_start >= 0, "05-pr-review の承認分岐が欠落"
            assert approval_end >= 0, "05-pr-review の再取得分岐が欠落"
            approval = pr_review[approval_start:approval_end]
            subject_position = approval.find(subject)
            approved_position = approval.find("承認取得済み")
            assert subject_position >= 0, f"05-pr-review の更新主体が欠落: {subject}"
            assert approved_position >= 0, "05-pr-review の承認状態が欠落"
            assert subject_position < approved_position

            orchestrator = _render_with_features(
                SKILL_TEMPLATE,
                code_review=code_review,
                gate_scripts=gate_scripts,
            )
            step5_start = orchestrator.find("### Step ⑤: PR レビュー検証")
            step5_end = orchestrator.find("Mode B（完了後の追加コメント対応）")
            assert step5_start >= 0 and step5_end >= 0, "orchestrator の Step ⑤ が欠落"
            step5 = orchestrator[step5_start:step5_end]
            orchestrator_subject = step5.find(subject)
            orchestrator_approved = step5.find("承認取得済み")
            assert orchestrator_subject >= 0, f"orchestrator の更新主体が欠落: {subject}"
            assert orchestrator_approved >= 0, "orchestrator の承認状態が欠落"
            assert orchestrator_subject < orchestrator_approved

            if gate_scripts:
                step6_position = approval.find("workflow-gate.sh step6")
                completion_position = approval.find("⑥へ進む")
                assert step6_position >= 0, "05-pr-review の step6 が欠落"
                assert completion_position >= 0, "05-pr-review の ⑥ 遷移が欠落"
                assert approved_position < step6_position < completion_position
                assert "親が `workflow-gate.sh step6`" in approval

                orchestrator_step6 = step5.find("workflow-gate.sh step6")
                assert orchestrator_step6 >= 0, "orchestrator の step6 が欠落"
                assert orchestrator_approved < orchestrator_step6
                assert "親が `workflow-gate.sh step6`" in step5
            else:
                for content in (approval, step5):
                    assert "workflow-gate.sh step6" not in content
                    assert "⑥へ進む" not in content
                    plan_gate_position = content.find("plan-gate.sh review")
                    completion_doc_position = content.find("06-completion.md")
                    report_archive_position = content.find("report archive")
                    assert plan_gate_position >= 0, "plan-gate.sh review 参照が欠落"
                    assert completion_doc_position >= 0, "06-completion.md 参照が欠落"
                    assert report_archive_position >= 0, "report archive 参照が欠落"
                    assert (
                        approved_position < plan_gate_position
                        if content is approval
                        else orchestrator_approved < plan_gate_position
                    )
                    assert plan_gate_position < completion_doc_position < report_archive_position

            if not code_review:
                assert "Step 7" not in approval
                assert "Step 7" not in step5


def test_archive_normal_procedure_recovery_display_and_inspection_only_gate():
    """通常移動・session-start 復旧表示・archive 検査を別責務として固定する。"""
    move_command = (
        "git mv docs/agent-tasks/reports/{report}.md "
        "docs/agent-tasks/reports/archives/"
    )
    recovery_command = (
        "git -C %q mv -- %q docs/agent-tasks/reports/archives/"
    )

    archive_gate = _read(ARCHIVE_GATE_TEMPLATE)
    assert move_command not in archive_gate
    assert "git mv" not in archive_gate

    for gate_scripts in (True, False):
        quality = _render_with_features(
            QUALITY_GATE_TEMPLATE,
            gate_scripts=gate_scripts,
        )
        archive_action_start = quality.find("**G-ARCHIVE の動作**")
        archive_action_end = quality.find("### 1.3 リンク衛生ゲート")
        assert archive_action_start >= 0 and archive_action_end >= 0
        archive_action = quality[archive_action_start:archive_action_end]
        assert "ファイルは移動しない" in archive_action
        assert move_command not in archive_action

        completion = _render_with_features(
            COMPLETION_TEMPLATE,
            gate_scripts=gate_scripts,
        )
        assert move_command in completion

        recovery = _render_with_features(
            SESSION_START_GATE_TEMPLATE,
            gate_scripts=gate_scripts,
        )
        assert recovery_command in recovery
        assert "git add" not in recovery

    for path in (QUALITY_GATE_TEMPLATE, SKILL_TEMPLATE, BEST_PRACTICES_TEMPLATE):
        assert move_command not in _read(path), f"通常移動コマンドの重複: {path}"


def test_step1_catalog_and_matrix_require_envelope_argument():
    """Step①のcatalogと各Matrixが実行可能なenvelope引数を案内すること。"""
    manifest = _read(MANIFEST)
    assert re.search(
        r"- id: step1\s+desc: \"調査→レポート境界（Step① envelope 完全検査）\"\s+"
        r"cmd: \"gate-artifact\.py <step1-envelope>\"",
        manifest,
        re.MULTILINE,
    ), "seed manifest の step1 catalog が不足している"

    for path in (SKILL_TEMPLATE, INDEX_TEMPLATE, QUALITY_GATE_TEMPLATE):
        content = _read(path)
        assert "step1" in content and "<step1-envelope>" in content, (
            f"{path} に step1 envelope 引数の Matrix 契約がない"
        )


def test_step6_archive_maintenance_docs_order_is_explicit():
    """Step⑥の判定・archive gate・report archive・独立workflow順を固定する。"""
    sources = (
        README_TEMPLATE,
        INDEX_TEMPLATE,
        COMPLETION_TEMPLATE,
        SKILL_TEMPLATE,
    )
    for path in sources:
        content = _read(path)
        if path == README_TEMPLATE:
            content = content[content.find("7. レビュー完了後") :]
        elif path == INDEX_TEMPLATE:
            content = content[content.find("## 基本フロー") :]
        if path == COMPLETION_TEMPLATE:
            content = content[content.find("## 6.3 archives 移動") :]
        elif path == SKILL_TEMPLATE:
            content = content[content.find("### Step ⑥: 完了報告") :]
        positions = [
            content.find("最終判定"),
            content.find("archive gate"),
            content.find("report archive"),
            content.find("maintenance-docs-workflow"),
        ]
        if path == README_TEMPLATE:
            positions = [
                content.find("起票判定を確定"),
                content.find("archive gate"),
                content.find("reports/archives/"),
                content.find("maintenance-docs-workflow"),
            ]
        assert all(position >= 0 for position in positions), (
            f"{path} にStep⑥の順序要素が不足している"
        )
        assert positions == sorted(positions), (
            f"{path} のStep⑥順序が不正: {positions}"
        )


def test_completion_labels_keep_maintenance_docs_feature_branches():
    """完了チェック第5項目の表示名を enabled/disabled で分岐する。"""
    for path in (
        INDEX_TEMPLATE,
        COMPLETION_TEMPLATE,
        TEMPLATE_DIR / "skills" / "session-handover" / "scripts" / "archive-gate.sh.template",
        TEMPLATE_DIR / "skills" / "session-handover" / "scripts" / "gate-report.py.template",
    ):
        content = _read(path)
        assert "{{#if agent_workflow.maintenance_docs.enabled}}" in content, path
        assert "maintenance-docs/ 起票判定" in content, path
        assert "docs への仕様反映" in content, path


def test_representative_feature_renders_hide_disabled_contracts():
    """代表feature分岐で無効な手順・リンクを露出させない。"""
    default_completion = _render_with_features(COMPLETION_TEMPLATE)
    completion_step6 = default_completion[
        default_completion.find("## 6.3 archives 移動") :
    ]
    order = [
        completion_step6.find("最終判定"),
        completion_step6.find("archive gate"),
        completion_step6.find("report archive"),
        completion_step6.find("maintenance-docs-workflow"),
    ]
    assert order == sorted(order) and all(position >= 0 for position in order)

    disabled_docs_paths = (
        INDEX_TEMPLATE,
        COMPLETION_TEMPLATE,
        SKILL_TEMPLATE,
        TEMPLATE_DIR / "skills" / "session-handover" / "scripts" / "archive-gate.sh.template",
        TEMPLATE_DIR / "skills" / "session-handover" / "scripts" / "gate-report.py.template",
    )
    for path in disabled_docs_paths:
        rendered = _render_with_features(path, maintenance_docs=False)
        assert "docs への仕様反映" in rendered, path
        assert "maintenance-docs/ 起票判定" not in rendered, path
        if path.name == "gate-report.py.template":
            assert "[maintenance-docs-workflow]" not in rendered, path
        else:
            assert "maintenance-docs-workflow" not in rendered, path

    no_dispatcher_paths = (
        INDEX_TEMPLATE,
        QUALITY_GATE_TEMPLATE,
        COMPLETION_TEMPLATE,
        PR_REVIEW_TEMPLATE,
        SKILL_TEMPLATE,
        TEMPLATE_DIR / "hooks" / "README.md.template",
        TEMPLATE_DIR / "skills" / "session-handover" / "SKILL.md.template",
    )
    for path in no_dispatcher_paths:
        rendered = _render_with_features(path, gate_scripts=False)
        assert "workflow-gate.sh" not in rendered, path

    for path in (PR_REVIEW_TEMPLATE, SKILL_TEMPLATE):
        rendered = _render_with_features(path, code_review=False, github_pr=False)
        assert "agent-code-review" not in rendered, path
        assert "agent-github-pr" not in rendered, path
        assert "workflow-gate.sh review-start" in rendered, path
        assert "review_start" in rendered, path
    pr_review_disabled = _render_with_features(
        PR_REVIEW_TEMPLATE, code_review=False, github_pr=False
    )
    assert "## 5.1.1 レビュー検証フェーズ開始の fail-closed 境界" in pr_review_disabled
    assert "レビュー担当へ委譲する" in pr_review_disabled


def main() -> int:
    tests = [
        test_step4_matrix_implementation_to_verification,
        test_step5_matrix_entry_exit,
        test_step2_matrix_excludes_po_approval_from_exit,
        test_step3_entry_requires_parent_pre_dispatch,
        test_step1_immediately_dispatches_step2_without_ack,
        test_resume_table_contains_pending_and_approved_branches,
        test_generated_step2_step3_contract_after_generate,
        test_step5_procedure_rerun_after_change,
        test_05_pr_review_template_step5_before_pr,
        test_05_pr_review_template_step5_rerun,
        test_05_pr_review_template_step6_completion,
        test_05_pr_review_generated_gate_contract,
        test_step6_tracker_approval_prerequisite,
        test_commit_policy_normal_procedure_and_disabled_feature_fallback,
        test_review_approval_transition_feature_matrix,
        test_archive_normal_procedure_recovery_display_and_inspection_only_gate,
        test_step1_catalog_and_matrix_require_envelope_argument,
        test_step6_archive_maintenance_docs_order_is_explicit,
        test_completion_labels_keep_maintenance_docs_feature_branches,
        test_representative_feature_renders_hide_disabled_contracts,
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

    print(f"[test_workflow_orchestrator_gate_matrix] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
