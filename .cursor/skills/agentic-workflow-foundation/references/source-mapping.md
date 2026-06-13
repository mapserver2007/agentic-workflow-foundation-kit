# source-mapping — seed manifest → root manifest / 出力ファイル のトレーサビリティ

> 本スキルでは `.cursor/skills/agentic-workflow-foundation/manifest.yaml` + `templates/` が root manifest 生成前の seed SoT。スキル実行によりリポジトリ直下 `manifest.yaml` が正式な per-project manifest として生成される。unified / bas の思想は本スキルに内部化済みであり、実行時に fingerprint drift 追跡は行わない。
>
> `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` は per-project 入力として Phase 1.6 で生成済み root `manifest.yaml > tech_stack` へ取り込む。`.cursor` 配下に永続的な project manifest は作らない。
>
> Phase 2 / Phase 3 では `scripts/run_resolved_engine.py` が seed manifest に root `manifest.yaml` の `project` / `framework.accd_axes` / `tech_stack` / `session` / `quality_gate_contract` を overlay した一時 resolved skill-dir を作る。resolved skill-dir は engine に渡すための実行時入力であり、永続的な出力ファイルではない。
>
> **対象外**: 生成/監査エンジン `agentic-workflow-engine`（`generate.py` / `audit.py` / `genlib.py`）は本マッピングに含めない。エンジンは How ツールであり、本スキルの生成出力ではない。

## 参照文書の位置づけ

| 文書 | 位置づけ |
| --- | --- |
| `.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md` | 歴史的設計根拠。思想は `framework.*` / templates へ内部化済み。実行時入力ではない。 |
| `.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` | 歴史的設計根拠。ACCD / Agent Conduct / YAML正本+Gate は内部化済み。実行時入力ではない。 |
| `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` | per-project 技術ポリシー源。Phase 1.6 で `tech_stack` へ取り込む任意入力。 |

## マッピング表

| manifest キー | 出力ファイル |
| --- | --- |
| `framework.naming` | `AGENTS.md`（Documentation Naming Convention）/ `docs/QUALITY_GATE.md`（G-DOC-NAMING） |
| `framework.hook_events` | `.cursor/hooks.json` / `.cursor/hooks/README.md` |
| `framework.exit_codes` | `docs/QUALITY_GATE.md` |
| `framework.design_dimensions` | `docs/DECISIONS.md` / `.cursor/rules/00-init.mdc` / `.cursor/skills/decisions-record/SKILL.md` |
| `framework.accd_axes` | `docs/AGENT_RUNBOOK.md §0`（Phase 1.5 で軽量実装を自動確定し、root manifest から overlay） |
| `framework.agent_conduct` | `.cursor/rules/02-agent-conduct.mdc` |
| `framework.budget_thresholds` | `.cursor/hooks/session-budget-evaluator.sh` / `docs/session-handoff-guide.md` / `.cursor/hooks/README.md` |
| `project.workflow_pattern` / `project.tracking_artifact` | `AGENTS.md`（Workflow Pattern）/ `docs/AGENT_RUNBOOK.md` / `.cursor/skills/session-planning/SKILL.md` / `.cursor/skills/session-handover/SKILL.md` |
| `project.name` / `project.one_liner` | `AGENTS.md` / `CLAUDE.md` |
| `project.boundaries` | `AGENTS.md`（Boundaries）/ `.cursor/rules/01-critical-constraints.mdc` |
| `project.quality_gate` | `docs/QUALITY_GATE.md` / `AGENTS.md`（Key Commands） |
| `quality_gate_contract` | `docs/QUALITY_GATE.md`（package script contract）/ `AGENTS.md`（Quality Gate Contract） |
| `tech_stack.note` / `tech_stack.items` | `docs/tech-stack.md`（Domain 層サマリ）/ `AGENTS.md`（Tech Stack はポインタのみ） |
| `session.large_task_threshold` | `.cursor/skills/session-planning/SKILL.md` |
| `session.verification.gate_command` | `.cursor/skills/session-handover/SKILL.md` / `.cursor/skills/session-handover/scripts/verification-gate.sh` |
| `marker_id` | `.gitignore` / `.cursorignore` |

## 変更時の運用

1. `framework.*` / `outputs[]` / `templates/*` / seed `session.*` の変更は、seed SoT 変更として PO 承認を得る。
2. `project.*` は Phase 1.5 の対話（AskQuestion / 自動導出 / 固定値）で確定し、`framework.accd_axes` は開発型 / パイプライン型 / ドキュメント型では軽量実装として自動導出する。確定値はスキル実行で生成される root `manifest.yaml` に保存する。
3. `tech_stack.*` は Phase 1.6 で techstack 設計書から生成済み root `manifest.yaml` へ取り込み、Phase 1.65 で `project.quality_gate` / `quality_gate_contract` を自動決定する。
4. Phase 2 / Phase 3 は `run_resolved_engine.py` 経由で engine を呼び、root manifest overlay を foundation 側の前処理に閉じ込める。
5. root `manifest.yaml` と生成ファイルの評価は PO が行う。プラン実装中に勝手に生成物を作らない。
