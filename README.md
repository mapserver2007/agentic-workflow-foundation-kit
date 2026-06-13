# Agentic Workflow Foundation Kit

AI エージェント（Cursor Agent 等）を開発プロジェクトに組み込むための**基盤ファイル群を、自己完結した Source of Truth から決定論的に生成・メンテナンスする**ツールキットです。

一次 SoT は [`agentic-workflow-foundation`](.cursor/skills/agentic-workflow-foundation/SKILL.md) スキル配下の seed `manifest.yaml` + `templates/` です。スキル実行時にリポジトリ直下 `manifest.yaml` が正式な project manifest として生成され、Python 製の [`agentic-workflow-engine`](.cursor/skills/agentic-workflow-engine/SKILL.md) が、`AGENTS.md`・Cursor Rules・Hooks・運用 docs・Layer 3 セッション管理スキルを**冪等・再現的**に出力します。旧称 `deterministic-generator` は現在の実行経路ではなく、README とスキルの正規手順では `agentic-workflow-engine` を使います。

フレームワークの思想（組織内の非公開な AI エージェント設計フレームワーク由来）は seed manifest + templates へ内部化済みで、生成時には参照しません。プロジェクトごとに変動する技術スタックは seed manifest には焼き込まず、スキル実行で生成された root `manifest.yaml > tech_stack` へ `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` から取り込んだ結果を生成物へ反映します。生成物を直接編集せず、正本を更新して再生成する運用を前提としています。

## 何ができるか

| レイヤー | 生成される主な成果物 |
| --- | --- |
| **Meta 層**（エージェント基盤） | `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/*.mdc` / `.cursor/hooks/*.sh` / `.cursor/hooks.json` |
| **Domain 層**（プロジェクト文書） | `docs/AGENT_RUNBOOK.md` / `docs/QUALITY_GATE.md` / `docs/session-handoff-guide.md` / `docs/tech-stack.md` / `docs/DECISIONS.md`（seed）/ `docs/GOTCHAS.md`（seed） |
| **Layer 3**（セッション管理スキル） | `.cursor/skills/session-planning` / `.cursor/skills/session-handover` / `.cursor/skills/decisions-record` / `verification-gate.sh` |

> **用語の整理**: 上表の **Meta 層 / Domain 層** はドキュメント命名の semantic 2層モデル（大文字 = 判断フレームワーク、小文字 = プロジェクト固有仕様）です。**Layer 1〜5** は別軸の 5層モデル（エージェントの文脈・制約・能力・自動化・委譲）です。Meta 層の成果物は主に Layer 1〜2 と Layer 4 に、Domain 層は主に Layer 1 にマッピングされます。Layer 3 は 5層モデル上の Capabilities 層であり、Meta 層とは別カテゴリです。

対象プロジェクトに対して Cursor で「Agentic 基盤を生成して」「基盤ファイルを作って/更新して」等と依頼すると、[`agentic-workflow-foundation`](.cursor/skills/agentic-workflow-foundation/SKILL.md) スキルがワークフローを実行します。

## 5層モデル（Layer 1〜5）

5層モデルは、AI エージェントへのオンボーディングを**ソフトウェア開発プロセス（設計〜QA）のアナロジー**で整理したものです。

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
| **3. Capabilities** | トリガー条件に応じて呼び出される専門手順 | 実装手順書 / ランブック / 再利用モジュール | トリガー条件合致時 | `session-planning` / `session-handover` / `decisions-record` スキルと `verification-gate.sh`（親 manifest から生成） |
| **4. Automation** | エージェントループの特定タイミングで自動実行 | CI / pre-commit hook / QA ゲート | ツール実行前後・セッション境界 | `.cursor/hooks/*` / `.cursor/hooks.json`（Git 書き込みガード + Context Budget Hooks） |
| **5. Delegation** | メインコンテキストを保護し専門タスクを委譲 | 並列ジョブ / 専門ビルドワーカー / レビューボット | 明示的に起動 | **本キットでは生成しない**。Cursor 組み込み Subagent（`explore` / `shell` / `browser-use`）を優先し、必要時は `.cursor/agents/` を手動追加 |

### 各層の要点

**Layer 1（Context）** — エージェントが「何のために・どう判断するか」を復元する入口。`AGENTS.md` は Cursor の主要 Context ファイルであり、`.cursor/rules` の簡易代替としても機能します。`docs/` 配下は semantic 2層モデルで **Meta 層**（`DECISIONS.md` 等・他プロジェクトでも通用する役割名）と **Domain 層**（`tech-stack.md` 等・プロジェクト固有仕様）に分類されます。

**Layer 2（Constraints）** — 手続きではなく**宣言的な制約のみ**を記述します。ワークフロー手順は Layer 3 スキルに委譲し、ルールからは参照だけにします（Single Source of Truth）。

**Layer 3（Capabilities）** — セッション管理の中核。大規模タスク検知・追跡ドキュメント作成（`session-planning`）、セッション終了時の検証ゲートと引き継ぎ（`session-handover`）、設計判断の ADR 記録（`decisions-record`）を担います。これらの生成定義は `agentic-workflow-foundation` に内包され、基盤再生成時に Meta / Domain 層と同時に同期されます。

**Layer 4（Automation）** — Rules（~80% 遵守）では不十分な制約を Hooks（~100% 遵守）で強制・観測します。`beforeShellExecution` で危険な Git 操作を deny / ask し、`sessionStart` / `beforeSubmitPrompt` / `afterShellExecution` / `stop` で Context Budget を観測して Yellow / Red 到達時に引き継ぎを促します。

**Layer 5（Delegation）** — 調査・並列処理・レビューなどを子エージェントに委譲し、メインのコンテキストウィンドウを保護します。本キットの生成範囲外です。まず Cursor 組み込み Subagent（`explore` / `shell` / `browser-use`）の活用を検討し、不足する場合のみ `.cursor/agents/` を手動追加します。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│  設定スキル（What・seed SoT）— seed manifest + templates/        │
│  └ agentic-workflow-foundation  （Meta 層 + Domain 層 + Layer 3）│
│                                                                 │
│  ＊ unified/bas の思想は seed manifest + templates へ内部化済み（非権威の由来メモ）│
│  ＊ TECHNOLOGY_STACK_UNIFIED_DESIGN.md のみ実行時に取り込み（Phase 1.6）│
└──────────────────────────┬──────────────────────────────────────┘
                           │ 100% 決定論
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  agentic-workflow-engine（How）                                  │
│  generate.py / audit.py / genlib.py                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
                    出力ファイル群（リポジトリルートへ展開）
```

**What / How の分離**が中核です。

- **What（設定スキル）**: フレームワーク定義と root manifest の初期雛形を seed `manifest.yaml` と `templates/` に保持する SoT
- **How（生成エンジン）**: `agentic-workflow-engine` が `--skill-dir` 付きで決定論的に変換・監査する

**manifest → 出力ファイルは AI を介さずバイト一致で再現**されます（BAS の「Markdown は表現・YAML は定義」パターン）。出力モードは、全体を再描画する `render`、既存追記ログを守る `seed`、既存ファイルの管理ブロックだけを更新する `marker` の 3 種です。スキル実行で root `manifest.yaml` を生成した後、Phase 1.6 が `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` を決定論パースして `tech_stack` へ具体スタックを取り込みます（実 `package.json` / `wrangler.jsonc` があれば実態優先）。

## リポジトリ構成

```
agentic-workflow-foundation-kit/
├── README.md                          # 本ファイル
├── LICENSE                            # Apache License 2.0
│
└── .cursor/
    ├── docs/                          # unified/bas=非権威の設計由来メモ（非公開正本・.gitignore）/ techstack=取り込み元ポリシー源
    │   ├── （組織内 AI エージェント設計フレームワークの正本 2 点。非公開のため .gitignore で除外）
    │   └── TECHNOLOGY_STACK_UNIFIED_DESIGN.md
    │
    ├── mcp.json                       # GitHub MCP 設定（任意）
    │
    └── skills/
        ├── agentic-workflow-foundation/   # 設定スキル（Meta + Domain 層 + Layer 3）
        │   ├── SKILL.md                   # ワークフロー定義
        │   ├── manifest.yaml              # seed YAML（framework.* / outputs / project.* / tech_stack.* の初期雛形）
        │   ├── templates/                 # 出力テンプレート（rules / hooks / docs / session skills）
        │   ├── references/                # SoT トレーサビリティ
        │   └── scripts/
        │       ├── ingest_tech_stack.py            # techstack §9 → 生成済み root manifest.yaml > tech_stack 取り込み（Phase 1.6）
        │       └── check_tech_stack_conformance.py # policy↔reality 整合ゲート（Phase 1.7）
        │
        ├── agentic-workflow-engine/       # 生成/監査エンジン（How・現行）
        │   ├── SKILL.md
        │   └── scripts/
        │       ├── genlib.py              # 共有ライブラリ（最小 YAML ローダ等）
        │       ├── generate.py            # 生成（render / marker / seed モード）
        │       └── audit.py               # 冪等性 + 必須要件の監査
        │
        └── deterministic-generator/       # 旧称。正規手順では agentic-workflow-engine を使用
```

### スキル一覧と責務

| スキル | 種別 | 役割 |
| --- | --- | --- |
| [`agentic-workflow-foundation`](.cursor/skills/agentic-workflow-foundation/SKILL.md) | 設定（What） | Meta 層・Domain 層・Layer 3 セッション管理スキル群を生成。seed manifest から root `manifest.yaml` を生成し、PO が評価する |
| [`agentic-workflow-engine`](.cursor/skills/agentic-workflow-engine/SKILL.md) | エンジン（How） | `manifest.yaml` + `templates/` から出力を決定論的に生成・監査 |

## 生成ワークフロー（概要）

`agentic-workflow-foundation` は次の順序で実行します。外部設計書の同期・fingerprint drift 照合は生成フローから外れています。

1. **Phase 1** — フレームワーク定義（`framework.*`）を変更する場合のみ `manifest.yaml` を直接編集（人手起点・PO 承認）
2. **Phase 1.5** — プロジェクト設定（`project.*`）を確定（`workflow_pattern` は AskQuestion、それ以外は自動導出 / 固定値）
3. **Phase 1.6** — techstack 設計書を取り込み（`ingest_tech_stack.py` → 生成済み root `manifest.yaml > tech_stack`）
4. **Phase 1.7** — techstack 整合ゲート（`check_tech_stack_conformance.py`、policy↔reality）
5. **Phase 2** — 生成（`agentic-workflow-foundation`。Meta + Domain + Layer 3 を同時生成）
6. **Phase 3** — 監査ゲート（`audit.py`）
7. **Phase 4** — 報告

### 手動実行例

```bash
# techstack の取り込み（生成済み root manifest.yaml > tech_stack へ書き戻し）
python3 .cursor/skills/agentic-workflow-foundation/scripts/ingest_tech_stack.py

# techstack policy↔reality 整合ゲート
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_tech_stack_conformance.py

# Meta + Domain + Layer 3 の生成
python3 .cursor/skills/agentic-workflow-engine/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation

# 冪等性ドライラン（必要に応じて）
python3 .cursor/skills/agentic-workflow-engine/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation \
  --check

# 監査（冪等性 + 必須要件）
python3 .cursor/skills/agentic-workflow-engine/scripts/audit.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation
```

## 設計上の重要な原則

### 出力ファイルを直接編集しない

変更は必ず seed `manifest.yaml` / 生成済み root `manifest.yaml` / `templates/` を編集し、再生成します。生成物の直接編集は `audit.py` が drift として検出します（exit 1）。

### 追記ログは seed モードで保護する

`docs/DECISIONS.md` と `docs/GOTCHAS.md` は継続追記するログのため、存在しない場合だけ初期生成する `seed` モードです。生成を再実行しても既存の ADR / Gotchas エントリは上書きしません。

### `.gitignore` / `.cursorignore` は marker モードで更新する

既存内容を保持し、`marker_id: agentic-foundation` の管理ブロックだけを upsert します。ブロック外の手編集は生成器の管理対象外です。

### `[要確認]` は配布時の WARN として扱う

スキル実行で生成される root `manifest.yaml` には、コピー先プロジェクトで確定する `workflow_pattern` / `quality_gate` / `session.verification.gate_command` が `[要確認]` として残ります。`audit.py` はこれを FAIL ではなく WARN（exit 0）として扱い、Phase 1.5 / 1.6 で具体値へ更新します。

### 3 つの統一設計書の扱い（揮発性で二分）

| ID | ファイル | 扱い |
| --- | --- | --- |
| `unified` | 組織内設計フレームワーク（非公開正本・`.gitignore`） | **凍結・非権威の設計由来メモ**。思想は manifest+templates に内部化済み（生成時に参照しない） |
| `bas` | 組織内設計フレームワーク（非公開正本・`.gitignore`） | 同上（BAS 行動規律 Humble / Cautious / Thorough / Selective を内部化済み） |
| `techstack` | `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` | **プロジェクト毎に変動する実行時入力**。Phase 1.6 で生成済み root `manifest.yaml > tech_stack` へ取り込み → `docs/tech-stack.md`（Domain 層）を駆動 |

`unified` / `bas` は凍結前提のため自己完結 SoT（manifest + templates）へ内部化し、drift 照合・外部同期は廃止しました。`techstack` のみ変動するため実行時に決定論パースで取り込み、実 `package.json` があれば実態優先で上書きします。

### Context Budget Hooks

生成される Hook は、危険な Git 操作の deterministic guard と、長時間セッションの引き継ぎ促進を担います。

| Hook | イベント | 役割 |
| --- | --- | --- |
| `guard-git-write.sh` | `beforeShellExecution` | force push / 保護ブランチ直 push / 危険な reset 等を deny / ask |
| `session-bootstrap.sh` | `sessionStart` | セッション state 初期化 + handoff manifest の注入 |
| `session-budget-tracker.sh` | `beforeSubmitPrompt` | prompt 回数を観測 |
| `session-shell-tracker.sh` | `afterShellExecution` | shell 出力量を観測 |
| `session-budget-evaluator.sh` | `stop` | elapsed / prompt_count / shell_bytes から Yellow / Red を判定し、必要時に followup を返す |

### ワークフローパターン

プロジェクトの主アウトプットに応じて 3 パターンから選択します（Phase 1.5 で PO が確定）。

| パターン | 主アウトプット | 追跡ドキュメント |
| --- | --- | --- |
| 開発型 | 動くアプリケーション | `plan.md` |
| パイプライン型 | スクリプト生成データ | `playbook.md` |
| ドキュメント型 | ドキュメント群（SDD 成果物） | `session_plan.md` |

複合型になりそうな場合は、単一リポジトリ内で無理に混ぜず、ワークスペース分離の要否を確認してから主パターンを1つ確定します。

## 前提条件

- **Python 3**（標準ライブラリのみ。PyYAML 不要）
- **jq**（Hook 実行時を推奨。未インストール時はフェイルオープン）
- **techstack 設計書**: `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` をプロジェクトのポリシーに合わせて用意（Phase 1.6 の取り込み元。不在時は fail-open）

詳細は各スキルの `SKILL.md` を参照してください。

## このリポジトリと生成先の関係

本リポジトリは**ジェネレータ・ツールキット本体**です。`agentic-workflow-foundation` を実行すると、**カレントのワークスペース（対象プロジェクト）のルート**に `AGENTS.md` や `.cursor/rules/` 等が展開されます。

- 本リポジトリ: スキル定義・テンプレート・生成エンジンを保持
- 対象プロジェクト: 生成された基盤ファイルで AI エージェント運用を開始

## ライセンス

[Apache License 2.0](LICENSE)
