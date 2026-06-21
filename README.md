# Agentic Workflow Foundation Kit

AI エージェント（Cursor Agent など）を開発プロジェクトに組み込むための基盤ファイル群を、**統一設計書 + seed manifest + templates + project manifest** から決定論的に生成・監査するツールキットです。

このリポジトリは「生成される基盤」そのものではなく、基盤を生成するための **Cursor Skill と Python エンジン一式**です。対象プロジェクトで `agentic-workflow-foundation` を実行すると、`AGENTS.md`、Cursor Rules、Hooks、運用 docs、セッション管理スキル、任意の CodeRabbit / review スキル設定がワークスペース直下に展開されます。

## できること

| 領域 | 生成・管理するもの |
| --- | --- |
| Context / Meta | `AGENTS.md`、`CLAUDE.md`、`docs/AGENT_RUNBOOK.md`、`docs/QUALITY_GATE.md` |
| Constraints | `.cursor/rules/00-init.mdc`、`01-critical-constraints.mdc`、`02-agent-conduct.mdc` |
| Capabilities | `session-planning`、`session-handover`、`decisions-record`、任意の `agent-code-review` |
| Automation | `.cursor/hooks/*.sh`、`.cursor/hooks.json`、Git write guard、Context Budget Hooks |
| Project Docs | `docs/tech-stack.md`、`docs/session-handoff-guide.md`、`docs/DECISIONS.md`、`docs/GOTCHAS.md` |
| Review Integration | 任意の `.coderabbit.yaml` と CodeRabbit path instructions |

`docs/DECISIONS.md` と `docs/GOTCHAS.md` は追記ログなので、存在しない場合だけ初期生成する `seed` モードです。`.gitignore` と `.cursorignore` は既存内容を保持し、`marker_id: agentic-foundation` の管理ブロックだけを更新します。

## 現行アーキテクチャ

```text
immutable upstream SoT
  .cursor/docs/AI_AGENT_UNIFIED_DESIGN.md
  .cursor/docs/AI_BUSINESS_AGENT_SUITE.md
        │
        ▼
agentic-workflow-foundation（What）
  seed manifest + templates + resolver scripts
        │
        ├─ bootstrap: root manifest.yaml を生成 / framework 同期
        ├─ ingest: tech_stack を root manifest.yaml へ取り込み
        ├─ resolve: quality gate / CodeRabbit 設定を導出
        ▼
run_resolved_engine.py
  seed + upstream metadata + root manifest overlay から
  一時 resolved skill-dir を作成
        │
        ▼
agentic-workflow-engine（How）
  generate.py / audit.py / genlib.py
        │
        ▼
対象プロジェクトの基盤ファイル群
```

中核は **What / How の分離**です。

`agentic-workflow-foundation` は、どのファイルをどの内容で出すかを持つ設定スキルです。統一設計書、seed `manifest.yaml`、`templates/`、project manifest の重ね合わせ、tech stack 取り込み、quality gate / CodeRabbit 解決を担当します。

`agentic-workflow-engine` は、解決済みの `manifest.yaml + templates/` だけを受け取る生成・監査エンジンです。統一設計書や root `manifest.yaml` を直接読まず、`render` / `seed` / `marker` モードでファイルをバイト一致再現します。

## リポジトリ構成

```text
agentic-workflow-foundation-kit/
├── README.md
├── LICENSE
└── .cursor/
    ├── docs/
    │   ├── AI_AGENT_UNIFIED_DESIGN.md        # immutable upstream SoT（非公開・gitignore）
    │   ├── AI_BUSINESS_AGENT_SUITE.md        # immutable upstream SoT（非公開・gitignore）
    │   └── TECHNOLOGY_STACK_UNIFIED_DESIGN.md # project ごとの tech stack 入力
    └── skills/
        ├── agentic-workflow-foundation/
        │   ├── SKILL.md
        │   ├── manifest.yaml
        │   ├── templates/
        │   ├── references/
        │   └── scripts/
        │       ├── run_resolved_engine.py
        │       ├── ingest_tech_stack.py
        │       ├── resolve_quality_gate.py
        │       ├── resolve_coderabbit.py
        │       └── check_tech_stack_conformance.py
        └── agentic-workflow-engine/
            ├── SKILL.md
            └── scripts/
                ├── genlib.py
                ├── generate.py
                └── audit.py
```

## 主要スキル

| スキル | 役割 |
| --- | --- |
| [`agentic-workflow-foundation`](.cursor/skills/agentic-workflow-foundation/SKILL.md) | 基盤の設定スキル。root `manifest.yaml` の生成、tech stack 取り込み、quality gate / CodeRabbit 解決、一時 resolved skill-dir 作成、生成・監査の orchestration を担う |
| [`agentic-workflow-engine`](.cursor/skills/agentic-workflow-engine/SKILL.md) | 生成・監査エンジン。設定スキルから渡された `manifest.yaml + templates/` を決定論的に変換する |

## 生成ワークフロー

Cursor では対象プロジェクトで「Agentic 基盤を生成して」「基盤ファイルを更新して」「techstack を取り込んで再生成して」などと依頼すると、`agentic-workflow-foundation` が次の流れを実行します。

1. **Phase 1**: seed manifest / templates / resolver を変更する必要がある場合だけ更新する
2. **Phase 1.45**: `run_resolved_engine.py bootstrap` で root `manifest.yaml` を作成、または `framework:` ブロックを seed から同期する
3. **Phase 1.5**: `project.*`、`workflow_pattern`、CodeRabbit / review / GitHub PR / GitHub Issue スキル生成有無を確定する
4. **Phase 1.6**: `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` から `tech_stack` を root `manifest.yaml` へ取り込む
5. **Phase 1.65**: `tech_stack` から `G-GEN`、`G-BUILD`、`G-LINT`、`G-TEST` と package script contract を導出する
6. **Phase 1.66**: CodeRabbit が有効な場合、tools / path filters / path instructions を解決する
7. **Phase 1.7**: tech stack policy と実リポジトリの整合をチェックする
8. **Phase 2**: 一時 resolved skill-dir から基盤ファイル群を生成する
9. **Phase 3**: 冪等性と required sections を監査する
10. **Phase 4**: 確定値、生成物、ゲート結果を報告する

## 手動実行

通常は Cursor Skill 経由で実行します。手動で確認する場合は、foundation 専用ラッパーを入口にします。

```bash
# root manifest.yaml を seed から作成 / framework ブロックを同期
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py bootstrap

# tech stack を root manifest.yaml > tech_stack へ取り込み
python3 .cursor/skills/agentic-workflow-foundation/scripts/ingest_tech_stack.py

# quality gate / package script contract を tech_stack から導出
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_quality_gate.py

# CodeRabbit 設定を tech_stack から導出（coderabbit.enabled: true の場合）
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_coderabbit.py

# tech stack policy と実リポジトリの整合確認
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_tech_stack_conformance.py

# 生成
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py generate

# 冪等性ドライラン
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py check

# 監査
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py audit
```

`agentic-workflow-engine/scripts/generate.py` と `audit.py` を直接呼ぶのは、エンジン単体の検証時だけです。通常の foundation 生成では `run_resolved_engine.py` が upstream metadata と root manifest overlay を解決してから engine を呼びます。

## 生成物

現行 seed manifest の `outputs[]` は次を管理します。

| 種別 | ファイル |
| --- | --- |
| Context | `AGENTS.md`、`CLAUDE.md` |
| Cursor Rules | `.cursor/rules/00-init.mdc`、`01-critical-constraints.mdc`、`02-agent-conduct.mdc` |
| Hooks | `.cursor/hooks/guard-git-write.sh`、`session-bootstrap.sh`、`session-budget-tracker.sh`、`session-shell-tracker.sh`、`session-budget-evaluator.sh`、`.cursor/hooks/README.md`、`.cursor/hooks.json` |
| Docs | `docs/AGENT_RUNBOOK.md`、`docs/QUALITY_GATE.md`、`docs/session-handoff-guide.md`、`docs/tech-stack.md`、`docs/DECISIONS.md`、`docs/GOTCHAS.md` |
| Session Skills | `.cursor/skills/session-planning/SKILL.md`、`.cursor/skills/session-handover/SKILL.md`、`verification-gate.sh`、`session-start-gate.sh`、`plan-gate.sh`、`.cursor/skills/decisions-record/SKILL.md` |
| Optional Review | `.cursor/skills/agent-code-review/**`、`.coderabbit.yaml` |
| Ignore Blocks | `.gitignore`、`.cursorignore` |

`.cursor/skills/agent-code-review/**` は `code_review.enabled: true` の場合のみ、`.coderabbit.yaml` は `coderabbit.enabled: true` の場合のみ生成されます。

## 5層モデル

このキットは AI エージェント運用を 5 層で整理します。

| Layer | 役割 | 本キットでの表現 |
| --- | --- | --- |
| 1. Context | 目的・判断基準・運用入口 | `AGENTS.md`、`CLAUDE.md`、`docs/*` |
| 2. Constraints | 常時適用される制約 | `.cursor/rules/*.mdc` |
| 3. Capabilities | 必要時に呼び出す専門手順 | `session-planning`、`session-handover`、`decisions-record`、`agent-code-review` |
| 4. Automation | ツール実行前後・セッション境界の自動処理 | `.cursor/hooks/*`、`.cursor/hooks.json` |
| 5. Delegation | 子エージェントへの委譲 | 本キットでは生成しない。Cursor 組み込み Subagent を利用する |

Meta 層 / Domain 層はドキュメント命名上の 2 層モデルです。Layer 1〜5 は運用アーキテクチャ上の分類で、別軸として扱います。

## 設計原則

### 生成物を直接編集しない

`AGENTS.md`、Rules、Hooks、生成 docs、生成スキルは出力です。変更は upstream docs、seed `manifest.yaml`、`templates/`、resolver scripts、または root `manifest.yaml` の project 値を更新して再生成します。直接編集は `audit` が drift として検出します。

### root manifest の責務を分ける

root `manifest.yaml` は対象プロジェクトの正式 project manifest です。ただし `framework:` ブロックの SoT は seed manifest で、root 側は同期された複製です。手編集してよいのは、Phase 1.5 / 1.6 / 1.65 / 1.66 が扱う `project`、`tech_stack`、`session`、`quality_gate_contract`、`code_review`、`github_pr`、`github_issue`、`coderabbit` などの per-project 値です。

### upstream docs は immutable input

`AI_AGENT_UNIFIED_DESIGN.md` と `AI_BUSINESS_AGENT_SUITE.md` は読み取り専用の upstream SoT です。`run_resolved_engine.py` が存在有無と fingerprint を resolved manifest に反映しますが、スキル実行で書き換えません。

### tech stack は project input

`TECHNOLOGY_STACK_UNIFIED_DESIGN.md` はプロジェクトごとに変わる入力です。`ingest_tech_stack.py` が root `manifest.yaml > tech_stack` へ取り込み、`docs/tech-stack.md`、quality gate、CodeRabbit 設定の元データになります。

### Context Budget は Hook で観測する

生成される Hooks は、危険な Git 操作のガードと長時間セッションの引き継ぎ促進を担います。`elapsed_min`、`prompt_count`、`shell_bytes` を proxy 指標として Yellow / Red を判定し、必要に応じて handoff manifest を使った新規チャット移行を促します。

## 前提条件

- Python 3（標準ライブラリのみ。PyYAML 不要）
- `jq`（Hook 実行時を推奨。未インストール時は fail-open）
- 必要に応じて `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md`
- Optional: CodeRabbit / GitHub review 運用を使う場合は、対象プロジェクト側の GitHub / CodeRabbit 設定

外部サービス・Cursor 設定を含む詳細なセットアップ手順は **[SETUP.md](SETUP.md)** を参照。

## このリポジトリと生成先

本リポジトリはジェネレータ・ツールキット本体です。対象プロジェクトにこのキットの `.cursor/skills/agentic-workflow-foundation` と `.cursor/skills/agentic-workflow-engine` を配置し、Cursor から `agentic-workflow-foundation` を起動すると、対象プロジェクトのルートに基盤ファイル群が生成されます。

詳細な運用手順は [`agentic-workflow-foundation/SKILL.md`](.cursor/skills/agentic-workflow-foundation/SKILL.md)、エンジン仕様は [`agentic-workflow-engine/SKILL.md`](.cursor/skills/agentic-workflow-engine/SKILL.md) を参照してください。

## ライセンス

[Apache License 2.0](LICENSE)
