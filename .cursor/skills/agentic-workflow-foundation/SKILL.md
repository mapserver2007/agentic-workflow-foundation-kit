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
- **生成/監査エンジン（how）は独立スキル [`deterministic-generator`](../deterministic-generator/SKILL.md) に分離**。本スキルは「what（manifest + templates + 設計書固有ロジック）」を担う設定スキルで、生成・冪等監査の実体は deterministic-generator の `generate.py` / `audit.py` を `--skill-dir` 付きで呼び出す（エンジン自体の扱いは「スコープ外」を参照）。
- **セッション管理スキル（Layer 3 / `agentic-session-management`）の生成を orchestrate する**。基盤メンテと同期して再生成し（親→子）、共有 `project.*` は本スキルの manifest を SoT として子が `inherits_project` で継承する（ADR-0007）。

### 構成ファイル

| ファイル | 役割 |
| --- | --- |
| `manifest.yaml` | YAML 正本（設計書 fingerprint / framework 要件 / outputs カタログ / `marker_id` / project 記入欄） |
| `references/source-mapping.md` | 設計書セクション → manifest キー → 出力ファイル のトレーサビリティ |
| `references/design-conformance.md` | 設計書由来の必須要件（audit 判定の設計根拠） |
| `templates/*` | 出力ファイルのテンプレート（`{{path}}` プレースホルダ） |
| `scripts/check_design_drift.py` | 設計書 fingerprint 照合 → 改版検知 / `--update` で書き戻し（本スキル固有） |

> 生成エンジン（`generate.py` / `audit.py` / `genlib.py`）は本スキルには含まれず、[`deterministic-generator`](../deterministic-generator/SKILL.md) が提供する。
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
3. `project.*` は **Phase 1.5 の対話（`AskQuestion` + 自由入力）で確定する**。manifest への PO 直接手入力は廃止した。ここ（Phase 1）では触らない。
4. fingerprint を書き戻す:

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_design_drift.py --update
```

### Phase 1.5: プロジェクト設定確定（対話: `AskQuestion` + 自由入力）

**発火条件**: `project.*` の必須フィールドに `[要確認]` が残っている場合に発火する。**`[要確認]` が残るフィールドのみ**を対象に問う（確定済みは再質問しない＝冪等再生成で質問が膨れない）。全必須フィールドが確定済みならスキップして **Phase 2 へ**。

`project.*` は manifest への PO 直接手入力を廃止し、**すべて対話で AI が聞き取り、確定値を manifest に記入する**（BAS 提案→推奨→承認）。`AskQuestion` は多肢選択専用ツールのため、選択肢化できないフィールドは「自由入力」で聞き取る。両者を総称して本スキルでは「対話で確定」と呼ぶ。確定手段はフィールドの性質で3分類:

**(1) `AskQuestion`（多肢選択） — 選択肢化できるもの**

- `workflow_pattern`: 統一設計書 §8 の4問（主アウトプット / 最大リスク / 検知方法 → パターン）を踏まえ、`AskQuestion` で PO に選択させる。`project.one_liner` 等から妥当な **推奨案を1つ明示**する（例: 主アウトプットが動くアプリケーションなら「開発型」を推奨）。

   | 選択肢 | 主アウトプット | 最大リスク | 検証方法 |
   | --- | --- | --- | --- |
   | 開発型 | 動くアプリケーション | リグレッション | 自動テスト + ビルド + 型チェック |
   | パイプライン型 | スクリプト生成データ | AI 幻覚 | スクリプト出力の整合性チェック |
   | ドキュメント型 | ドキュメント群（SDD 成果物） | 不完全・不整合 | 完了基準チェックリスト |

- `quality_gate.{build,lint,test}_cmd`: AI がリポジトリ調査（`package.json` / `Makefile` / `pyproject.toml` 等）から候補コマンドを抽出し `AskQuestion` の選択肢にする。ビルド/テスト構成が無くゲートを敷けない場合は「該当なし」とし、**`quality_gate` を設定しない**（`[要確認]` を残さない＝audit の WARN 対象にもしない。推測でコマンドを断定しない）。

**(2) 決定論マッピング（質問不要）**

- `tracking_artifact`: `workflow_pattern` から自動確定する（マッピングの SoT は [`agentic-session-management` パターン別記入ガイド](../agentic-session-management/SKILL.md)）。

   | workflow_pattern | tracking_artifact |
   | --- | --- |
   | 開発型 | `plan.md` |
   | パイプライン型 | `playbook.md` |
   | ドキュメント型 | `session_plan.md` |

- `slug`: `name` から AI が導出する（厳密なルールは設けず AI 任せでよい。下流の出力ファイルで未使用のため弊害はない）。**PO には問わない**。

**(3) 自由入力（チャットで聞き取り → AI が manifest に記入。`AskQuestion` ではない）**

- `name` / `one_liner` / `agent_role` / `priorities` / `boundaries.{always,ask_first,never_extra}` / `doc_navigation.domain[]`
- これらはビジネス文脈依存で、AI が選択肢を作ると推測になる。**自由入力で PO の回答をそのまま記入する**。AI は参考例を提示してよいが、推測値で確定しない（BAS Humble）。
- 任意項目（`quality_gate.extra` / `boundaries.never_extra` 等）は PO が「不要」と回答すればスキップし `[要確認]` のまま残してよい。

**確定後**

- 確定値はすべて `agentic-workflow-foundation/manifest.yaml > project.*` に記入する（共有 SoT。子 `agentic-session-management` は `inherits_project` で継承するため記入は親 1 箇所のみ）。
- 「複合型」になりそうな場合は §8「複合型の場合」のワークスペース分離判断を PO に確認してから主パターンを確定する。

> `tracking_artifact` は追跡ドキュメント（`plan.md` / `playbook.md` / `session_plan.md`）であり、AI 実装レポート（`docs/agent-tasks/reports/`、`create-design-doc` 下流の別工程）とは別物。manifest 初期値の例示パスに引きずられないこと。

### Phase 2: 生成

基盤一式の生成を **2 段（2a → 2b）** で実行する。セッション管理スキル（Layer 3）は基盤インフラの一部であり、人間が別タイミングで生成するのではなく **基盤メンテと同期して再生成する**（親子 orchestrate）。共有 `project.*`（`workflow_pattern` / `tracking_artifact`）は子が `inherits_project` で本スキルの manifest から継承するため、必ず **2a（親）→ 2b（子）の順**で実行する。

**2a. 基盤ファイル群（Meta 層）**

```bash
python3 .cursor/skills/deterministic-generator/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation
```

- manifest + templates から全出力ファイルを生成/上書きする（冪等）。
- `.gitignore` / `.cursorignore` はマーカーブロックを upsert（既存内容は保持。`marker_id: agentic-foundation`）。
- Hook スクリプトには実行ビットを付与する。

**2b. セッション管理スキル群（Layer 3 / `agentic-session-management`）**

```bash
python3 .cursor/skills/deterministic-generator/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-session-management
```

- `session-planning` / `session-handover` / `decisions-record` と検証ゲート雛形を生成する。
- 共有 `project.*` は本スキルの manifest から継承される（`inherits_project`）。子固有値（`large_task_threshold` / `verification.gate_command`）は子スキルの Phase 1.5 で対話により確定する（`large_task_threshold` は `AskQuestion` の数値選択肢、`verification.gate_command` は親 `quality_gate` の流用 or リポジトリ調査→`AskQuestion`）。manifest 直接手入力は廃止。

### Phase 3: 監査ゲート

2a / 2b の両方を監査する（親 → 子の順）。

```bash
python3 .cursor/skills/deterministic-generator/scripts/audit.py \
  --skill-dir .cursor/skills/agentic-workflow-foundation
python3 .cursor/skills/deterministic-generator/scripts/audit.py \
  --skill-dir .cursor/skills/agentic-session-management
```

- exit 0 → 冪等性 + 設計書準拠 OK（`project.*` の `[要確認]` は WARN 表示だが PASS）。
- exit 1 → drift / 必須要件欠落 / ファイル不在。**FAIL を修正して Phase 2 から再実行**（Advisory ループ）。
- exit 2 → テンプレート不在 / manifest 破損。ユーザーに報告して停止。

> 子（`agentic-session-management`）の audit は `inherits_project` 解決後の `project` を検査するため、親由来の共有キー（`workflow_pattern` 等）が未記入なら子の WARN にも列挙される（＝親へ 1 度記入すれば解消する）。
> 冪等性の最終確認は両 `--skill-dir` で `generate.py ... --check` が exit 0 になることで担保する。

### Phase 4: 報告

以下を報告する:

- 生成/更新した出力ファイル一覧（generate.py の出力）
- audit.py の結果（PASS / FAIL）
- Phase 1.5 の対話で確定した `project.*` 値一覧（`AskQuestion` / 決定論マッピング / 自由入力の別）
- PO が「不要」と判断しスキップした任意項目（`[要確認]` のまま残したもの）
- drift があった場合は更新した manifest キーと起票すべき ADR

## 重要な制約

- **出力ファイルを直接編集しない**。変更は必ず `manifest.yaml` か `templates/` を編集して再生成する（直接編集は audit が drift 検出）。
- **`framework.*` の変更は Meta 層の設計判断**。設計書改版に基づき、PO 承認を得て行う。
- **`project.*` は Phase 1.5 の対話で AI が候補/推奨を提示し PO 承認で確定する**（manifest 直接手入力は廃止）。`AskQuestion`（多肢選択）/ 決定論マッピング / 自由入力の3分類で確定し、AI が候補を作れない純ビジネス値（`name` / `one_liner` / `agent_role` / `priorities` 等）は **PO の回答をそのまま記入し、推測で埋めない**（BAS Humble）。未確定で残った `[要確認]` は audit が WARN 扱い（FAIL ではない）。
- 既存の `.gitignore` / `.cursorignore` の他の行を消さない（マーカーブロックのみ管理）。

## スコープ外

- **生成/監査エンジン `deterministic-generator` 自体の生成**。エンジン（How）は独立スキルで、統一設計書を正本とする自動生成・drift 追跡の対象外（正本はエンジンの工学仕様）。本スキルはそれを `--skill-dir` 付きで**呼び出すだけ**で、エンジンのコードは生成・改修しない。エンジンの改修は `deterministic-generator` スキル内のスクリプトを正本として行う。
- プロジェクト固有の品質ゲートコマンド（`make build` 等）の実装。manifest の空欄として残す。
- セッション管理スキルの **テンプレート/manifest 定義**（what）は `agentic-session-management` が持つ。本スキルは Phase 2b/3 でその**生成を orchestrate するだけ**で、テンプレート内容は改修しない。
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
