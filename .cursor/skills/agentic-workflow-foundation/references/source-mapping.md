# source-mapping — 設計書 → manifest → 出力ファイル のトレーサビリティ

> 統一設計書のどのセクションが manifest のどのキーに対応し、どの出力ファイルに反映されるかを一覧化する。
> 設計書改版時、`check_design_drift.py` が変更を検知したら本表で影響範囲（manifest キー / 出力ファイル）を特定する。
>
> **対象外**: 生成/監査エンジン `manifest-generator`（`generate.py` / `audit.py` / `genlib.py`）は本マッピングに含めない。エンジンは How ツールであり、統一設計書を正本とする生成・drift 追跡の対象ではない（正本はエンジンの工学仕様）。

## 設計書 ID

| ID | パス | 役割 |
| --- | --- | --- |
| `unified` | `.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md` | 5層モデル / 3パターン / Skill・Rule・Subagent・Hook 設計仕様 / semantic 2層命名 / ドキュメントリスト |
| `bas` | `.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` | ACCD 5軸 / Agent Conduct 4原則 / 提案→推奨→承認 / YAML正本+Gate |
| `techstack` | `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` | 技術スタック一覧 / バージョン方針（§9）。他2種と性質が異なり Meta 層へは焼き込まず、Domain 層 `docs/tech-stack.md` の生成元になる |

## マッピング表

| 設計書セクション | manifest キー | 出力ファイル |
| --- | --- | --- |
| unified §12 Layer1「ドキュメント命名規約 semantic 2層」 | `framework.naming` | `AGENTS.md`（Documentation Naming Convention）/ `QUALITY_GATE.md`（G-DOC-NAMING） |
| unified §12 Layer4 / §13.5.2 Hook イベント表 | `framework.hook_events` | `.cursor/hooks.json` / `.cursor/hooks/README.md` |
| unified §13.5.2 / QUALITY_GATE exit code 3段階 | `framework.exit_codes` | `docs/QUALITY_GATE.md` |
| DECISIONS 運用ルール 設計次元 D-\* | `framework.design_dimensions` | `docs/DECISIONS.md` / `.cursor/rules/00-init.mdc` |
| bas ACCD 5軸 | `framework.accd_axes` | `docs/AGENT_RUNBOOK.md §0` |
| bas Agent Conduct 4原則 / Anti-Sycophancy | `framework.agent_conduct` | `.cursor/rules/02-agent-conduct.mdc` |
| unified ADR Context Budget / session-handoff | `framework.budget_thresholds` | `.cursor/hooks/session-budget-evaluator.sh` / `docs/session-handoff-guide.md` / `.cursor/hooks/README.md` |
| unified §3 パターン選択 / §9-11 セットアップ | `project.workflow_pattern` / `project.tracking_artifact` | `AGENTS.md`（Workflow Pattern）/ `docs/AGENT_RUNBOOK.md` |
| unified §12 Layer1 CLAUDE/AGENTS 統合 | `project.name` / `project.one_liner` / `project.tech_stack` | `AGENTS.md` / `CLAUDE.md` |
| unified §13.3 / Boundaries | `project.boundaries` | `AGENTS.md`（Boundaries）/ `.cursor/rules/01-critical-constraints.mdc` |
| unified §9 品質ゲート / 技術スタック別カスタマイズ | `project.quality_gate` | `docs/QUALITY_GATE.md` / `AGENTS.md`（Key Commands） |
| unified §13.5 guard hook（git 不可逆操作） | （framework 固定 / manifest 非依存） | `.cursor/hooks/guard-git-write.sh` |
| unified 原則8 自己改善サイクル | （framework 固定） | `docs/GOTCHAS.md` |
| techstack §9 技術スタック一覧とバージョン方針 | `framework.tech_stack` / `framework.tech_stack_note` | `docs/tech-stack.md`（Domain 層サマリ）/ `AGENTS.md`（Tech Stack はポインタのみ） |

## 改版時の運用

1. `check_design_drift.py` が `design_docs[].sha256` の不一致を検知。
2. 本表で変更セクション → 影響 manifest キー → 影響出力ファイルを特定。
3. `framework.*` の変更なら manifest を更新（Meta 層変更につき PO 承認）。`project.*` のみなら Phase 1.5 の対話（`AskQuestion` + 自由入力）で確定する（PO 直接手入力は廃止）。
4. `generate.py` で再生成 → `audit.py` で準拠検証。
5. drift スクリプトが新しい sha256 を manifest に書き戻す。
