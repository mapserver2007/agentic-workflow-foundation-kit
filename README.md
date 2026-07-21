# Agentic Workflow Foundation Kit

AI エージェント（Cursor Agent など）を開発プロジェクトに組み込むための基盤ファイル群を、**統一設計書 + seed manifest + templates + project manifest** から決定論的に生成・監査するツールキットです。

このリポジトリは「生成される基盤」そのものではなく、基盤を生成するための **Cursor Skill と Python エンジン一式**です。対象プロジェクトで `agentic-workflow-foundation` を実行すると、`AGENTS.md`、Cursor Rules、Hooks、運用 docs、Domain 層ドキュメント、セッション管理スキル、GitHub 連携スキル、多角評価スキル、wrapper スクリプト、任意の CodeRabbit / review スキル設定がワークスペース直下に展開されます。

**本リポジトリは dogfooding 構成**です。キット本体（`.cursor/skills/agentic-workflow-foundation` / `agentic-workflow-engine`）に加え、ルート直下に `manifest.yaml` と生成物（`AGENTS.md`、`docs/`、`bin/` 等）が同居しています。生成物の変更は manifest / templates 経由の再生成が正規ルートです。

## できること

| 領域 | 生成・管理するもの |
| --- | --- |
| Context / Meta | `AGENTS.md`、`CLAUDE.md`、`docs/AGENT_RUNBOOK.md`、`docs/QUALITY_GATE.md` |
| Constraints | `.cursor/rules/00-init.mdc`、`01-critical-constraints.mdc`、`02-agent-conduct.mdc` |
| Capabilities | `session-planning`、`session-handover`、`decisions-record`、任意の `workflow-orchestrator`、`requirement-analysis`、`maintenance-docs-workflow`、`maintenance-gotchas-workflow`、`agent-code-review`、`agent-github-pr`、`agent-github-issue`、`cross-repository-knowledge-link`、`deep-thinking`、`agent-kaizen` |
| Automation | `.cursor/hooks/*.sh`、`.cursor/hooks.json`、Git write guard、Context Budget Hooks（compact 観測・会話ログ含む）、workflow / artifact / archive ゲート |
| Project Docs (Meta) | `docs/AGENT_RUNBOOK.md`、`docs/QUALITY_GATE.md`、`docs/CONTEXT_BUDGET.md`、`docs/references/context-budget-internals.md`、`docs/DECISIONS.md`、`docs/GOTCHAS.md` |
| Project Docs (Domain) | `docs/spec.md`、`docs/spec/`、`docs/architecture.md`、`docs/api.md`、`docs/data-models.md`、`docs/coding-standards.md`、`docs/workflows.md` |
| Tech Stack | `docs/tech-stack.md`（Domain 層）、quality gate contract、CodeRabbit / Domain docs の自動解決 |
| Agent Workflow | 任意の `docs/agent-tasks/agent-workflow/**`（6 段階：①〜⑥）、`docs/agent-tasks/{reports,maintenance-docs}/`、`workflow-orchestrator`、`requirement-analysis`、`maintenance-docs-workflow`、`maintenance-gotchas-workflow` |
| Multi-perspective | 任意の `.cursor/skills/deep-thinking/**`（A/B 並列分析 + C 統合裁定） |
| GitHub Wrappers | `bin/_github-app-auth.sh`、`bin/github-pr-create-safe`、任意の `bin/github-pr-{reviews,comment,reply}-safe`、`bin/github-issue-{create,read}-safe` |
| Cross-Repo | 任意の `.cursor/skills/cross-repository-knowledge-link/**`、`bin/cross-repo-sync-safe` |
| Review Integration | 任意の `.coderabbit.yaml` と CodeRabbit path instructions |

`docs/DECISIONS.md`、`docs/GOTCHAS.md` および Domain 層ドキュメント群（`docs/spec.md` 等）は追記ログまたは PO 充実用のため、存在しない場合だけ初期生成する `seed` モードです。`.gitignore` と `.cursorignore` は既存内容を保持し、`marker_id: agentic-foundation` の管理ブロックだけを更新します。

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
        ├─ resolve: budget thresholds / quality gate / CodeRabbit / domain docs 設定を導出
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

`agentic-workflow-foundation` は、どのファイルをどの内容で出すかを持つ設定スキルです。統一設計書、seed `manifest.yaml`、`templates/`、project manifest の重ね合わせ、tech stack 取り込み、budget thresholds / quality gate / CodeRabbit / domain docs 解決を担当します。

`agentic-workflow-engine` は、解決済みの `manifest.yaml + templates/` だけを受け取る生成・監査エンジンです。統一設計書や root `manifest.yaml` を直接読まず、`render` / `seed` / `marker` モードでファイルをバイト一致再現します。

## リポジトリ構成

```text
agentic-workflow-foundation-kit/
├── README.md                          # 本ファイル（手管理）
├── setup.md                           # 外部サービス・Cursor 設定手順
├── LICENSE
├── Makefile                           # CLI 依存の install / check
├── manifest.yaml                      # 正式 project manifest（スキル実行で生成）
│
├── AGENTS.md                          ┐
├── CLAUDE.md                          │
├── .coderabbit.yaml                   │
├── bin/                               │ 生成物（dogfooding）
│   ├── _github-app-auth.sh            │
│   ├── github-pr-*-safe               │
│   ├── github-issue-*-safe            │
│   └── cross-repo-sync-safe           │
├── docs/                              │
│   ├── AGENT_RUNBOOK.md               │
│   ├── QUALITY_GATE.md                │
│   ├── CONTEXT_BUDGET.md              │
│   ├── references/                    │
│   ├── tech-stack.md                  │
│   ├── DECISIONS.md / GOTCHAS.md      │
│   ├── spec.md / spec/                │
│   ├── architecture.md / api.md / …   │
│   └── agent-tasks/                   ┘
│
└── .cursor/
    ├── docs/
    │   ├── AI_AGENT_UNIFIED_DESIGN.md        # immutable upstream SoT（非公開・gitignore）
    │   ├── AI_BUSINESS_AGENT_SUITE.md        # immutable upstream SoT（非公開・gitignore）
    │   └── TECHNOLOGY_STACK_UNIFIED_DESIGN.md # project ごとの tech stack 入力
    ├── hooks/                                # 生成 Hook スクリプト
    ├── hooks.json
    ├── rules/                                # 生成 Cursor Rules
    └── skills/
        ├── agentic-workflow-foundation/      # ── キット本体（What）──
        │   ├── SKILL.md
        │   ├── manifest.yaml                 # seed manifest
        │   ├── templates/
        │   │   ├── AGENTS.md.template
        │   │   ├── CLAUDE.md.template
        │   │   ├── coderabbit.yaml.template
        │   │   ├── hooks.json.template
        │   │   ├── gitignore.block.template
        │   │   ├── cursorignore.block.template
        │   │   ├── rules/                    # 00-init 〜 02-agent-conduct
        │   │   ├── hooks/                    # guard-git-write, session-*,
        │   │   │                             # budget-*, compact-observer, response-tracker
        │   │   ├── docs/                     # AGENT_RUNBOOK, QUALITY_GATE, tech-stack,
        │   │   │                             # CONTEXT_BUDGET, references/, DECISIONS, GOTCHAS,
        │   │   │                             # spec, spec/README, architecture, api,
        │   │   │                             # data-models, coding-standards, workflows,
        │   │   │                             # agent-tasks/**
        │   │   ├── skills/                   # session-planning, session-handover,
        │   │   │                             # decisions-record, agent-code-review,
        │   │   │                             # agent-github-pr, agent-github-issue,
        │   │   │                             # workflow-orchestrator, requirement-analysis,
        │   │   │                             # maintenance-*-workflow, cross-repository-
        │   │   │                             # knowledge-link, deep-thinking, agent-kaizen
        │   │   └── bin/                      # _github-app-auth.sh, github-*-safe,
        │   │                                 # cross-repo-sync-safe
        │   ├── references/
        │   │   ├── source-mapping.md
        │   │   └── design-conformance.md
        │   └── scripts/
        │       ├── run_resolved_engine.py
        │       ├── ingest_tech_stack.py
        │       ├── resolve_budget_thresholds.py
        │       ├── resolve_quality_gate.py
        │       ├── resolve_coderabbit.py
        │       ├── resolve_domain_docs.py
        │       ├── check_tech_stack_conformance.py
        │       ├── validate_deep_thinking.py
        │       ├── validate_requirement_analysis.py
        │       └── test_*.py
        ├── agentic-workflow-engine/          # ── キット本体（How）──
        │   ├── SKILL.md
        │   └── scripts/
        │       ├── genlib.py
        │       ├── generate.py
        │       └── audit.py
        │
        └── （生成スキル）                     # session-planning, session-handover,
                                               # decisions-record, workflow-orchestrator,
                                               # requirement-analysis, maintenance-*-workflow,
                                               # agent-code-review, agent-github-pr,
                                               # agent-github-issue, cross-repository-
                                               # knowledge-link, deep-thinking, agent-kaizen
```

## 主要スキル

| スキル | 役割 |
| --- | --- |
| [`agentic-workflow-foundation`](.cursor/skills/agentic-workflow-foundation/SKILL.md) | 基盤の設定スキル。root `manifest.yaml` の生成、tech stack 取り込み、budget thresholds / quality gate / CodeRabbit 解決、一時 resolved skill-dir 作成、生成・監査の orchestration を担う |
| [`agentic-workflow-engine`](.cursor/skills/agentic-workflow-engine/SKILL.md) | 生成・監査エンジン。設定スキルから渡された `manifest.yaml + templates/` を決定論的に変換する |

生成先プロジェクトで利用可能になるスキル（本リポジトリでは dogfooding 済み）:

| スキル | 役割 |
| --- | --- |
| [`session-planning`](.cursor/skills/session-planning/SKILL.md) | 追跡ドキュメント（`.cursor/.tracking/tracker-{session_id}.md`）の作成・更新 |
| [`session-handover`](.cursor/skills/session-handover/SKILL.md) | セッション開始/終了、handoff、検証・artifact・archive ゲート |
| [`decisions-record`](.cursor/skills/decisions-record/SKILL.md) | 設計判断記録（`docs/DECISIONS.md`）の起票 |
| [`workflow-orchestrator`](.cursor/skills/workflow-orchestrator/SKILL.md) | 6 段階標準タスク実行ワークフロー（①〜⑥）の制御 |
| [`requirement-analysis`](.cursor/skills/requirement-analysis/SKILL.md) | Step ①の要求正規化、3段階ガード、分析深度判定 |
| [`maintenance-docs-workflow`](.cursor/skills/maintenance-docs-workflow/SKILL.md) | 起票キューから Domain 層 docs を反映する独立パイプライン |
| [`maintenance-gotchas-workflow`](.cursor/skills/maintenance-gotchas-workflow/SKILL.md) | GOTCHAS の再発防止策を Meta 層へ反映する独立パイプライン |
| [`agent-code-review`](.cursor/skills/agent-code-review/SKILL.md) | PR レビューコメントの検証・返答 |
| [`agent-github-pr`](.cursor/skills/agent-github-pr/SKILL.md) | GitHub App wrapper 経由の PR 作成 |
| [`agent-github-issue`](.cursor/skills/agent-github-issue/SKILL.md) | GitHub App wrapper 経由の Issue 作成・読み取り |
| [`cross-repository-knowledge-link`](.cursor/skills/cross-repository-knowledge-link/SKILL.md) | 登録済み関連リポジトリの docs / コード参照 |
| [`deep-thinking`](.cursor/skills/deep-thinking/SKILL.md) | A/B 並列分析 + C 統合裁定による多角評価 |
| [`agent-kaizen`](.cursor/skills/agent-kaizen/SKILL.md) | kit 内部の manifest→生成物チェーンの整合性検査（18 評価観点） |

## 本リポジトリの dogfooding 既定

ルート `manifest.yaml` では、オプション機能がすべて有効化されています（生成先プロジェクトでは Phase 1.5 の AskQuestion で個別に決定）。

| 設定キー | 既定値 | 生成物 |
| --- | --- | --- |
| `code_review.enabled` | `true` | `agent-code-review`、`bin/github-pr-{reviews,comment,reply}-safe` |
| `github_pr.enabled` | `true` | `agent-github-pr` |
| `github_issue.enabled` | `true` | `agent-github-issue`、`bin/github-issue-{create,read}-safe` |
| `coderabbit.enabled` | `true` | `.coderabbit.yaml` |
| `agent_workflow.enabled` | `true` | `docs/agent-tasks/**`、`workflow-orchestrator`、`requirement-analysis`、各種 gate スクリプト |
| `agent_workflow.maintenance_docs.enabled` | `true` | `maintenance-docs-workflow`、`docs/agent-tasks/maintenance-docs/` |
| `agent_workflow.maintenance_gotchas.enabled` | `true` | `maintenance-gotchas-workflow` |
| `deep_thinking.enabled` | `true` | `deep-thinking`（`config.yaml` + references） |
| `cross_repo_knowledge.enabled` | `true` | `cross-repository-knowledge-link`、`bin/cross-repo-sync-safe` |
| `agent_kaizen.enabled` | `true` | `agent-kaizen`（`SKILL.md` + `config.yaml` + references） |

> 本キットリポジトリ自体にアプリケーションコード（`package.json` 等）は含まれません。`project.quality_gate` の backend command（`pnpm run *`）は tech stack 設計書から導出される生成先プロジェクト向け contract です。AI・docs・gate scripts は `bin/quality-gate <subcmd>` を公開入口として使用し、backend command を直接実行しません。

## 生成ワークフロー

Cursor では対象プロジェクトで「Agentic 基盤を生成して」「基盤ファイルを更新して」「techstack を取り込んで再生成して」などと依頼すると、`agentic-workflow-foundation` が次の流れを実行します。

1. **Phase 1**: seed manifest / templates / resolver を変更する必要がある場合だけ更新する
2. **Phase 1.45**: `run_resolved_engine.py bootstrap` で root `manifest.yaml` を作成、または `framework:` ブロックを seed から同期する
3. **Phase 1.5**: `project.*`、`workflow_pattern`、CodeRabbit / review / GitHub PR / GitHub Issue / agent workflow / dual thinking / cross-repo スキル生成有無を確定する
4. **Phase 1.55**: `resolve_budget_thresholds.py` で `min_context_window_tokens` から Context Budget 閾値を算出する
5. **Phase 1.6**: `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` から `tech_stack` を root `manifest.yaml` へ取り込む
6. **Phase 1.65**: `tech_stack` から `G-GEN`、`G-BUILD`、`G-LINT`、`G-TEST` と package script contract を導出する
7. **Phase 1.66**: CodeRabbit が有効な場合、tools / path filters / path instructions を解決する
8. **Phase 1.67**: `tech_stack` から Domain 層ドキュメント用の tech-stack 固有セクションリストを解決する
9. **Phase 1.7**: tech stack policy と実リポジトリの整合をチェックする
10. **Phase 2**: 一時 resolved skill-dir から基盤ファイル群を生成する
11. **Phase 3**: 冪等性、required sections、deep-thinking / requirement-analysis の静的契約を監査する
12. **Phase 4**: 確定値、生成物、ゲート結果を報告する

## 手動実行

通常は Cursor Skill 経由で実行します。手動で確認する場合は、foundation 専用ラッパーを入口にします。

```bash
# root manifest.yaml を seed から作成 / framework ブロックを同期
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py bootstrap

# Context Budget 閾値を min_context_window_tokens から導出
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_budget_thresholds.py

# tech stack を root manifest.yaml > tech_stack へ取り込み
python3 .cursor/skills/agentic-workflow-foundation/scripts/ingest_tech_stack.py

# quality gate / package script contract を tech_stack から導出
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_quality_gate.py

# CodeRabbit 設定を tech_stack から導出（coderabbit.enabled: true の場合）
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_coderabbit.py

# Domain 層ドキュメント用の tech-stack 固有セクションを導出
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_domain_docs.py

# tech stack policy と実リポジトリの整合確認
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_tech_stack_conformance.py

# 生成
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py generate

# 冪等性ドライラン（wrapper 経由）
bin/quality-gate check

# 監査（wrapper 経由）
bin/quality-gate audit

# kit 全自己検証（audit + foundation script tests）
bin/quality-gate self

# 下流プロジェクトの検証（build → lint → test）
bin/quality-gate verify
```

`agentic-workflow-engine/scripts/generate.py` と `audit.py` を直接呼ぶのは、エンジン単体の検証時だけです。通常の foundation 生成では `run_resolved_engine.py` が upstream metadata と root manifest overlay を解決してから engine を呼びます。`bin/quality-gate` は公開入口であり、AI・docs・gate scripts はこの wrapper 経由で検証を実行します。

## 生成物

現行 seed manifest の `outputs[]` は次を管理します。

| 種別 | ファイル |
| --- | --- |
| Context | `AGENTS.md`、`CLAUDE.md` |
| Cursor Rules | `.cursor/rules/00-init.mdc`、`01-critical-constraints.mdc`、`02-agent-conduct.mdc` |
| Hooks | `.cursor/hooks/guard-git-write.sh`、`session-bootstrap.sh`、`session-budget-tracker.sh`、`session-shell-tracker.sh`、`session-response-tracker.sh`、`session-compact-observer.sh`、`session-budget-evaluator.sh`、`.cursor/hooks/README.md`、`.cursor/hooks.json` |
| Docs (Meta) | `docs/AGENT_RUNBOOK.md`、`docs/QUALITY_GATE.md`、`docs/CONTEXT_BUDGET.md`、`docs/references/context-budget-internals.md`、`docs/DECISIONS.md`、`docs/GOTCHAS.md` |
| Docs (Domain) | `docs/tech-stack.md`、`docs/spec.md`、`docs/spec/README.md`、`docs/architecture.md`、`docs/api.md`、`docs/data-models.md`、`docs/coding-standards.md`、`docs/workflows.md` |
| Session Skills | `.cursor/skills/session-planning/SKILL.md`、`.cursor/skills/session-handover/SKILL.md`、`.cursor/skills/session-handover/scripts/verification-gate.sh`、`.cursor/skills/session-handover/scripts/session-start-gate.sh`、`.cursor/skills/session-handover/scripts/plan-gate.sh`、`.cursor/skills/session-handover/scripts/workflow-gate.sh`、`.cursor/skills/session-handover/scripts/archive-gate.sh`、`.cursor/skills/session-handover/scripts/gate-report.py`、`.cursor/skills/session-handover/scripts/gate-adr.py`、`.cursor/skills/session-handover/scripts/gate-artifact.py`、`.cursor/skills/session-handover/scripts/gate-redispatch.py`、`.cursor/skills/decisions-record/SKILL.md` |
| GitHub Wrappers | `bin/_github-app-auth.sh`、`bin/github-pr-create-safe` |
| Optional Review | `.cursor/skills/agent-code-review/**`、`bin/github-pr-{reviews,comment,reply}-safe`、`.coderabbit.yaml` |
| Optional GitHub PR | `.cursor/skills/agent-github-pr/**` |
| Optional GitHub Issue | `.cursor/skills/agent-github-issue/**`、`bin/github-issue-{create,read}-safe` |
| Optional Agent Workflow | `docs/agent-tasks/agent-workflow/**`、`docs/agent-tasks/README.md`、`docs/agent-tasks/{reports,maintenance-docs}/`、`.cursor/skills/workflow-orchestrator/**`、`.cursor/skills/requirement-analysis/**`、任意の `.cursor/skills/maintenance-{docs,gotchas}-workflow/**` |
| Optional Deep Thinking | `.cursor/skills/deep-thinking/SKILL.md`、`.cursor/skills/deep-thinking/config.yaml`、`.cursor/skills/deep-thinking/README.md`、`.cursor/skills/deep-thinking/references/**` |
| Optional Cross-Repo | `.cursor/skills/cross-repository-knowledge-link/**`、`bin/cross-repo-sync-safe` |
| Optional Agent Kaizen | `.cursor/skills/agent-kaizen/SKILL.md`、`.cursor/skills/agent-kaizen/config.yaml`、`.cursor/skills/agent-kaizen/references/**` |
| Ignore Blocks | `.gitignore`、`.cursorignore` |

各オプション出力の条件:

- `.cursor/skills/agent-code-review/**` と `bin/github-pr-{reviews,comment,reply}-safe` — `code_review.enabled: true` の場合のみ
- `.cursor/skills/agent-github-pr/**` — `github_pr.enabled: true` の場合のみ
- `.cursor/skills/agent-github-issue/**` と `bin/github-issue-{create,read}-safe` — `github_issue.enabled: true` の場合のみ
- `.coderabbit.yaml` — `coderabbit.enabled: true` の場合のみ
- `docs/agent-tasks/agent-workflow/**`、`docs/agent-tasks/reports/`、`.cursor/skills/workflow-orchestrator/**`、各種 workflow gate スクリプト — `agent_workflow.enabled: true` の場合のみ
- `.cursor/skills/requirement-analysis/**` — `agent_workflow.enabled: true` の場合
- `.cursor/skills/maintenance-docs-workflow/**` — `agent_workflow.maintenance_docs.enabled: true` の場合のみ
- `.cursor/skills/maintenance-gotchas-workflow/**` — `agent_workflow.maintenance_gotchas.enabled: true` の場合のみ
- `.cursor/skills/deep-thinking/**` — `deep_thinking.enabled: true` の場合のみ
- `.cursor/skills/cross-repository-knowledge-link/**` と `bin/cross-repo-sync-safe` — `cross_repo_knowledge.enabled: true` の場合のみ
- `.cursor/skills/agent-kaizen/**` — `agent_kaizen.enabled: true` の場合のみ

Domain 層ドキュメント（`docs/spec.md` 等）は `seed` モードで初回のみ生成し、以降は PO が内容を充実させます。

## 5層モデル

このキットは AI エージェント運用を 5 層で整理します。

| Layer | 役割 | 本キットでの表現 |
| --- | --- | --- |
| 1. Context | 目的・判断基準・運用入口 | `AGENTS.md`、`CLAUDE.md`、`docs/*` |
| 2. Constraints | 常時適用される制約 | `.cursor/rules/*.mdc` |
| 3. Capabilities | 必要時に呼び出す専門手順 | `session-*`、`workflow-orchestrator`、`requirement-analysis`、`maintenance-*-workflow`、GitHub 連携、`cross-repository-knowledge-link`、`deep-thinking`、`agent-kaizen` |
| 4. Automation | ツール実行前後・セッション境界の自動処理 | `.cursor/hooks/*`、`.cursor/hooks.json` |
| 5. Delegation | 子エージェントへの委譲 | 本キットでは生成しない。Cursor 組み込み Subagent を利用する |

Meta 層 / Domain 層はドキュメント命名上の 2 層モデルです。Layer 1〜5 は運用アーキテクチャ上の分類で、別軸として扱います。

## 設計原則

### 生成物を直接編集しない

`AGENTS.md`、Rules、Hooks、生成 docs、生成スキル、`bin/` wrapper は出力です。変更は upstream docs、seed `manifest.yaml`、`templates/`、resolver scripts、または root `manifest.yaml` の project 値を更新して再生成します。直接編集は `audit` が drift として検出します。

### root manifest の責務を分ける

root `manifest.yaml` は対象プロジェクトの正式 project manifest です。ただし `framework:` ブロックの SoT は seed manifest で、root 側は同期された複製です。`framework.budget_thresholds` は Phase 1.55 の `resolve_budget_thresholds.py` が `project.context_budget.min_context_window_tokens` から算出して上書きする（唯一の例外）。手編集してよいのは、Phase 1.5 / 1.55 / 1.6 / 1.65 / 1.66 / 1.67 が扱う `project`、`tech_stack`、`session`、`quality_gate_contract`、`domain_docs`、`code_review`、`github_pr`、`github_issue`、`coderabbit`、`agent_workflow`、`deep_thinking`、`cross_repo_knowledge` などの per-project 値です。

### upstream docs は immutable input

`AI_AGENT_UNIFIED_DESIGN.md` と `AI_BUSINESS_AGENT_SUITE.md` は読み取り専用の upstream SoT です。`run_resolved_engine.py` が存在有無と fingerprint を resolved manifest に反映しますが、スキル実行で書き換えません。

### tech stack は project input

`TECHNOLOGY_STACK_UNIFIED_DESIGN.md` はプロジェクトごとに変わる入力です。`ingest_tech_stack.py` が root `manifest.yaml > tech_stack` へ取り込み、`docs/tech-stack.md`、quality gate、CodeRabbit 設定、Domain 層ドキュメントの元データになります。

### Context Budget は Hook で観測する

生成される Hooks は、危険な Git 操作のガードと長時間セッションの引き継ぎ促進を担います。`prompt_count`、`shell_bytes`、compact イベントを proxy 指標として Yellow / Red を判定し、必要に応じて handoff manifest（`.cursor/.session/handoff-{session_id}.md`）を使った新規チャット移行を促します。技術詳細は `docs/CONTEXT_BUDGET.md` と `.cursor/hooks/README.md` を参照。

## 前提条件

- Python 3（生成・監査エンジンは標準ライブラリのみ）
- PyYAML（`agent_workflow.enabled: true` で step artifact ゲートを使う場合）
- `git`
- `jq`（Hook 実行時を推奨。未インストール時は fail-open）
- `gh`（GitHub 連携スキル使用時を推奨）
- 必要に応じて `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md`
- Optional: CodeRabbit / GitHub review 運用を使う場合は、対象プロジェクト側の GitHub / CodeRabbit 設定

macOS では `make install` / `make check` で CLI 依存を一括確認できます。

外部サービス・Cursor 設定を含む詳細なセットアップ手順は **[setup.md](setup.md)** を参照。

## このリポジトリと生成先

本リポジトリはジェネレータ・ツールキット本体です。対象プロジェクトにこのキットの `.cursor/skills/agentic-workflow-foundation` と `.cursor/skills/agentic-workflow-engine` を配置し、Cursor から `agentic-workflow-foundation` を起動すると、対象プロジェクトのルートに基盤ファイル群が生成されます。

本リポジトリ自身も dogfooding 対象のため、ルート直下に `manifest.yaml` と生成物が存在します。キット開発時は seed manifest / templates を変更し、再生成 + audit で整合を保ちます。

詳細な運用手順は [`agentic-workflow-foundation/SKILL.md`](.cursor/skills/agentic-workflow-foundation/SKILL.md)、エンジン仕様は [`agentic-workflow-engine/SKILL.md`](.cursor/skills/agentic-workflow-engine/SKILL.md) を参照してください。

## ライセンス

[Apache License 2.0](LICENSE)
