# agentic-workflow-update — 更新責務

手順、取得元、承認フローは [SKILL.md](SKILL.md) が正本です。本書は、updater と人間のどちらがファイルを更新するかを定めます。

ファイルの所有者は `outputs[].mode` で一つに決まります。

## updater が適用する

- `render`: ファイル全体を再生成結果で置き換えます。人間の直接編集は次回 apply で消えます。変更は seed manifest、templates、root `manifest.yaml`、承認済み `tech_contract` を更新して再生成します。
- `marker`: `marker_id` の管理ブロックだけを upsert します。ブロック外の既存内容は残します。

適用カタログに入るのは `render` と `marker`、および `.cursor/agentic-workflow-update.lock.yaml` です。

## 人間が維持する

`seed` は、ファイルが既にあれば生成が中身を見ずにスキップします。updater の適用カタログには入らず、denylist と合わせてバイト列を保護します。人間が出力ファイルを編集しても、seed manifest とテンプレートは更新されません。

## 誰が更新するか

| 区分 | 例 | 人間 | kit updater |
| --- | --- | --- | --- |
| Domain の seed | `docs/spec.md`、`docs/spec/**`、`docs/architecture.md`、`docs/api.md`、`docs/data-models.md`、`docs/coding-standards.md`、`docs/workflows.md` | 初回生成後の内容を人間が充実させる | 適用しない |
| Meta の追記ログ（seed） | `docs/DECISIONS.md`、`docs/GOTCHAS.md` | エントリの直接追記は設計上の正規経路 | 枠組みもエントリも上書きしない |
| Meta / 生成物（render） | `docs/QUALITY_GATE.md`、`docs/CONTEXT_BUDGET.md`、`docs/AGENT_RUNBOOK.md`、`docs/references/context-budget-internals.md`、`docs/agent-tasks/agent-workflow/**` | 直接編集は drift。次回生成で消える | テンプレートから上書きする |
| Domain 名でも render | `docs/tech-stack.md` | 直接編集しない。`tech_stack` を更新して再生成する | 上書きする |

## 境界

- seed ファイルを削除すると、次の生成でテンプレートの初期骨格が作り直されます。
- `docs/coding-standards.md` は seed です。既存ファイルがあるあいだ、`domain_docs.coding_standards_sections` の変更は updater 経由では入りません。初期内容は承認済み契約の投影です。
- consumer updater の audit は `--skip-seed-required-sections` により、既存 seed の必須見出しを要求しません。kit 自身の `bin/foundation-gate audit` は seed の `required_sections` を検査します。
