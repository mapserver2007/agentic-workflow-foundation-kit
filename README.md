# Agentic Workflow Foundation Kit

AI エージェント（Cursor Agent 等）を開発プロジェクトに組み込むための**基盤ファイル群を、設計書から決定論的に生成・メンテナンスする**ツールキットです。

統一設計書（Source of Truth）を YAML 正本（`manifest.yaml`）に符号化し、Python ジェネレータで `AGENTS.md`・Cursor Rules・Hooks・ドキュメント一式を**冪等・再現的**に出力します。生成物を直接編集せず、正本を更新して再生成する運用を前提としています。

## 何ができるか

| レイヤー | 生成される主な成果物 |
| --- | --- |
| **Meta 層**（エージェント基盤） | `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/*.mdc` / `.cursor/hooks/*` / `.cursor/hooks.json` |
| **Domain 層**（プロジェクト文書） | `docs/AGENT_RUNBOOK.md` / `docs/QUALITY_GATE.md` / `docs/tech-stack.md` / `docs/DECISIONS.md`（seed）/ `docs/GOTCHAS.md`（seed） 等 |
| **Layer 3**（セッション管理スキル） | `session-planning` / `session-handover` / `decisions-record` スキルと検証ゲート雛形 |

> **用語の整理**: 上表の **Meta 層 / Domain 層** はドキュメント命名の semantic 2層モデル（大文字 = 判断フレームワーク、小文字 = プロジェクト固有仕様）です。**Layer 1〜5** は別軸の 5層モデル（エージェントの文脈・制約・能力・自動化・委譲）です。Meta 層の成果物は主に Layer 1〜2 と Layer 4 に、Domain 層は主に Layer 1 にマッピングされます。Layer 3 は 5層モデル上の Capabilities 層であり、Meta 層とは別カテゴリです（[ADR-0007](.cursor/skills/agentic-session-management/references/decisions.md)）。

対象プロジェクトに対して Cursor で「Agentic 基盤を生成して」「統一設計書から再生成して」等と依頼すると、[`agentic-workflow-foundation`](.cursor/skills/agentic-workflow-foundation/SKILL.md) スキルが 5 フェーズのワークフローを実行します。

## 5層モデル（Layer 1〜5）

[統一設計書 §5](.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md) で定義される 5層モデルは、AI エージェントへのオンボーディングを**ソフトウェア開発プロセス（設計〜QA）のアナロジー**で整理したものです。各層の実装方法の詳細は [§12](.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md) を参照してください。

```
┌─────────────────────────────────────────
│  Layer 1: Context（文脈）
│  プロジェクトの設定ファイル
│  = 要件定義書・仕様書（What / Why）
├─────────────────────────────────────────
│  Layer 2: Constraints（制約）
│  常時適用されるルール
│  = コーディング規約・設計ガイドライン
├─────────────────────────────────────────
│  Layer 3: Capabilities（能力）
│  必要時に呼び出されるスキル
│  = 実装手順書・ランブック・再利用可能モジュール
├─────────────────────────────────────────
│  Layer 4: Automation（自動化）
│  ツール実行前後の自動処理
│  = CI / 静的解析 / QA ゲート
├─────────────────────────────────────────
│  Layer 5: Delegation（委譲）
│  子エージェントへのタスク委譲
│  = 並列ワーカー / 専門ビルドジョブ
└─────────────────────────────────────────
```

| Layer | 役割 | 開発プロセスのアナロジー | 読み込みタイミング | 本キットが生成する主な成果物 |
| --- | --- | --- | --- | --- |
| **1. Context** | プロジェクトの目的・判断基準・セッションプロトコルを定義 | 要件定義書 / 仕様書 / README | セッション開始時に自動 | `AGENTS.md` / `CLAUDE.md` / `docs/AGENT_RUNBOOK.md` / `docs/QUALITY_GATE.md` 等（Meta 層 + Domain 層の文脈ドキュメント） |
| **2. Constraints** | 全セッションで守るべきルールを宣言的に定義 | コーディング規約 / lint ルール / 設計原則 | セッション開始時に自動 | `.cursor/rules/00-init.mdc` / `01-critical-constraints.mdc` / `02-agent-conduct.mdc` |
| **3. Capabilities** | トリガー条件に応じて呼び出される専門手順 | 実装手順書 / ランブック / 再利用モジュール | トリガー条件合致時 | `session-planning` / `session-handover` / `decisions-record` スキルと `verification-gate.sh`（`agentic-session-management` が生成） |
| **4. Automation** | エージェントループの特定タイミングで自動実行 | CI / pre-commit hook / QA ゲート | ツール実行前後・セッション境界 | `.cursor/hooks/*` / `.cursor/hooks.json`（`guard-git-write.sh` / `session-bootstrap.sh` 等） |
| **5. Delegation** | メインコンテキストを保護し専門タスクを委譲 | 並列ジョブ / 専門ビルドワーカー / レビューボット | 明示的に起動 | **本キットでは生成しない**。Cursor 組み込み Subagent（`explore` / `bash` / `browser`）を優先し、必要時は `.cursor/agents/` を手動追加 |

### 各層の要点

**Layer 1（Context）** — エージェントが「何のために・どう判断するか」を復元する入口。`AGENTS.md` は Cursor の主要 Context ファイルであり、`.cursor/rules` の簡易代替としても機能します。`docs/` 配下は semantic 2層モデルで **Meta 層**（`DECISIONS.md` 等・他プロジェクトでも通用する役割名）と **Domain 層**（`tech-stack.md` 等・プロジェクト固有仕様）に分類されます。

**Layer 2（Constraints）** — 手続きではなく**宣言的な制約のみ**を記述します。ワークフロー手順は Layer 3 スキルに委譲し、ルールからは参照だけにします（Single Source of Truth）。

**Layer 3（Capabilities）** — セッション管理の中核。大規模タスク検知・追跡ドキュメント作成（`session-planning`）、セッション終了時の検証ゲートと引き継ぎ（`session-handover`）、設計判断の ADR 記録（`decisions-record`）を担います。設定スキル `agentic-session-management` が親 `agentic-workflow-foundation` と分離されており、基盤再生成時に親→子の順で同期されます。

**Layer 4（Automation）** — Rules（~80% 遵守）では不十分な制約を Hooks（~100% 遵守）で強制します。例: `beforeShellExecution` で危険な Git 操作をブロック、`sessionStart` でコンテキスト注入、`stop` でセッション境界の検証を促進。

**Layer 5（Delegation）** — 調査・並列処理・レビューなどを子エージェントに委譲し、メインのコンテキストウィンドウを保護します。本キットの生成範囲外ですが、統一設計書では組み込み Subagent の活用を推奨しています。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│  3つの統一設計書（SoT）                                            │
│  .cursor/docs/AI_AGENT_UNIFIED_DESIGN.md                        │
│  .cursor/docs/AI_BUSINESS_AGENT_SUITE.md                        │
│  .cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md                │
└──────────────────────────┬──────────────────────────────────────┘
                           │ AI + PO レビュー（改版時）
                           │ fingerprint 照合（drift 検知）
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  設定スキル（What）— manifest.yaml + templates/                  │
│  ├ agentic-workflow-foundation  （Meta 層 + Domain 層）          │
│  └ agentic-session-management   （Layer 3、親 project.* 継承）  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 100% 決定論
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  deterministic-generator（How）                                  │
│  generate.py / audit.py / genlib.py                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
                    出力ファイル群（リポジトリルートへ展開）
```

**What / How の分離**が中核です。

- **What（設定スキル）**: 設計書の意図を `manifest.yaml` と `templates/` に符号化する
- **How（生成エンジン）**: `deterministic-generator` が `--skill-dir` 付きで決定論的に変換・監査する

設計書 → manifest のマッピングは AI と PO のレビューを伴いますが、**manifest → 出力ファイルは AI を介さずバイト一致で再現**されます（BAS の「Markdown は表現・YAML は定義」パターン）。

## リポジトリ構成

```
agentic-workflow-foundation-kit/
├── README.md                          # 本ファイル
├── LICENSE                            # Apache License 2.0
│
└── .cursor/
    ├── docs/                          # 統一設計書（同期先・SoT）
    │   ├── AI_AGENT_UNIFIED_DESIGN.md
    │   ├── AI_BUSINESS_AGENT_SUITE.md
    │   └── TECHNOLOGY_STACK_UNIFIED_DESIGN.md
    │
    ├── mcp.json                       # GitHub MCP（設計書同期用）
    │
    └── skills/
        ├── agentic-workflow-foundation/   # 親設定スキル（Meta + Domain 層）
        │   ├── SKILL.md                   # ワークフロー定義（5 フェーズ）
        │   ├── manifest.yaml              # YAML 正本（framework.* / project.* / outputs）
        │   ├── templates/                 # 出力テンプレート
        │   ├── references/                # 設計書トレーサビリティ
        │   └── scripts/
        │       └── check_design_drift.py  # 設計書 fingerprint 照合
        │
        ├── agentic-session-management/    # 子設定スキル（Layer 3）
        │   ├── SKILL.md
        │   ├── manifest.yaml              # inherits_project で親 project.* を継承
        │   ├── templates/skills/          # セッション管理スキル用テンプレート
        │   └── references/
        │
        ├── deterministic-generator/       # 生成/監査エンジン（How）
        │   ├── SKILL.md
        │   └── scripts/
        │       ├── genlib.py                # 共有ライブラリ（最小 YAML ローダ等）
        │       ├── generate.py              # 生成（render / marker / seed モード）
        │       └── audit.py                 # 冪等性 + 必須要件の監査
        │
        └── sync-ai-agent-unified-design/    # 設計書同期（private repo → .cursor/docs/）
            ├── SKILL.md
            ├── references/source.yaml       # 取得元リポジトリ設定
            └── scripts/
```

### スキル一覧と責務

| スキル | 種別 | 役割 |
| --- | --- | --- |
| [`agentic-workflow-foundation`](.cursor/skills/agentic-workflow-foundation/SKILL.md) | 設定（What） | Meta 層・Domain 層の基盤一式を生成。`project.*` の共有 SoT を持つ |
| [`agentic-session-management`](.cursor/skills/agentic-session-management/SKILL.md) | 設定（What） | セッション管理スキル群（Layer 3）を生成。親から `project.*` を継承 |
| [`deterministic-generator`](.cursor/skills/deterministic-generator/SKILL.md) | エンジン（How） | `manifest.yaml` + `templates/` から出力を決定論的に生成・監査 |
| [`sync-ai-agent-unified-design`](.cursor/skills/sync-ai-agent-unified-design/SKILL.md) | 同期 | private リポジトリから 3 つの統一設計書を `.cursor/docs/` へ取得 |

## 生成ワークフロー（概要）

`agentic-workflow-foundation` は次の順序で実行します。

1. **Phase 0** — 統一設計書の同期と fingerprint 照合（`check_design_drift.py`）
2. **Phase 1** — 設計書改版時のみ `manifest.yaml` を更新（PO 承認）
3. **Phase 1.5** — プロジェクト設定（`project.*`）を対話で確定（`AskQuestion` / 自由入力）
4. **Phase 2** — 生成（親 → 子の順）
   - 2a: `agentic-workflow-foundation`（Meta + Domain 層）
   - 2b: `agentic-session-management`（Layer 3）
5. **Phase 3** — 監査ゲート（`audit.py`、親 → 子）
6. **Phase 4** — 報告

### 手動実行例

```bash
# 設計書の改版検知
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_design_drift.py

# Meta + Domain 層の生成
python3 .cursor/skills/deterministic-generator/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation

# Layer 3 セッション管理スキルの生成
python3 .cursor/skills/deterministic-generator/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-session-management

# 監査（冪等性 + 必須要件）
python3 .cursor/skills/deterministic-generator/scripts/audit.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation
python3 .cursor/skills/deterministic-generator/scripts/audit.py \
  --skill-dir .cursor/skills/agentic-session-management
```

## 設計上の重要な原則

### 出力ファイルを直接編集しない

変更は必ず `manifest.yaml` または `templates/` を編集し、再生成します。生成物の直接編集は `audit.py` が drift として検出します（exit 1）。

### 3 つの統一設計書

| ID | ファイル | 主な用途 |
| --- | --- | --- |
| `unified` | `AI_AGENT_UNIFIED_DESIGN.md` | 5 層モデル・セッション管理・Skill/Rule/Hook 仕様 |
| `bas` | `AI_BUSINESS_AGENT_SUITE.md` | BAS 行動規律（Humble / Cautious / Thorough / Selective） |
| `techstack` | `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` | 技術スタック方針 → `docs/tech-stack.md`（Domain 層） |

`techstack` は Meta 層へ焼き込まず、`framework.tech_stack` 経由で Domain 層 `docs/tech-stack.md` を駆動します。

### ワークフローパターン

プロジェクトの主アウトプットに応じて 3 パターンから選択します（Phase 1.5 で PO が確定）。

| パターン | 主アウトプット | 追跡ドキュメント |
| --- | --- | --- |
| 開発型 | 動くアプリケーション | `plan.md` |
| パイプライン型 | スクリプト生成データ | `playbook.md` |
| ドキュメント型 | ドキュメント群（SDD 成果物） | `session_plan.md` |

## 前提条件

- **Python 3**（標準ライブラリのみ。PyYAML 不要）
- **jq**（Hook 実行時を推奨。未インストール時はフェイルオープン）
- **設計書同期**（初回）: `sync-ai-agent-unified-design` 用に GitHub 認証（Fine-grained PAT を `.env` の `GITHUB_TOKEN` に設定）と Docker（MCP 経路）

詳細は各スキルの `SKILL.md` を参照してください。

## このリポジトリと生成先の関係

本リポジトリは**ジェネレータ・ツールキット本体**です。`agentic-workflow-foundation` を実行すると、**カレントのワークスペース（対象プロジェクト）のルート**に `AGENTS.md` や `.cursor/rules/` 等が展開されます。

- 本リポジトリ: スキル定義・テンプレート・生成エンジンを保持
- 対象プロジェクト: 生成された基盤ファイルで AI エージェント運用を開始

## ライセンス

[Apache License 2.0](LICENSE)
