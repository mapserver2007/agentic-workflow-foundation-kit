# source-mapping — unified design → resolved manifest/templates → 出力ファイル のトレーサビリティ

> 本スキルでは `.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md` / `.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` を immutable upstream SoT として読み取り、`.cursor/skills/agentic-workflow-foundation/manifest.yaml` + `templates/` を schema/default として使う。スキル実行時に `scripts/run_resolved_engine.py` が一時 resolved skill-dir を作成し、既存 engine に渡す。
>
> `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` は per-project 入力として Phase 1.6 で生成済み root `manifest.yaml > tech_stack` へ取り込む。`.cursor` 配下に永続的な project manifest は作らない。
>
> Phase 2 / Phase 3 では `scripts/run_resolved_engine.py` が immutable design docs の fingerprint / 構造化要件と、root `manifest.yaml` の `project` / `framework.accd_axes` / `tech_stack` / `session` / `quality_gate_contract` を seed manifest に overlay した一時 resolved skill-dir を作る。resolved skill-dir は engine に渡すための実行時入力であり、永続的な出力ファイルではない。
>
> **対象外**: 生成/監査エンジン `agentic-workflow-engine`（`generate.py` / `audit.py` / `genlib.py`）は本マッピングに含めない。エンジンは How ツールであり、本スキルの生成出力ではない。

## 参照文書の位置づけ

| 文書 | 位置づけ |
| --- | --- |
| `.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md` | immutable upstream SoT。セッション管理、Lost in the Middle、レイヤー構造、Hook 配置の設計入力。 |
| `.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` | immutable upstream SoT。ACCD / Agent Conduct / YAML正本+Gate の設計入力。 |
| `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` | per-project 技術ポリシー源。Phase 1.6 で `tech_stack` へ取り込む任意入力。 |

## マッピング表

| manifest キー | 出力ファイル |
| --- | --- |
| `framework.naming` | `AGENTS.md`（Documentation Naming Convention）/ `docs/QUALITY_GATE.md`（G-DOC-NAMING） |
| `framework.hook_events` | `.cursor/hooks.json` / `.cursor/hooks/README.md` |
| `framework.exit_codes` | `docs/QUALITY_GATE.md` |
| `framework.design_dimensions` | `docs/DECISIONS.md` / `.cursor/rules/00-init.mdc` |
| `framework.accd_axes` | `docs/AGENT_RUNBOOK.md §0`（開発型の軽量実装として seed manifest に固定し、root manifest から overlay） |
| `framework.agent_conduct` | `.cursor/rules/02-agent-conduct.mdc` |
| `framework.budget_thresholds` | `.cursor/hooks/session-budget-evaluator.sh` / `docs/CONTEXT_BUDGET.md` / `.cursor/hooks/README.md` |
| `framework.upstream_design_inputs` | `docs/CONTEXT_BUDGET.md`（生成根拠の説明）/ `references/design-conformance.md`（監査根拠） |
| `framework.handoff` | `docs/CONTEXT_BUDGET.md`（本番運用レベルのユーザー手順 / 状態ファイル / 失敗モード / manifest 必須項目 / 非採用設計(non_goals) / 将来拡張(future_notes) / 参考リンク(references)） |
| `project.workflow_pattern` / `project.tracking_artifact` | `AGENTS.md`（Workflow Pattern）/ `docs/AGENT_RUNBOOK.md` / `.cursor/skills/session-planning/SKILL.md` / `.cursor/skills/session-handover/SKILL.md`。ゲート文脈は `.cursor/skills/session-handover/scripts/session-start-gate.sh`（検査対象）/ `docs/QUALITY_GATE.md`（§1.4 検査ID / §1.5 セッション開始ゲート / §3 フェーズ境界ゲート）で補足 |
| `project.name` / `project.one_liner` | `AGENTS.md` / `CLAUDE.md` |
| `project.boundaries` | `AGENTS.md`（Boundaries）/ `.cursor/rules/01-critical-constraints.mdc` |
| `project.quality_gate` | `docs/QUALITY_GATE.md` / `AGENTS.md`（Key Commands。`bin/quality-gate <subcmd>` 経由で `G-GEN` / `G-BUILD` / `G-LINT` / `G-TEST`）/ `bin/quality-gate`（wrapper 本体。ADR-0001） |
| `quality_gate_contract` | `docs/QUALITY_GATE.md`（package script contract。gen / build / lint / test）/ `AGENTS.md`（Quality Gate Contract） |
| `tech_stack.note` / `tech_stack.items` | `docs/tech-stack.md`（Domain 層サマリ）/ `AGENTS.md`（Tech Stack はポインタのみ）/ `.coderabbit.yaml`（`coderabbit` 経由で tech_stack に従属） |
| `coderabbit.language` / `coderabbit.tools_*` / `coderabbit.path_*` | `.coderabbit.yaml`（CodeRabbit レビュー設定。Phase 1.66 で tech_stack から自動導出） |
| `domain_docs.primary_language` / `domain_docs.framework` / `domain_docs.*_sections` | `docs/spec.md` / `docs/spec/README.md` / `docs/architecture.md` / `docs/api.md` / `docs/data-models.md` / `docs/coding-standards.md` / `docs/workflows.md`（Domain 層スケルトン。Phase 1.67 で tech_stack から自動導出、seed モード） |
| `session.large_task_threshold` | `.cursor/skills/session-planning/SKILL.md` |
| `session.verification.gate_command` | `.cursor/skills/session-handover/SKILL.md` / `.cursor/skills/session-handover/scripts/verification-gate.sh` |
| `framework.security` | `AGENTS.md > Boundaries`（宣言的ルール）/ `.cursor/hooks/guard-git-write.sh`（deterministic deny/ask 強制）/ `.cursor/skills/agent-code-review/references/gh-commands.md`（レビュー用 wrapper コマンドリファレンス）/ `.cursor/skills/agent-github-pr/references/pr-commands.md`（PR 作成用 wrapper コマンドリファレンス） |
| `github_pr` | `.cursor/skills/agent-github-pr/SKILL.md`（PR 作成ワークフロー）/ `.cursor/skills/agent-github-pr/references/pr-commands.md`（`github-pr-create-safe` wrapper 仕様） |
| `deep_thinking` | `.cursor/skills/deep-thinking/SKILL.md`（内部 A/B 並列分析 + C 統合裁定。通常のチャット返答と同じ体裁で応答。一次証跡優先の採用順位、同一モデル時の限定性開示、A/B 未回収時の中止規約、静的保証と実行時制約の境界表を含む）/ `config.yaml`（モデル・実行パラメータの SoT。seed モード。`require_distinct_models` / `max_issues_per_round` / `stop_when` を含む）/ `references/analyst-brief.md`（Ledger スキーマ・`不明` 正規値・ブリーフ欠落報告）/ `references/verification-flags.md`（`MODEL_HOMOGENEOUS` を含む。静的検査との関係を明記）/ `references/issue-card-format.md`（再審三条件・ラウンド配布上限）/ `references/response-synthesis.md`（一次証跡優先 tie-break）/ `validate_deep_thinking.py`（静的契約ゲート G-DEEP-*。audit 統合）/ `docs/QUALITY_GATE.md §4.1`（静的契約ゲートの検査 ID・対象外の実行時特性） |
| `marker_id` | `.gitignore` / `.cursorignore`（認証情報・秘密鍵の除外パターン含む） |

## 変更時の運用

1. immutable upstream docs / stateless resolver / `framework.*` / `outputs[]` / `templates/*` / seed `session.*` の変更は、基盤定義変更として扱う。PO 確定済み事項は再質問せず、未確定事項のみ PO 承認を得る。
2. `project.*` は Phase 1.5 の `init.yaml` → `apply_kit_init.py` で確定する（name / context_budget のみ。workflow_pattern は開発型固定）。`framework.accd_axes` は開発型の軽量実装として seed manifest に固定する。確定値はスキル実行で生成される root `manifest.yaml` に保存する。
3. `tech_stack.*` は Phase 1.6 で techstack 設計書から生成済み root `manifest.yaml` へ取り込み、Phase 1.65 で `G-GEN` を含む `project.quality_gate` / `quality_gate_contract` を自動決定し、Phase 1.66 で `coderabbit`（CodeRabbit 設定）を自動決定し、Phase 1.67 で `domain_docs`（Domain 層ドキュメント変数）を自動決定する。
4. Phase 2 / Phase 3 は `run_resolved_engine.py` 経由で engine を呼び、unified design / root manifest overlay を foundation 側の stateless 前処理に閉じ込める。
5. root `manifest.yaml` と生成ファイルの評価は PO が行う。プラン実装中に勝手に生成物を作らない。
