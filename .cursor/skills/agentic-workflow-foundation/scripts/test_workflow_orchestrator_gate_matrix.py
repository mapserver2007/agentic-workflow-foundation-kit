#!/usr/bin/env python3
"""Workflow Orchestrator Gate Matrix 契約テスト。

Step Gate Matrix のテンプレート（SoT）と feature 分岐が、
step4/step5/step6 の境界責務を正しく案内していることを検証する。

検査対象:
  - テンプレート SKILL.md.template の Step ④ 行が step4 を「実装 → 検証」として案内すること
  - テンプレート SKILL.md.template の Step ⑤ 行が step5 を必須入口、step6 を必須出口として案内すること
  - テンプレート SKILL.md.template の Step ⑤ 手順がコード変更後の step5 再実行を要求すること
  - 05-pr-review.md.template が PR 作成前 step5・変更後 step5 再実行・step6 完了条件を含むこと

検査方式:
  生成物の日本語文言そのものではなく、契約マーカー（`<!-- contract: <id> -->`）の
  存在・個数・順序・範囲と、同一行の安定トークン（コマンド名・ファイル名・状態値）を検査する。
  文言を推敲してもテストは落ちない。マーカー検査は `_contract_markers.py` に集約する。
  マーカーを使わないのは、機械が解釈する契約値（完了チェック項目名・コマンド文字列・ID）のみ。
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
PR_REVIEW_TEMPLATE = TEMPLATE_DIR / "docs" / "agent-tasks" / "agent-workflow" / "05-pr-review.md.template"
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

sys.path.insert(0, str(HERE))
import _contract_markers as cm  # noqa: E402


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
    requirement_analysis: bool = True,
) -> str:
    context = copy.deepcopy(load_manifest(str(MANIFEST)))
    context["requirement_analysis"]["enabled"] = requirement_analysis
    context["agent_workflow"]["maintenance_docs"]["enabled"] = maintenance_docs
    context["agent_workflow"]["gate_scripts"] = gate_scripts
    context["code_review"]["enabled"] = code_review
    context["github_pr"]["enabled"] = github_pr
    return render(_read(path), context)


def test_step4_matrix_implementation_to_verification():
    """Step ④ Matrix 行が step4 を「実装 → 検証」として案内すること。"""
    marker = "matrix-step4-impl-then-verify"
    for gate_scripts in (True, False):
        for path in (SKILL_TEMPLATE, INDEX_TEMPLATE):
            rendered = _render_with_features(path, gate_scripts=gate_scripts)
            tokens = ["04-testing.md"]
            if gate_scripts:
                tokens.append("workflow-gate.sh step4")
            cm.require_tokens_on_line(
                rendered,
                marker,
                tokens,
                forbidden=("実装 → PR",),  # 旧契約（検証前に PR へ進む）の再混入防止
                label=f"{path.name} gate_scripts={gate_scripts}",
            )


def test_step5_matrix_entry_exit():
    """Step ⑤ Matrix 行が step5 を必須入口、step6 を必須出口として案内すること。"""
    gated = _render_with_features(SKILL_TEMPLATE, gate_scripts=True)
    cm.require_tokens_on_line(
        gated,
        "matrix-step5-gate-chain",
        ("05-pr-review.md", "workflow-gate.sh step5", "review-start", "step6"),
        ordered=True,
        label="orchestrator Matrix Step⑤ (gate_scripts)",
    )
    plain = _render_with_features(SKILL_TEMPLATE, gate_scripts=False)
    cm.require_tokens_on_line(
        plain,
        "matrix-step5-gate-chain",
        ("05-pr-review.md",),
        forbidden=("workflow-gate.sh",),
        label="orchestrator Matrix Step⑤ (no gate_scripts)",
    )


def test_step2_matrix_excludes_po_approval_from_exit():
    """Step②退出は機械ゲートであり、PO承認を含めない。"""
    content = _render_with_features(SKILL_TEMPLATE)
    cm.require_tokens_on_line(
        content,
        "matrix-step2-machine-exit",
        ("02-report-creation.md", "`step2-report` PASS", "`step2` PASS"),
        forbidden=("PO承認", "ユーザー承認"),  # 退出条件に人間承認を混ぜない
        label="orchestrator Matrix Step②",
    )


def test_step3_entry_requires_parent_pre_dispatch():
    """Step③入口が親 pre-dispatch・approved・digest一致を要求する。"""
    content = _render_with_features(SKILL_TEMPLATE)
    cm.require_tokens_on_line(
        content,
        "matrix-step3-entry-pre-dispatch",
        ("03-implementation.md", "digest"),
        label="orchestrator Matrix Step③",
    )
    assert "implementation_approval.status: approved" in content


def test_step1_immediately_dispatches_step2_without_ack():
    """Step① PASS は4分類通知後に同一ターンでStep②へ遷移し、旧ackを要求しない。

    「旧 ack を要求しない」側は test_step2_approval_boundary.py の旧契約語リスト
    （再ack 等）が検査する。ここでは即時遷移の契約マーカーとその主要トークンを確認する。
    """
    content = _render_with_features(SKILL_TEMPLATE, requirement_analysis=True)
    cm.require_tokens_on_line(
        content,
        "step1-pass-dispatches-step2-immediately",
        ("campaign_slug", "report_slug", "dispatch"),
        label="orchestrator Step①",
    )
    disabled = _render_with_features(SKILL_TEMPLATE, requirement_analysis=False)
    cm.require_absent(
        disabled,
        "step1-pass-dispatches-step2-immediately",
        reference=content,
        label="requirement_analysis 無効",
    )


def test_resume_table_contains_pending_and_approved_branches():
    """再開表がPO待ち・承認済み未着手・digest不一致を分岐する。"""
    content = _render_with_features(SKILL_TEMPLATE)
    cm.require_tokens_on_line(
        content,
        "resume-pending-approval",
        ("implementation_approval.status: pending",),
        label="再開表: PO待ち",
    )
    cm.require_tokens_on_line(
        content,
        "resume-approved-digest-mismatch",
        ("approved", "digest"),
        label="再開表: digest 不一致",
    )
    cm.require_tokens_on_line(
        content,
        "resume-approved-digest-match-no-step3-envelope",
        ("approved", "digest", "Step③"),
        label="再開表: 承認済み未着手",
    )
    cm.require_order(
        content,
        (
            "resume-pending-approval",
            "resume-approved-digest-mismatch",
            "resume-approved-digest-match-no-step3-envelope",
        ),
        label="再開表の分岐順",
    )


def test_step5_procedure_rerun_after_change():
    """Step ⑤ 手順がコード変更後の step5 再実行を要求すること。"""
    content = _render_with_features(SKILL_TEMPLATE, gate_scripts=True)
    cm.require_in_span(
        content,
        "orchestrator-step5",
        "step5-rerun-after-code-change",
        end_outer="orchestrator-step6",
        label="orchestrator Step⑤",
    )
    cm.require_tokens_on_line(
        content,
        "step5-rerun-after-code-change",
        ("workflow-gate.sh step5",),
        label="orchestrator Step⑤ 再実行",
    )
    plain = _render_with_features(SKILL_TEMPLATE, gate_scripts=False)
    cm.require_absent(
        plain,
        "step5-rerun-after-code-change",
        reference=content,
        label="gate_scripts 無効",
    )


def test_05_pr_review_template_step5_before_pr():
    """05-pr-review.md.template が PR 作成前 step5 を明記すること。"""
    content = _render_with_features(PR_REVIEW_TEMPLATE, gate_scripts=True)
    cm.require_in_span(
        content,
        "pr-review-completion-conditions",
        "pr-review-completion-step5-before-pr",
        end_outer="pr-review-approval-gate",
        label="05-pr-review §完了条件",
    )
    cm.require_tokens_on_line(
        content,
        "pr-review-completion-step5-before-pr",
        ("workflow-gate.sh step5",),
        label="05-pr-review PR 作成前 step5",
    )


def test_05_pr_review_template_step5_rerun():
    """05-pr-review.md.template がコード変更後の step5 再実行を明記すること。"""
    content = _render_with_features(PR_REVIEW_TEMPLATE, gate_scripts=True)
    cm.require_in_span(
        content,
        "pr-review-completion-conditions",
        "pr-review-completion-step5-rerun-after-change",
        end_outer="pr-review-approval-gate",
        label="05-pr-review §完了条件",
    )
    cm.require_tokens_on_line(
        content,
        "pr-review-completion-step5-rerun-after-change",
        ("workflow-gate.sh step5",),
        label="05-pr-review 変更後 step5 再実行",
    )


def test_commit_policy_normal_procedure_and_disabled_feature_fallback():
    """通常手順の正本と code_review 無効時の代替手順を区別する。"""
    skill = _render_with_features(CODE_REVIEW_SKILL_TEMPLATE)
    assert "⑤〜⑦" not in skill  # 旧表記（Step 範囲）の再混入防止
    cm.require_tokens_on_line(
        skill,
        "code-review-commit-policy",
        ("reviews/archives/", "path_filters"),
        label="agent-code-review コミットポリシー",
    )

    enabled = _render_with_features(PR_REVIEW_TEMPLATE, code_review=True)
    disabled = _render_with_features(PR_REVIEW_TEMPLATE, code_review=False)
    reference = enabled + "\n" + disabled
    delegated = "pr-review-report-commit-policy-delegated"
    inline = "pr-review-report-commit-policy-inline"

    enabled_report = cm.span(
        enabled, "pr-review-report-update", "pr-review-report-update-end", label="code_review 有効"
    )
    cm.require(enabled_report, delegated, label="code_review 有効")
    cm.require_absent(enabled_report, inline, reference=reference, label="code_review 有効")
    cm.require_tokens_on_line(
        enabled,
        delegated,
        ("agent-code-review",),
        label="code_review 有効: 正本への委譲",
    )

    disabled_report = cm.span(
        disabled, "pr-review-report-update", "pr-review-report-update-end", label="code_review 無効"
    )
    cm.require(disabled_report, inline, label="code_review 無効")
    cm.require_absent(disabled_report, delegated, reference=reference, label="code_review 無効")
    cm.require_tokens_on_line(
        disabled,
        inline,
        ("reviews/archives/", "path_filters"),
        forbidden=("agent-code-review",),
        label="code_review 無効: 代替手順",
    )
    assert "agent-code-review" not in disabled_report


def _assert_approval_transition_line(
    rendered: str,
    marker: str,
    *,
    code_review: bool,
    gate_scripts: bool,
    label: str,
) -> str:
    """承認 → 追跡ドキュメント更新 → 次工程 の遷移行を、安定トークンの順序で検査する。"""
    if gate_scripts:
        tokens = ["承認取得済み", "workflow-gate.sh step6"]
        forbidden = []
    else:
        tokens = ["承認取得済み", "plan-gate.sh review", "06-completion.md", "report archive"]
        forbidden = ["workflow-gate.sh"]
    if code_review:
        tokens.insert(0, "agent-code-review")
    else:
        forbidden.append("agent-code-review")
        forbidden.append("Step 7")
    return cm.require_tokens_on_line(
        rendered,
        marker,
        tokens,
        forbidden=forbidden,
        ordered=True,
        label=label,
    )


def test_review_approval_transition_feature_matrix():
    """code_review / gate_scripts の4分岐で承認順序と必須契約の存在を固定する。"""
    for code_review in (True, False):
        for gate_scripts in (True, False):
            variant = f"code_review={code_review} gate_scripts={gate_scripts}"

            pr_review = _render_with_features(
                PR_REVIEW_TEMPLATE,
                code_review=code_review,
                gate_scripts=gate_scripts,
            )
            approval = cm.span(
                pr_review,
                "pr-review-approval-gate",
                "pr-review-approval-fetch-new-comments",
                label=f"05-pr-review 承認分岐 ({variant})",
            )
            cm.require(approval, "pr-review-approval-transition", label=f"05-pr-review ({variant})")
            _assert_approval_transition_line(
                pr_review,
                "pr-review-approval-transition",
                code_review=code_review,
                gate_scripts=gate_scripts,
                label=f"05-pr-review 承認順序 ({variant})",
            )

            completion = cm.span(
                pr_review,
                "pr-review-completion-conditions",
                "pr-review-approval-gate",
                label=f"05-pr-review 完了条件 ({variant})",
            )
            step6_marker = "pr-review-completion-step6-after-approval"
            if gate_scripts:
                cm.require_tokens_on_line(
                    pr_review,
                    step6_marker,
                    ("workflow-gate.sh step6",),
                    label=f"05-pr-review step6 通過条件 ({variant})",
                )
                cm.require_in_span(
                    pr_review,
                    "pr-review-completion-conditions",
                    step6_marker,
                    end_outer="pr-review-approval-gate",
                    label=f"05-pr-review step6 通過条件の位置 ({variant})",
                )
            else:
                reference = _render_with_features(PR_REVIEW_TEMPLATE, gate_scripts=True)
                cm.require_absent(
                    completion, step6_marker, reference=reference, label=f"05-pr-review ({variant})"
                )

            orchestrator = _render_with_features(
                SKILL_TEMPLATE,
                code_review=code_review,
                gate_scripts=gate_scripts,
            )
            step5 = cm.span(
                orchestrator,
                "orchestrator-step5",
                "step5-mode-b-excluded",
                label=f"orchestrator Step⑤ ({variant})",
            )
            step6 = cm.span(
                orchestrator,
                "orchestrator-step6",
                "orchestrator-context-budget",
                label=f"orchestrator Step⑥ ({variant})",
            )
            cm.require(step5, "step5-approval-transition", label=f"orchestrator Step⑤ ({variant})")
            _assert_approval_transition_line(
                orchestrator,
                "step5-approval-transition",
                code_review=code_review,
                gate_scripts=gate_scripts,
                label=f"orchestrator Step⑤ 承認順序 ({variant})",
            )
            cm.require_tokens_on_line(
                orchestrator,
                "orchestrator-step6-precondition",
                ("plan-gate.sh review",),
                label=f"orchestrator Step⑥ 前提 ({variant})",
            )
            cm.require(step6, "orchestrator-step6-precondition", label=f"orchestrator Step⑥ ({variant})")
            if gate_scripts:
                cm.require_tokens_on_line(
                    orchestrator,
                    "orchestrator-step6-precondition",
                    ("workflow-gate.sh step6",),
                    label=f"orchestrator Step⑥ 前提 ({variant})",
                )


def test_archive_procedure_and_inspection_only_gate():
    """通常移動・session-start 復旧表示・archive 検査を別責務として固定する。"""
    move_command = (
        "git mv docs/agent-tasks/reports/{report}.md "
        "docs/agent-tasks/reports/archives/"
    )
    recovery_command = (
        "git -C %q mv -- %q docs/agent-tasks/reports/archives/"
    )

    archive_gate = _read(ARCHIVE_GATE_TEMPLATE)
    assert "git mv" not in archive_gate

    quality = _render_with_features(QUALITY_GATE_TEMPLATE)
    cm.require_tokens_on_line(
        quality,
        "quality-gate-archive-inspection-only",
        ("archive-gate.sh", "06-completion.md"),
        forbidden=("git mv",),  # archive gate は検査専用。移動コマンドを持たない
        label="QUALITY_GATE G-ARCHIVE",
    )

    for gate_scripts in (True, False):
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

    assert "git add" not in _read(SESSION_START_GATE_TEMPLATE)

    for path in (QUALITY_GATE_TEMPLATE, SKILL_TEMPLATE, BEST_PRACTICES_TEMPLATE):
        assert move_command not in _read(path), f"通常移動コマンドの重複: {path}"


def _find_step_gate(node, gate_id: str):
    """manifest 内の step_gates catalog から id 一致のエントリを再帰的に探す。"""
    if isinstance(node, dict):
        if node.get("id") == gate_id and "cmd" in node:
            return node
        for value in node.values():
            found = _find_step_gate(value, gate_id)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_step_gate(value, gate_id)
            if found is not None:
                return found
    return None


def test_step1_catalog_and_matrix_require_envelope_argument():
    """Step①のcatalogと各Matrixが実行可能なenvelope引数を案内すること。"""
    manifest = load_manifest(str(MANIFEST))
    entry = _find_step_gate(manifest, "step1")
    assert entry is not None, "seed manifest の step1 catalog が不足している"
    # desc は説明文のため検査しない。cmd は実行可能な契約値として検査する。
    assert entry["cmd"] == "gate-artifact.py <step1-envelope>", entry

    for path in (SKILL_TEMPLATE, INDEX_TEMPLATE, QUALITY_GATE_TEMPLATE):
        content = _read(path)
        assert "<step1-envelope>" in content, (
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
    judgment = "step6-order-final-judgment"
    archive_gate = "step6-order-archive-gate"
    report_archive = "step6-order-report-archive"
    maintenance = "step6-order-maintenance-docs"
    for gate_scripts in (True, False):
        expected = [judgment]
        if gate_scripts:
            expected.append(archive_gate)
        expected += [report_archive, maintenance]
        for path in sources:
            rendered = _render_with_features(
                path, maintenance_docs=True, gate_scripts=gate_scripts
            )
            cm.require_order(
                rendered,
                expected,
                label=f"{path.name} Step⑥順序 (gate_scripts={gate_scripts})",
            )
            if not gate_scripts:
                reference = _render_with_features(
                    path, maintenance_docs=True, gate_scripts=True
                )
                cm.require_absent(
                    rendered,
                    archive_gate,
                    reference=reference,
                    label=f"{path.name} gate_scripts 無効",
                )


def test_completion_labels_keep_maintenance_docs_feature_branches():
    """完了チェック第5項目の表示名を enabled/disabled で分岐する。

    表示名は gate-report.py / archive-gate.sh がレポートの完了チェック行を機械照合する
    契約値であり、文章ではないためマーカー化せず固定文字列で検査する。
    """
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
    cm.require(
        pr_review_disabled,
        "pr-review-review-start-boundary",
        label="05-pr-review (code_review/github_pr 無効)",
    )
    cm.require_tokens_on_line(
        pr_review_disabled,
        "pr-review-delegate-only-after-review-start-exit0",
        ("exit 0",),
        forbidden=("agent-code-review",),
        label="05-pr-review review-start 後の委譲 (code_review 無効)",
    )


def main() -> int:
    tests = [
        test_step4_matrix_implementation_to_verification,
        test_step5_matrix_entry_exit,
        test_step2_matrix_excludes_po_approval_from_exit,
        test_step3_entry_requires_parent_pre_dispatch,
        test_step1_immediately_dispatches_step2_without_ack,
        test_resume_table_contains_pending_and_approved_branches,
        test_step5_procedure_rerun_after_change,
        test_05_pr_review_template_step5_before_pr,
        test_05_pr_review_template_step5_rerun,
        test_commit_policy_normal_procedure_and_disabled_feature_fallback,
        test_review_approval_transition_feature_matrix,
        test_archive_procedure_and_inspection_only_gate,
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
