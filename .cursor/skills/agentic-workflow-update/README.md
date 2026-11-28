# agentic-workflow-update — 更新責務

手順、取得元、承認フローは [SKILL.md](SKILL.md) が正本です。本書は、updater と人間のどちらがファイルを更新するかを定めます。

ファイルの所有者は `outputs[].mode` で一つに決まります。

## updater が適用する

- `render`: ファイル全体を再生成結果で置き換えます。人間の直接編集は次回 apply で消えます。変更は seed manifest、templates、root `manifest.yaml`、承認済み `tech_contract` を更新して再生成します。
- `marker`: `marker_id` の管理ブロックだけを upsert します。ブロック外の既存内容は残します。

適用カタログ（lock に記録するもの）に入るのは `render` と `marker`、および `.cursor/agentic-workflow-update.lock.yaml` です。

次の2つは lock に記録せず、updater がミラーで適用します。

- **kit 本体**: kit の clone と対象アプリを直接比較し、上書きと、clone に無いファイルの削除を行います。対象は `.cursor/skills/agentic-workflow-foundation/`、`.cursor/skills/agentic-workflow-engine/`、`.cursor/skills/technology-stack-unified-design/`、`.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md`、`.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` です。`__pycache__` と `*.pyc` は比較しません。
- **`mode: split` の出力**: 対象アプリ自身のブループリントから生成した結果（plan の一時作業ツリー）と比較し、追加・更新・削除を行います。kit の clone とは比較しません。

`agentic-workflow-update` 自身は、ホスト個人スキルとして配置する前提なので、対象アプリへ同期も削除もしません。対象アプリに既にあるときは、plan の `warnings` に出すだけです。

kit 本体と split の削除は、plan に表示し、`retirement=delete` の承認があるときだけ実行します。`keep` はミラーが収束しないため使えません。

適用後は、対象アプリ内の foundation で `run_resolved_engine.py check` を実行し、再生成差分がゼロであることを確認します（`generate` は実行しません）。

## 人間が維持する

`seed` は、ファイルが既にあれば生成が中身を見ずにスキップします。updater の適用カタログには入らず、denylist と合わせてバイト列を保護します。人間が出力ファイルを編集しても、seed manifest とテンプレートは更新されません。

## 誰が更新するか

| 区分 | 例 | 人間 | kit updater |
| --- | --- | --- | --- |
| Domain の seed | `docs/spec.md`、`docs/spec/**`、`docs/architecture.md`、`docs/api.md`、`docs/data-models.md`、`docs/coding-standards.md`、`docs/workflows.md` | 初回生成後の内容を人間が充実させる | 適用しない |
| Meta の追記ログ（seed） | `docs/DECISIONS.md`、`docs/GOTCHAS.md` | エントリの直接追記は設計上の正規経路 | 枠組みもエントリも上書きしない |
| スキル設定（seed） | `campaign-cleanup` / `workflow-orchestrator` / `deep-thinking` / `requirement-analysis` / `agent-kaizen` の `config.yaml`、`cross-repository-knowledge-link/config.json` | 初回生成後のモデルや閾値を人間が編集する | 適用しない。denylist でバイト列を保護する |
| キュー（seed / denylist） | `docs/agent-tasks/reports/**`、`docs/agent-tasks/reviews/**`、`docs/agent-tasks/maintenance-docs/.gitkeep` | キャンペーン成果物と起票を人間が維持する | `reports/**` と `reviews/**` は denylist。`maintenance-docs/.gitkeep` は seed で、既存なら適用しない |
| Meta / 生成物（render） | `docs/QUALITY_GATE.md`、`docs/CONTEXT_BUDGET.md`、`docs/AGENT_RUNBOOK.md`、`docs/references/context-budget-internals.md`、`docs/agent-tasks/agent-workflow/**`、`.cursor/skills/domain-docs/SKILL.md`、`.cursor/skills/campaign-cleanup/SKILL.md`、`bin/quality-gate`、`bin/foundation-gate`、`bin/project-setup`、`.cursor/hooks/session-progress-emitter.sh` | 直接編集は drift。次回生成で消える | テンプレートから上書きする |
| Domain 名でも split | `docs/tech-stack.md`、`docs/tech-stack/` | 直接編集しない。ブループリントの正本（`.cursor/docs/<設計書名>`）を更新して、updater の plan → apply で反映する | 対象アプリのブループリントから生成した結果と比較して、追加・更新・削除する。以前の `render` として lock に残る `docs/tech-stack.md` は、所有が split へ移っただけなので orphan にしない |
| kit 本体 | `.cursor/skills/agentic-workflow-foundation/**`、`.cursor/skills/agentic-workflow-engine/**`、`.cursor/skills/technology-stack-unified-design/**`、`.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md`、`.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` | 直接編集しない（次回の更新で上書き・削除される） | kit の clone と直接比較してミラーする。削除は `retirement=delete` のときだけ |
| updater 自身 | `.cursor/skills/agentic-workflow-update/**` | 対象アプリには置かない（ホスト個人スキル） | 同期も削除もしない。対象アプリにあれば `warnings` に出す |

## 境界

- seed ファイルを削除すると、次の生成でテンプレートの初期骨格が作り直されます。
- `docs/coding-standards.md` は seed です。既存ファイルがあるあいだ、`domain_docs.coding_standards_sections` の変更は updater 経由では入りません。初期内容は承認済み契約の投影です。
- `docs/spec/**`、`docs/agent-tasks/reports/**`、`docs/agent-tasks/reviews/**` は denylist です。`reviews/.gitkeep` は `code_review.enabled: true` のときだけ seed で作られます。`maintenance-docs/.gitkeep` と `maintenance-docs/archives/.gitkeep` は `agent_workflow.maintenance_docs.enabled: true` のとき seed です。
- `.cursor/skills/domain-docs/SKILL.md` と `.cursor/skills/campaign-cleanup/SKILL.md`、`campaign-cleanup.sh` は render です。`campaign-cleanup/config.yaml` は seed かつ denylist です。
- `bin/quality-gate` は常時の render です。`bin/foundation-gate` と `bin/project-setup` は `foundation.enabled: true` のときだけ render されます。
- `foundation.enabled` は変更しません（`manifest.yaml` は保護対象）。このフラグは `bin/foundation-gate` と `bin/project-setup` の生成、および `bin/quality-gate` の contract 検査分岐だけを制御します。kit 本体が対象アプリにあっても、`foundation.enabled: false` の `bin/quality-gate` の挙動は変わりません。
- root `manifest.yaml` の `framework:` の同期（bootstrap）は updater の対象外です。root に `framework.accd_axes` を持つ場合、root の値が seed の値より優先されます。
- consumer updater の audit は `--skip-seed-required-sections` により、既存 seed の必須見出しを要求しません。kit 自身の `bin/foundation-gate audit` は seed の `required_sections` を検査します。
