# source-mapping — 設計書 → manifest/テンプレート → 出力スキル のトレーサビリティ

> 統一設計書のどのセクションが本スキルの manifest キー / テンプレートに対応し、どの出力スキルに反映されるかを一覧化する。
> 親 `agentic-workflow-foundation/references/source-mapping.md` の Layer 3（セッション管理）担当部分を本スキルが引き継ぐ。
>
> **対象外**: 生成/監査エンジン `deterministic-generator`（`generate.py` / `audit.py` / `genlib.py`）は本マッピングに含めない（How ツールであり設計符号化生成の対象外）。

## 設計書 ID（本スキルに寄与する2種）

| ID | パス | 本スキルへの寄与 |
| --- | --- | --- |
| `unified` | `.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md` | §1-2 セッション管理と3構成要素 / §5 5層モデル Layer 3 / §6 追跡ドキュメントのライフサイクル / §8 パターン選択フロー / §9-11 パターン別検証スクリプト / §12 Layer 3 skill 仕様 / §13.2 Skill 設計仕様 / Appendix B decisions_record |
| `bas` | `.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` | 提案→推奨→承認（Phase 1.5 対話）/ Agent Conduct（各スキルの Gotchas・即時外部化） |

> `techstack` は Meta 層へ焼き込まず `docs/tech-stack.md` のみを駆動するため、本スキルには寄与しない。

## マッピング表

| 設計書セクション | manifest キー / テンプレート | 出力スキル |
| --- | --- | --- |
| unified §2 3構成要素（追跡ドキュメント / 検証ゲート / 再開プロトコル） | 3テンプレートの責務分担 | session-planning / session-handover / decisions-record |
| unified §5 Layer 3 Capabilities / §13.2 Skill 仕様（description の What/When/Negative・Gotchas・Progressive Disclosure） | 各 `SKILL.md.template` の frontmatter / 本文体裁 | 全出力スキル |
| unified §6 追跡ドキュメントのライフサイクル（Active/Complete/Archive） | `session-handover` テンプレ「アーカイブ提案」 | session-handover |
| unified §8 パターン選択フロー（4問） | `session-planning` テンプレ「パターン選択フロー」 | session-planning |
| unified §9-11 パターン別セットアップ / 検証スクリプト | `session.verification.gate_command` / `verification-gate.sh.template` | session-handover/scripts/verification-gate.sh |
| unified §12 session_planning 閾値（変更5件 / サブタスク3つ） | `session.large_task_threshold.{files,subtasks}` | session-planning |
| unified 設計原則1（単一ファイル）/ 4（即時外部化）/ 5（リンク衛生） | 各テンプレ本文 | session-planning / session-handover |
| unified Appendix B decisions_record（ADR 自動化）/ 設計次元 D-* | `decisions-record` テンプレ「設計判断の検知」「ADR フォーマット」 | decisions-record |
| 親 `agentic-workflow-foundation/project.*`（workflow_pattern / tracking_artifact / name） | `inherits_project`（継承） | 全出力スキル（`{{ project.* }}` で参照） |

## 改版時の運用

1. 親 `agentic-workflow-foundation/scripts/check_design_drift.py` が `unified` / `bas` の改版を検知する（fingerprint は親 manifest が保持。本スキルは fingerprint を持たない）。
2. 改版が Layer 3（セッション管理）に及ぶ場合、本表で影響テンプレート / manifest キーを特定する。
3. テンプレート / `session.*` を更新し、`deterministic-generator/generate.py` で再生成 → `audit.py` で検証。
4. `project.*` の変更は親側の Phase 1.5 対話で確定する（本スキルは継承するのみ）。
