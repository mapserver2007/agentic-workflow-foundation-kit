---
name: agentic-workflow-foundation
description: >-
  スキル内 seed manifest + templates + Python generator により、
  Agentic Workflow 基盤ファイル群（AGENTS.md / CLAUDE.md /
  .cursor/rules/*.mdc / .cursor/hooks/* / .cursor/hooks.json /
  docs/AGENT_RUNBOOK.md / DECISIONS.md / GOTCHAS.md / QUALITY_GATE.md /
  session-handoff-guide.md / docs/tech-stack.md / session-planning /
  session-handover / decisions-record / .gitignore / .cursorignore）を
  冪等・再現的に生成/メンテナンスする。「Agentic 基盤を生成して」
  「基盤ファイルを作って/更新して」「techstack を取り込んで再生成して」
  「session 系スキルも含めて整備して」「agentic-workflow-foundation スキル」
  等を検知したときに使う。
  Generate / maintain the agentic workflow foundation files deterministically
  from a skill-bundled seed manifest + templates + generator.
  Do NOT use for: 機能単位の Design Doc（基本設計書）の作成・テンプレート書き出し（create-design-doc）、
  プロジェクト固有の業務仕様 docs（Domain 層）の作成。
disable-model-invocation: true
---

# agentic-workflow-foundation

Agentic Workflow 基盤ファイル群を、**スキル内に同梱された汎用 seed `manifest.yaml` + `templates/`** から冪等・再現的に生成/メンテナンスするスキル。

> `AI_AGENT_UNIFIED_DESIGN.md` / `AI_BUSINESS_AGENT_SUITE.md` の思想は本スキル作成時に `SKILL.md` / seed `manifest.yaml` / `templates/` へ内部化済み。スキル実行時にこの2つを再入力・再同期する必要はない。
>
> `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` だけはプロジェクトごとに変動する per-project 入力として扱い、スキル実行で生成されたリポジトリ直下 `manifest.yaml > tech_stack` へ Phase 1.6 で取り込む。
>
> リポジトリ直下 `manifest.yaml` は本スキル実行の生成物であり、生成ファイルの評価は PO が別途行う。

## アーキテクチャ（決定論型）

```text
seed SoT(.cursor/skills/agentic-workflow-foundation/manifest.yaml + templates)
       │
       ├─ Phase 1.5: project 設定確定 → root manifest.yaml 生成
       │
       ├─ Phase 1.6: techstack 設計書（必要時のみ）→ root manifest tech_stack
       │
       └─ 100%決定論 generate.py ──▶ 出力ファイル群
                                      │
                                      └─ audit.py / conformance gate
```

- **スキル内 `manifest.yaml` は root manifest 生成前の汎用 seed**。統一設計書の入力前のテンプレートに近い位置づけで、特定リポジトリの確定値を焼き込まない。
- **リポジトリ直下 `manifest.yaml` は本スキル実行で生成される正式 project manifest**。`project.*` / `tech_stack.*` / `session.verification.*` は生成後の root manifest で PO が評価する。
- **techstack は per-project パラメータ**。配布時点の seed manifest には具体スタックを焼き込まず、`ingest_tech_stack.py` が `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` を読んで生成済み root `manifest.yaml` を更新する。実 `package.json` / `wrangler.jsonc` があれば実態を優先する。
- **生成/監査エンジン（how）は独立スキル [`agentic-workflow-engine`](../agentic-workflow-engine/SKILL.md) に分離**。本スキルは「what（manifest + templates + 固有の取り込み/整合ロジック）」を担う設定スキル。
- **session 管理（Layer 3）は親に内包**。`session-planning` / `session-handover` / `decisions-record` は本スキルの `outputs[]` から生成し、別の `agentic-session-management` スキルは不要。

### 構成ファイル

| ファイル | 役割 |
| --- | --- |
| `.cursor/skills/agentic-workflow-foundation/manifest.yaml` | スキル内 seed YAML（framework 要件 / outputs カタログ / `marker_id` / project / tech_stack の初期雛形） |
| `manifest.yaml` | スキル実行で生成されるリポジトリ直下の正式 project manifest（project 設定 / tech_stack / session.verification） |
| `references/source-mapping.md` | manifest キー → 出力ファイル のトレーサビリティ |
| `references/design-conformance.md` | audit 判定の設計根拠 |
| `templates/*` | 出力ファイルのテンプレート |
| `scripts/ingest_tech_stack.py` | techstack 設計書 §9 → root `manifest.yaml > tech_stack` 取り込み |
| `scripts/check_tech_stack_conformance.py` | root `manifest.yaml > tech_stack` と `package.json` の意味的整合チェック |

> 生成エンジン（`generate.py` / `audit.py` / `genlib.py`）は本スキルには含まれず、[`agentic-workflow-engine`](../agentic-workflow-engine/SKILL.md) が提供する。
> 依存: Python 3 標準ライブラリのみ（PyYAML 不要）。Hook 実行時は `jq` を推奨（未インストール時はフェイルオープン）。

## ワークフロー（6フェーズ）

Phase は番号順に実行する。「不要」と自己判断してスキップしない。

```text
- [ ] Phase 1: manifest / templates のフレームワーク変更（必要時のみ、PO 承認）
- [ ] Phase 1.5: プロジェクト設定確定（AskQuestion / 自動導出 / 固定値）
- [ ] Phase 1.6: techstack 取り込み（ingest_tech_stack.py）
- [ ] Phase 1.7: techstack 整合ゲート（check_tech_stack_conformance.py）
- [ ] Phase 2: 生成（generate.py）
- [ ] Phase 3: 監査ゲート（audit.py）
- [ ] Phase 4: 報告
```

### 対話と中断の原則（全フェーズ共通）

- **AskQuestion は1ステップ＝1論点ずつ提示する**。複数の確認事項を1回の `AskQuestion` にまとめない。
- **各 AskQuestion には推奨案を必ず1つ添える**。トレードオフを1〜2行で示し、判断を丸投げしない。
- **ステップが失敗・問題を検知したら、そのステップで中断する**。次フェーズへ進まず、検知内容・原因・影響範囲・推奨対応を PO に報告する。
- unified/bas の再同期・fingerprint drift 照合は行わない。`check_design_drift.py` / `sync-ai-agent-unified-design` は本フローの構成要素ではない。

### Phase 1: manifest / templates 更新（必要時のみ）

自己完結 SoT を更新する必要がある場合だけ実行する。

1. 変更が `framework.*` / `templates/*` / `outputs[]` / `session.*` など基盤定義に及ぶか確認する。
2. 設計判断に該当する場合は、`AskQuestion` で PO に1論点ずつ確認し、承認を得てから変更する。
3. `project.*` は Phase 1.5、`tech_stack.*` は Phase 1.6 で扱い、スキル実行で生成されるリポジトリ直下 `manifest.yaml` に保存する。Phase 1 では混ぜない。

> `docs/DECISIONS.md` はこの基盤を利用して実アプリを作るときの判断記録であり、本ツールキット内部の変更理由を必ず ADR 化する場所ではない。

### Phase 1.5: プロジェクト設定確定（AskQuestion / 自動導出 / 固定値）

**発火条件**: `project.*` の必須フィールドに `[要確認]` が残っている場合。確定済みなら再質問せず Phase 1.6 へ進む。

`project.*` は manifest への PO 直接手入力・自由入力を原則廃止し、**AskQuestion / 自動導出 / 固定値**で確定する。

**(1) AskQuestion（多肢選択）**

- `workflow_pattern`: 主アウトプット / 最大リスク / 検証方法から、推奨案を添えて PO に選択してもらう。

| 選択肢 | 主アウトプット | 最大リスク | 検証方法 |
| --- | --- | --- | --- |
| 開発型 | 動くアプリケーション | リグレッション | 自動テスト + ビルド + 型チェック |
| パイプライン型 | スクリプト生成データ | AI 幻覚 | スクリプト出力の整合性チェック |
| ドキュメント型 | ドキュメント群（SDD 成果物） | 不完全・不整合 | 完了基準チェックリスト |

**(2) 自動導出（質問不要）**

- `tracking_artifact`: `workflow_pattern` から自動確定する。
- `name`: コピー先（実行先）リポジトリのディレクトリ名から自動導出する。
- `slug`: `name` から導出する。
- `quality_gate.{build,lint,test}_cmd`: `workflow_pattern` × `tech_stack` と実リポジトリの `package.json` / `Makefile` 等から導出する。実コマンドがあれば実態を優先する。

| workflow_pattern | tracking_artifact |
| --- | --- |
| 開発型 | `plan.md` |
| パイプライン型 | `playbook.md` |
| ドキュメント型 | `session_plan.md` |

**(3) 固定値**

- `one_liner` / `agent_role` / `priorities` / `boundaries.{always,ask_first,never_extra}` / `doc_navigation.domain[]`
- これらは本基盤の機能・運用制約を説明する固定値。コピー先リポジトリが変わっても不変。

**確定後**

- 確定値はすべて、スキル実行で生成されるリポジトリ直下 `manifest.yaml > project.*` に記入する。
- 「複合型」になりそうな場合は、ワークスペース分離判断を PO に確認してから主パターンを確定する。

### Phase 1.6: techstack 取り込み

`.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` がある場合、§9 の技術スタック表を生成済みのリポジトリ直下 `manifest.yaml > tech_stack` に取り込む。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/ingest_tech_stack.py
```

- 設計書が無い場合は WARN でスキップし、既存 root `manifest.yaml > tech_stack` を維持する。
- `package.json` / `wrangler.jsonc` がある場合は、実固定バージョンを優先して `version_policy` を上書きする。
- 生成前の `docs/tech-stack.md` は存在しなくてよい。ここで更新するのは生成元データ root `manifest.yaml > tech_stack`。
- seed manifest には具体スタックを焼き込まない。プロジェクトへ設置される具体値は、この Phase の入力（techstack 設計書 + 実 `package.json`）から決まる。

### Phase 1.7: techstack 整合ゲート

root `manifest.yaml > tech_stack`（policy）と `package.json`（reality）の意味的乖離を確認する。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_tech_stack_conformance.py
```

- exit 0 → PASS。WARN があっても生成へ進める。
- exit 1 → 不採用ライブラリや major policy 違反などの意味的違反。PO に報告して中断する。
- exit 2 → manifest 破損など致命的エラー。中断する。

### Phase 2: 生成

基盤一式と session 系3スキルを、スキル内 seed から生成された **リポジトリ直下 manifest.yaml** を正として生成する。

```bash
python3 .cursor/skills/agentic-workflow-engine/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation
```

- manifest + templates から全出力ファイルを生成/上書きする（冪等）。生成ファイルの評価は PO が行う。
- `.gitignore` / `.cursorignore` はマーカーブロックを upsert（既存内容は保持。`marker_id: agentic-foundation`）。
- Hook スクリプトと `session-handover/scripts/verification-gate.sh` には実行ビットを付与する。
- `session-planning` / `session-handover` / `decisions-record` は本スキルの `templates/skills/*` から生成する。別スキルの orchestration は行わない。

### Phase 3: 監査ゲート

親 skill-dir だけを監査する。session 系出力も親 `outputs[]` に含まれる。

```bash
python3 .cursor/skills/agentic-workflow-engine/scripts/audit.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation
```

- exit 0 → 冪等性 + required sections OK（`[要確認]` は WARN 表示だが PASS）。
- exit 1 → drift / 必須要件欠落 / ファイル不在。原因を特定し Phase 2 から再生成して修正する。
- exit 2 → テンプレート不在 / manifest 破損。中断してユーザーに報告する。

冪等性の最終確認は次でも確認できる。

```bash
python3 .cursor/skills/agentic-workflow-engine/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation \
  --check
```

### Phase 4: 報告

以下を報告する。

- Phase 1.6 / 1.7 の結果（techstack 取り込み・整合ゲート）
- 生成/更新した出力ファイル一覧（generate.py の出力）
- audit.py の結果（PASS / FAIL）
- Phase 1.5 で確定した `project.*` 値一覧
- 実行できなかったゲートがあれば理由

## 重要な制約

- **出力ファイルを直接編集しない**。変更は必ず seed `manifest.yaml` / 生成済み root `manifest.yaml` / `templates/` を編集して再生成する。
- **unified/bas を実行時入力として扱わない**。この2つの思想は本スキルに内部化済み。
- **techstack は root `manifest.yaml > tech_stack` へ取り込んでから生成する**。生成物 `docs/tech-stack.md` を事前入力として扱わない。
- **`project.*` は AskQuestion / 自動導出 / 固定値の3分類で確定する**。未確定で残った `[要確認]` は audit が WARN 扱い。
- **`quality_gate` は `workflow_pattern` × `tech_stack` と実リポジトリ証拠から導出する**。推測でコマンドを断定しない。
- 既存の `.gitignore` / `.cursorignore` の他の行を消さない（マーカーブロックのみ管理）。
- 不要になった `agentic-session-management` は再作成しない。session 系出力は生成済み root manifest から生成する。

## スコープ外

- **生成/監査エンジン `agentic-workflow-engine` 自体の生成**。エンジン（How）は独立スキルで、本スキルは `--skill-dir` 付きで呼び出すだけ。
- プロジェクト固有の業務仕様 docs（`docs/spec.md` / `docs/api.md` / curated 目次等）の生成。
- feature 単位の Design Doc 作成。
- unified/bas の動的再同期・fingerprint drift 追跡。

## Gotchas

> 集約先: [docs/GOTCHAS.md](../../../docs/GOTCHAS.md)
>
> agentic-workflow-foundation 運用中の失敗・踏み外し記録。Observe → Amend → Evolve サイクルの入口。

### 起票トリガー（いずれか 1 つ以上）

1. 開発者から「期待と違う」等の不一致指摘を受けた
2. 同じ問題で 2 回以上の修正が必要になった
3. 既存スキル・ドキュメント通りに作業したのに想定外の結果になった

### 記録フォーマット

```text
- YYYY-MM-DD: {症状} / {原因} / {再発防止策} / {関連ファイル or spec/runbookリンク}
```

### エントリ

(現時点のエントリは無し)
