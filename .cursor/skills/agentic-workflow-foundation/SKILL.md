---
name: agentic-workflow-foundation
description: >-
  3つの統一設計書（.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md /
  AI_BUSINESS_AGENT_SUITE.md / TECHNOLOGY_STACK_UNIFIED_DESIGN.md）を絶対ルール(SoT)とし、Agentic Workflow 基盤
  ファイル群（AGENTS.md / CLAUDE.md / .cursor/rules/*.mdc / .cursor/hooks/* /
  .cursor/hooks.json / docs/AGENT_RUNBOOK.md / DECISIONS.md / GOTCHAS.md /
  QUALITY_GATE.md / session-handoff-guide.md / .gitignore / .cursorignore）を
  YAML 正本(manifest.yaml) + テンプレート + Python generator で冪等・再現的に
  生成/メンテナンスする。「Agentic 基盤を生成して」「基盤ファイルを作って/更新して」
  「統一設計書から再生成して」「AGENTS.md や hooks をまとめて整備して」
  「agentic-workflow-foundation スキル」等を検知したときに使う。
  Generate / maintain the agentic workflow foundation files deterministically
  from the two unified design docs via a YAML manifest + templates + generator.
  Do NOT use for: 機能単位の Design Doc（基本設計書）の作成・テンプレート書き出し（create-design-doc）、
  プロジェクト固有の業務仕様 docs（Domain 層）の作成。
disable-model-invocation: true
---

# agentic-workflow-foundation

3つの統一設計書を**絶対的ルール（Source of Truth）**とし、Agentic Workflow 基盤ファイル群を**冪等・再現的**に生成/メンテナンスするスキル。

> **設計書ごとの性質の違い**: `unified` / `bas` は Meta 層基盤（AGENTS.md / rules / hooks 等）へ符号化する。`techstack`（技術スタック統一設計書）は性質が異なり、Meta 層へは焼き込まず `framework.tech_stack` 経由で **Domain 層 `docs/tech-stack.md`** を生成する（AGENTS.md からはポインタのみ）。これにより下流の Design Doc / AI レポート生成が技術制約を Domain ドキュメントとして参照できる。

## アーキテクチャ（決定論型）

```
設計書(SoT) ──AI+PO レビュー──▶ manifest.yaml(YAML正本) ──100%決定論──▶ 出力ファイル群
   │                                    ▲                                   │
   └──fingerprint照合(drift)────────────┘            audit(再生成diff=0)─────┘
```

- **`manifest.yaml` → 出力ファイル** は完全決定論（再実行でバイト一致 = 冪等）。AI は生成ループに入らない。
- **設計書 → `manifest.yaml`** は AI/PO レビュー付きマッピング。`check_design_drift.py` の fingerprint 照合で改版を検知し、manifest 更新を促して同期を保つ。
- BAS の「Markdown は表現・YAML は定義」パターンに準拠。
- **生成/監査エンジン（how）は [`manifest-generator`](../manifest-generator/SKILL.md) に分離**。本スキルは「what（設定: manifest + templates + 設計書固有ロジック）」を担う設定スキルであり、生成・冪等監査の実体は manifest-generator の `generate.py` / `audit.py` を `--skill-dir` 付きで呼び出す。出力ファイルの直接編集は同エンジンの audit が drift として検出する。
- **セッション管理スキル（Layer 3）の生成を orchestrate する**。`create-session-workflow` はエンジン視点では兄弟の設定スキル（別 manifest + templates）だが、セッション管理は基盤インフラの一部であり、人間が単独で実行するのではなく **本スキルの基盤メンテと同期して再生成する**（運用視点では親→子）。共有 `project.*` の Source of Truth は本スキルの manifest に一本化し、子は `inherits_project` で継承する（ADR-0007）。

### 構成ファイル

| ファイル | 役割 |
| --- | --- |
| `manifest.yaml` | YAML 正本（設計書 fingerprint / framework 要件 / outputs カタログ / `marker_id` / project 記入欄） |
| `references/source-mapping.md` | 設計書セクション → manifest キー → 出力ファイル のトレーサビリティ |
| `references/design-conformance.md` | 設計書由来の必須要件（audit 判定の設計根拠） |
| `templates/*` | 出力ファイルのテンプレート（`{{path}}` プレースホルダ） |
| `scripts/check_design_drift.py` | 設計書 fingerprint 照合 → 改版検知 / `--update` で書き戻し（本スキル固有） |

> 生成エンジン（`generate.py` / `audit.py` / `genlib.py`）は本スキルには含まれず、[`manifest-generator`](../manifest-generator/SKILL.md) が提供する。
> 依存: Python 3 標準ライブラリのみ（PyYAML 不要）。Hook 実行時は `jq` を推奨（未インストール時はフェイルオープン）。

## ワークフロー（5フェーズ）

Phase は番号順に実行する。「不要」と自己判断してスキップしない。

```
- [ ] Phase 0: 統一設計書の同期（不在/改版なら sync-ai-agent-unified-design で取得）→ fingerprint 照合（drift 検知）
- [ ] Phase 1: 改版時のみ manifest を更新（AI 提案 + PO 承認）
- [ ] Phase 1.5: プロジェクトパターン確定（AskQuestion で PO 選択 → workflow_pattern / tracking_artifact を確定）
- [ ] Phase 2: 生成（generate.py）
- [ ] Phase 3: 監査ゲート（audit.py）
- [ ] Phase 4: 報告
```

### Phase 0: 統一設計書の同期 → fingerprint 照合

3つの統一設計書（`.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md` / `AI_BUSINESS_AGENT_SUITE.md` / `TECHNOLOGY_STACK_UNIFIED_DESIGN.md`）は private リポジトリが SoT であり、`.cursor/docs/` への配置は [`sync-ai-agent-unified-design`](../sync-ai-agent-unified-design/SKILL.md) が担う。fingerprint 照合の前に**取得/最新化**を済ませる。

**Phase 0a: 同期（取得→ drift 照合の順）**

- 3つの設計書のいずれかが `.cursor/docs/` に**存在しない**場合 → `sync-ai-agent-unified-design` を実行して取得する。
- 存在する場合も、`sync-ai-agent-unified-design` を実行して**改版/更新があれば上書き**する（内容差分時のみ上書き＝冪等）。同期スキルが取得設定（`references/source.yaml`）未記入や取得失敗を報告したらユーザーに報告して停止する。

**Phase 0b: fingerprint 照合**

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_design_drift.py
```

- exit 0（改版なし）→ **Phase 2 へ**（既存 manifest のまま再生成）。
- exit 1（DRIFT / 未記録）→ **Phase 1 へ**。出力された「影響 manifest キー / 出力ファイル」を控える。
- exit 2（設計書不在）→ Phase 0a の同期を実行しても取得できていない状態。`sync-ai-agent-unified-design` の報告（設定未記入 / 取得失敗）をユーザーに伝えて停止する。

### Phase 1: manifest 更新（改版時のみ）

1. 設計書の変更差分を `references/source-mapping.md` で影響範囲に展開する。
2. 影響する `framework.*` キーを更新する。
   - **`framework.*`（Meta 層）の変更は設計判断**。`AskQuestion` で PO に確認し、承認を得てから変更する。
   - 変更が設計次元 D-* に該当する場合は、生成後 `docs/DECISIONS.md` に ADR を起票する。
3. `project.*` は PO 記入欄。ここでは触らない（`workflow_pattern` / `tracking_artifact` は **Phase 1.5** で AskQuestion により確定。その他は PO が別途記入）。
4. fingerprint を書き戻す:

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_design_drift.py --update
```

### Phase 1.5: プロジェクトパターン確定（AskQuestion）

`project.workflow_pattern` が `[要確認]`（未確定）の場合に発火する。確定済みならスキップして **Phase 2 へ**。

`workflow_pattern` と `tracking_artifact` は下流生成（Phase 2a の `AGENTS.md`、Phase 2b のセッション管理スキル）の入力になるため、**生成前に確定する**。これらは「AI の推測で埋める」のではなく、統一設計書 §8 のパターン選択フローに沿って **`AskQuestion` で PO に選択させて確定する**（BAS 提案→推奨→承認）。

1. 統一設計書 §8 の4問（主アウトプット / 最大リスク / 検知方法 → パターン）を踏まえ、`AskQuestion` で PO にパターンを選択させる。`project.one_liner` 等から妥当な **推奨案を1つ明示**する（例: 主アウトプットが動くアプリケーションなら「開発型」を推奨）。

   | 選択肢 | 主アウトプット | 最大リスク | 検証方法 |
   | --- | --- | --- | --- |
   | 開発型 | 動くアプリケーション | リグレッション | 自動テスト + ビルド + 型チェック |
   | パイプライン型 | スクリプト生成データ | AI 幻覚 | スクリプト出力の整合性チェック |
   | ドキュメント型 | ドキュメント群（SDD 成果物） | 不完全・不整合 | 完了基準チェックリスト |

2. PO の選択に応じて、`tracking_artifact` を **決定論マッピング**で確定する（マッピングの SoT は [`create-session-workflow` パターン別記入ガイド](../create-session-workflow/SKILL.md)）。

   | workflow_pattern | tracking_artifact |
   | --- | --- |
   | 開発型 | `plan.md` |
   | パイプライン型 | `playbook.md` |
   | ドキュメント型 | `session_plan.md` |

3. 確定値を `agentic-workflow-foundation/manifest.yaml > project.workflow_pattern` / `project.tracking_artifact` に記入する（共有 SoT。子 `create-session-workflow` は `inherits_project` で継承するため記入は親 1 箇所のみ）。
4. 「複合型」になりそうな場合は §8「複合型の場合」のワークスペース分離判断を PO に確認してから主パターンを確定する。

> `tracking_artifact` は追跡ドキュメント（`plan.md` / `playbook.md` / `session_plan.md`）であり、AI 実装レポート（`docs/agent-tasks/reports/`、`create-design-doc` 下流の別工程）とは別物。manifest 初期値の例示パスに引きずられないこと。

### Phase 2: 生成

基盤一式の生成を **2 段（2a → 2b）** で実行する。セッション管理スキル（Layer 3）は基盤インフラの一部であり、人間が別タイミングで生成するのではなく **基盤メンテと同期して再生成する**（親子 orchestrate）。共有 `project.*`（`workflow_pattern` / `tracking_artifact`）は子が `inherits_project` で本スキルの manifest から継承するため、必ず **2a（親）→ 2b（子）の順**で実行する。

**2a. 基盤ファイル群（Meta 層）**

```bash
python3 .cursor/skills/manifest-generator/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation
```

- manifest + templates から全出力ファイルを生成/上書きする（冪等）。
- `.gitignore` / `.cursorignore` はマーカーブロックを upsert（既存内容は保持。`marker_id: agentic-foundation`）。
- Hook スクリプトには実行ビットを付与する。

**2b. セッション管理スキル群（Layer 3 / `create-session-workflow`）**

```bash
python3 .cursor/skills/manifest-generator/scripts/generate.py \
  --skill-dir .cursor/skills/create-session-workflow
```

- `session-planning` / `session-handover` / `decisions-record` と検証ゲート雛形を生成する。
- 共有 `project.*` は本スキルの manifest から継承される（`inherits_project`）。子固有値（`large_task_threshold` / `verification.gate_command`）は子 manifest の PO 記入欄。

### Phase 3: 監査ゲート

2a / 2b の両方を監査する（親 → 子の順）。

```bash
python3 .cursor/skills/manifest-generator/scripts/audit.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation
python3 .cursor/skills/manifest-generator/scripts/audit.py \
  --skill-dir .cursor/skills/create-session-workflow
```

- exit 0 → 冪等性 + 設計書準拠 OK（`project.*` の `[要確認]` は WARN 表示だが PASS）。
- exit 1 → drift / 必須要件欠落 / ファイル不在。**FAIL を修正して Phase 2 から再実行**（Advisory ループ）。
- exit 2 → テンプレート不在 / manifest 破損。ユーザーに報告して停止。

> 子（`create-session-workflow`）の audit は `inherits_project` 解決後の `project` を検査するため、親由来の共有キー（`workflow_pattern` 等）が未記入なら子の WARN にも列挙される（＝親へ 1 度記入すれば解消する）。
> 冪等性の最終確認は両 `--skill-dir` で `generate.py ... --check` が exit 0 になることで担保する。

### Phase 4: 報告

以下を報告する:

- 生成/更新した出力ファイル一覧（generate.py の出力）
- audit.py の結果（PASS / FAIL）
- Phase 1.5 で確定した `workflow_pattern` / `tracking_artifact`（選択された場合）
- `project.*` に残る `[要確認]` 一覧（**PO が次に記入すべき項目**）
- drift があった場合は更新した manifest キーと起票すべき ADR

## 重要な制約

- **出力ファイルを直接編集しない**。変更は必ず `manifest.yaml` か `templates/` を編集して再生成する（直接編集は audit が drift 検出）。
- **`framework.*` の変更は Meta 層の設計判断**。設計書改版に基づき、PO 承認を得て行う。
- **`project.*` の `[要確認]` を AI が推測で埋めない**。PO 記入欄として残す（audit は WARN 扱い）。ただし `workflow_pattern` / `tracking_artifact` は例外で、**Phase 1.5 の `AskQuestion` による PO 選択結果**を決定論マッピングで確定する（AI の推測ではなく PO 承認に基づく確定）。
- 既存の `.gitignore` / `.cursorignore` の他の行を消さない（マーカーブロックのみ管理）。

## スコープ外

- プロジェクト固有の品質ゲートコマンド（`make build` 等）の実装。manifest の空欄として残す。
- セッション管理スキルの **テンプレート/manifest 定義**（what）は `create-session-workflow` が持つ。本スキルは Phase 2b/3 でその**生成を orchestrate するだけ**で、テンプレート内容は改修しない。
- techstack 由来の `docs/tech-stack.md` **以外** の Domain 層 docs（業務仕様 `docs/spec.md` / API 仕様 `docs/api.md` / curated 目次 `docs/README.md` 等）の生成。これらは下流の doc 生成スキルが実装物から作る。

## Gotchas

> 集約先: [docs/GOTCHAS.md](../../../docs/GOTCHAS.md)
>
> agentic-workflow-foundation 運用中の失敗・踏み外し記録。Observe → Amend → Evolve サイクルの入口。
> 集約済みエントリは docs/GOTCHAS.md を参照。新規エントリは下記「エントリ」配下に追記し、次回集約で `docs/GOTCHAS.md` に転記後ここからは削除される。

### 起票トリガー（いずれか 1 つ以上）

1. 開発者から「期待と違う」等の不一致指摘を受けた
2. 同じ問題で 2 回以上の修正が必要になった
3. 既存スキル・ドキュメント通りに作業したのに想定外の結果になった

### 記録フォーマット

```
- YYYY-MM-DD: {症状} / {原因} / {再発防止策} / {関連ファイル or spec/runbookリンク}
```

### エントリ

(現時点のエントリは無し)
