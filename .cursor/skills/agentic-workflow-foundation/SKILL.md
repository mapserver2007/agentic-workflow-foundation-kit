---
name: agentic-workflow-foundation
description: >-
  統一設計書を immutable upstream SoT として読み、スキル内 seed
  manifest + templates + root manifest から一時 resolved skill-dir を
  stateless に作成して Python generator に渡し、
  Agentic Workflow 基盤ファイル群（AGENTS.md / CLAUDE.md /
  .cursor/rules/*.mdc / .cursor/hooks/* / .cursor/hooks.json /
  docs/AGENT_RUNBOOK.md / DECISIONS.md / GOTCHAS.md / QUALITY_GATE.md /
  CONTEXT_BUDGET.md / docs/tech-stack.md / session-planning /
  session-handover / .gitignore / .cursorignore）を
  冪等・再現的に生成/メンテナンスする。「Agentic 基盤を生成して」
  「基盤ファイルを作って/更新して」「techstack を取り込んで再生成して」
  「session 系スキルも含めて整備して」「agentic-workflow-foundation スキル」
  等を検知したときに使う。
  Generate / maintain the agentic workflow foundation files deterministically
  from immutable unified design inputs, a skill-bundled seed manifest +
  templates, and a stateless resolved skill-dir.
  Do NOT use for: 機能単位の Design Doc（基本設計書）の作成・テンプレート書き出し（create-design-doc）、
  プロジェクト固有の業務仕様 docs（Domain 層）の作成。
disable-model-invocation: true
---

# agentic-workflow-foundation

Agentic Workflow 基盤ファイル群を、**immutable upstream SoT（統一設計書） + スキル内 seed `manifest.yaml` / `templates/` + root `manifest.yaml`** から、毎回一時 resolved skill-dir を作って冪等・再現的に生成/メンテナンスするスキル。

> `AI_AGENT_UNIFIED_DESIGN.md` / `AI_BUSINESS_AGENT_SUITE.md` は immutable upstream SoT として読み取り、`run_resolved_engine.py` が一時 resolved skill-dir の `manifest.yaml` へ決定論的に展開する。スキル内 seed `manifest.yaml` / `templates/` は schema / default / fallback であり、実行結果によって永続更新しない。
>
> `TECHNOLOGY_STACK_UNIFIED_DESIGN.md` だけはプロジェクトごとに変動する per-project 入力として扱い、スキル実行で生成されたリポジトリ直下 `manifest.yaml > tech_stack` へ Phase 1.6 で取り込む。Phase 1.65 では、その技術スタックから `G-GEN` / `G-BUILD` / `G-LINT` / `G-TEST` と package script contract を PO 確認なしで決定する。
>
> リポジトリ直下 `manifest.yaml` は本スキル実行の生成物であり、生成ファイルの評価は PO が別途行う。

## アーキテクチャ（stateless 決定論型）

```text
immutable upstream SoT(.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md / AI_BUSINESS_AGENT_SUITE.md)
       │
seed schema/default(.cursor/skills/agentic-workflow-foundation/manifest.yaml + templates)
       │
       ├─ Phase 1.5: init.yaml → apply_kit_init.py → root manifest.yaml の project.*
       ├─ Phase 1.55: min_context_window_tokens → budget_thresholds 算出
       │
       ├─ Phase 1.6: techstack 設計書（必要時のみ）→ root manifest tech_stack
       ├─ Phase 1.65: tech_stack → quality_gate / quality_gate_contract
       │
      └─ run_resolved_engine.py（unified design + root manifest overlay）
             │
             ├─ 一時 resolved skill-dir（実行後破棄 / 永続状態なし）
             │
             └─ 100%決定論 engine ──▶ 出力ファイル群
                                      │
                                      └─ audit.py / conformance gate
```

- **統一設計書は immutable upstream SoT**。実行時に読み取り、fingerprint と構造化要件を一時 resolved manifest へ展開する。読み取り専用であり、スキル実行で書き換えない。
- **スキル内 `manifest.yaml` は root manifest 生成前の汎用 seed / schema / default**。統一設計書から一意に抽出できない既定値を保持するが、実行結果によって永続更新しない。
- **リポジトリ直下 `manifest.yaml` は本スキル実行で生成される正式 project manifest**。`project.*` / `framework.accd_axes` / `tech_stack.*` / `session.verification.*` / `code_review` / `github_pr` / `github_issue` / `coderabbit` は生成後の root manifest で PO が評価する。
- **techstack は per-project パラメータ**。配布時点の seed manifest には具体スタックを焼き込まず、`ingest_tech_stack.py` が `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` を読んで生成済み root `manifest.yaml` を更新する。`resolve_quality_gate.py` はこの `tech_stack` だけから root scripts の canonical G-* を決める。
- **生成/監査エンジン（how）は独立スキル [`agentic-workflow-engine`](../agentic-workflow-engine/SKILL.md) に分離**。本スキルは「what（manifest + templates + 固有の取り込み/整合ロジック）」を担う設定スキル。
- **unified design / root manifest overlay は本スキルの前処理責務**。`run_resolved_engine.py` が immutable design docs、seed manifest、root `manifest.yaml` の per-project 値（`project` / `tech_stack` / `session` / `quality_gate_contract` / `domain_docs` / `code_review` / `github_pr` / `github_issue` / `coderabbit`）を合成した一時 skill-dir を作り、engine には解決済み入力だけを渡す。
- **session 管理（Layer 3）は親に内包**。`session-planning` / `session-handover` は本スキルの `outputs[]` から生成し、別の `agentic-session-management` スキルは不要。

### 構成ファイル

| ファイル | 役割 |
| --- | --- |
| `.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md` / `.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` | immutable upstream SoT。session handoff を含む基盤思想と本番運用知の上流入力 |
| `.cursor/skills/agentic-workflow-foundation/manifest.yaml` | スキル内 seed YAML（framework 要件 / handoff schema-default / outputs カタログ / `marker_id` / project / tech_stack の初期雛形） |
| `manifest.yaml` | スキル実行で生成されるリポジトリ直下の正式 project manifest（project 設定 / ACCD 採用・非採用 / tech_stack / session.verification） |
| `references/source-mapping.md` | manifest キー → 出力ファイル のトレーサビリティ |
| `references/design-conformance.md` | audit 判定の設計根拠 |
| `templates/*` | 出力ファイルのテンプレート |
| `templates/bin/*` | wrapper スクリプトのテンプレート。`github-pr-create-safe` / `_github-app-auth.sh` は基盤必須出力として常に生成。`github-pr-{reviews,comment,reply}-safe` は `code_review` 有効時のみ生成。`.cursorignore` で AI アクセス遮断 |
| `scripts/ingest_tech_stack.py` | techstack 設計書 §9 → root `manifest.yaml > tech_stack` 取り込み |
| `scripts/resolve_quality_gate.py` | root `manifest.yaml > tech_stack` → `project.quality_gate` / `quality_gate_contract` 決定（`G-GEN` 含む） |
| `scripts/check_tech_stack_conformance.py` | root `manifest.yaml > tech_stack` と、存在する場合の `package.json` の意味的整合チェック |
| `scripts/resolve_coderabbit.py` | root `manifest.yaml > tech_stack` → `coderabbit`（CodeRabbit 有効/無効ツール・path_instructions・path_filters）決定 |
| `scripts/resolve_domain_docs.py` | root `manifest.yaml > tech_stack` → `domain_docs`（Domain 層ドキュメント用の tech-stack 固有セクションリスト）決定 |
| `scripts/run_resolved_engine.py` | immutable design docs + seed manifest + root `manifest.yaml` の per-project 値から一時 resolved skill-dir を作り、engine を呼び出す stateless resolver。`bootstrap` サブコマンドで root `manifest.yaml` の `framework:` ブロックを seed から単一 SoT として生成/同期する |

> 生成エンジン（`generate.py` / `audit.py` / `genlib.py`）は本スキルには含まれず、[`agentic-workflow-engine`](../agentic-workflow-engine/SKILL.md) が提供する。engine は統一設計書や root `manifest.yaml` を直接読まず、渡された一時 skill-dir の `manifest.yaml + templates/` だけを決定論変換する。
> 依存: Python 3 標準ライブラリのみ（PyYAML 不要）。Hook 実行時は `jq` を推奨（未インストール時はフェイルオープン）。

## ワークフロー（6フェーズ）

Phase は番号順に実行する。「不要」と自己判断してスキップしない。

```text
- [ ] Phase 1: unified design resolver / manifest / templates のフレームワーク変更（必要時のみ。PO 確定事項は再質問しない）
- [ ] Phase 1.45: root manifest framework 同期（run_resolved_engine.py bootstrap。root 不在時は新規生成 / `framework.*` 変更時のみ再同期）
- [ ] Phase 1.5: init.yaml 適用（apply_kit_init.py。開発型固定 / name・slug 導出 / context_budget 適用）
- [ ] Phase 1.55: budget_thresholds 算出（resolve_budget_thresholds.py）
- [ ] Phase 1.6: techstack 取り込み（ingest_tech_stack.py）
- [ ] Phase 1.65: G-* / script contract 自動決定（resolve_quality_gate.py）
- [ ] Phase 1.66: CodeRabbit 設定自動決定（resolve_coderabbit.py）
- [ ] Phase 1.67: Domain 層ドキュメント変数自動決定（resolve_domain_docs.py）
- [ ] Phase 1.7: techstack 整合ゲート（check_tech_stack_conformance.py）
- [ ] Phase 2: 生成（generate.py）
- [ ] Phase 3: 監査ゲート（audit.py）
- [ ] Phase 4: 報告
```

### 対話と中断の原則（全フェーズ共通）

- **AskQuestion は1ステップ＝1論点ずつ提示する**。複数の確認事項を1回の `AskQuestion` にまとめない。
- **各 AskQuestion には推奨案を必ず1つ添える**。トレードオフを1〜2行で示し、判断を丸投げしない。
- **ステップが失敗・問題を検知したら、そのステップで中断する**。次フェーズへ進まず、検知内容・原因・影響範囲・推奨対応を PO に報告する。
- unified/bas は immutable input として読み取り、毎回 resolved skill-dir に fingerprint と構造化要件を展開する。永続 seed を更新する同期処理や、前回実行結果との stateful drift 照合は行わない。

### Phase 1: manifest / templates 更新（必要時のみ）

自己完結 SoT または stateless resolver を更新する必要がある場合だけ実行する。

1. 変更が unified design resolver / `framework.*` / `templates/*` / `outputs[]` / `session.*` など基盤定義に及ぶか確認する。
2. 設計判断に該当する場合は、PO 確定済み事項かを先に確認する。確定済みなら AskQuestion せず実装し、未確定なら `AskQuestion` で PO に1論点ずつ確認する。
3. `project.*` は Phase 1.5、`tech_stack.*` は Phase 1.6 で扱い、スキル実行で生成されるリポジトリ直下 `manifest.yaml` に保存する。Phase 1 では混ぜない。

#### PO 確定済みの stateless resolver 方針

以下は採用済みの前提であり、実装時に AskQuestion しない。

- 統一設計書を immutable upstream SoT とする。
- SKILL 内部では永続更新せず、一時 resolved manifest/templates を毎回生成して既存 engine に渡す。
- session handoff の本番運用知は統一設計書に構造化し、resolver が `framework.handoff.*` 相当に展開する。
- 入力が同じなら同じ resolved manifest/templates と同じ出力になることを最優先する。

> `docs/DECISIONS.md` はこの基盤を利用して実アプリを作るときの判断記録であり、本ツールキット内部の変更理由を必ず ADR 化する場所ではない。

### Phase 1.45: root manifest framework 同期（bootstrap）

root `manifest.yaml` の `framework:` ブロックは seed manifest を単一 SoT とする生成物である。生成に実際に使われる framework は seed 側であり（`run_resolved_engine.py > resolved_manifest` が seed.framework を基底にし、root からは `project` / `tech_stack` / `session` / `quality_gate_contract` / `framework.accd_axes` のみ overlay する）、root の framework は複製。手編集するとドリフト源になるため、`framework.*` を変更したら bootstrap で root へ同期する。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py bootstrap
```

- root `manifest.yaml` が**不在**なら、seed manifest をそのまま root へ新規生成する（`project.*` は Phase 1.5、`tech_stack` / `quality_gate` は Phase 1.6 / 1.65 で確定する placeholder のまま）。
- root が**存在**するなら、`framework:` ブロックだけを seed 由来に置換する。root のファイルヘッダ（「正式 project manifest」の framing）・`project.*` / `tech_stack` / `quality_gate*` / `session` の確定値は保持する。
- 冪等。`framework.*` 未変更なら「更新なし=冪等」を出力する。`framework:` ブロックを特定できない場合は exit 2。
- 実行順序: Phase 1（seed/templates 編集）→ **Phase 1.45（bootstrap で root へ同期）** → Phase 1.5（project 設定）→ **Phase 1.55（budget_thresholds 算出）** → Phase 1.6 以降（tech_stack / quality_gate 確定）→ Phase 2（generate）。

#### `AGENTS.md > Context Budget Protocol` 節の取り扱い

`AGENTS.md` には `## Context Budget Protocol` 独立節を持たせる。これは、複数の生成物（`docs/CONTEXT_BUDGET.md` / `.cursor/hooks/README.md` / `session-budget-evaluator.sh` / `session-bootstrap.sh` / `framework.handoff.references`）が `AGENTS.md > Context Budget Protocol` を参照しているのに、実体の `AGENTS.md` には独立節がなく Layer 1 のアンカーが欠けている drift を解消するためである。

**名称の位置づけ（断定の根拠を必ず書く）**:

- `Context Budget Protocol` は統一設計書（`AI_AGENT_UNIFIED_DESIGN.md` / `AI_BUSINESS_AGENT_SUITE.md`）の正式見出しではなく、複数の上流概念を本基盤向けに束ねた **foundation 側の運用名** である。節本文にこの旨を明記し、上流に存在しない用語が無根拠に増えたと誤解されないようにする。
- 上流の根拠概念は以下に対応づける。
  - `AI_AGENT_UNIFIED_DESIGN.md`: 「追跡ドキュメント / 検証ゲート / 再開プロトコル」の3要素、原則4「コンテキストの即時外部化」、原則5「コンテキスト保護」、原則6「コンテキストコストの管理」、および `stop` / `preCompact` / `sessionStart` Hook。
  - `AI_BUSINESS_AGENT_SUITE.md`: ACCD 軸 A「制約の補完」（容量上限・揮発性・断崖性への対処）、軸 D「段階的圧縮」、Context Loading、Handover、Context/Session/State SoT。

**`AGENTS.md > Context Budget Protocol` 節が満たすべき最低要件**:

- **目的**: LLM のコンテキストウィンドウは有限かつ揮発的であり、長時間セッションでは判断・進捗・制約が文脈から落ちる。これを防ぐため作業状態を外部化し、新規チャットで再構築する旨を書く。
- **根拠**: 上記の統一設計書概念から派生した運用名であることを1行で示す。
- **発火条件**: `framework.budget_thresholds` の `prompt_count` / `shell_bytes` を proxy 指標とし、OR 判定で Yellow / Red を判定する旨を書く。
- **AI の行動**: Yellow では追跡ドキュメントの「次セッションTODO / 追加調査が必要な項目」を更新し区切りを準備する。Red では `framework.handoff.active_manifest_path`（`.cursor/.session/handoff-{session_id}.md`）に handoff manifest を書き出し、同セッションで新規実装を続けず新規チャットへ誘導する。
- **詳細委譲**: 詳細手順・閾値・失敗モードは `docs/CONTEXT_BUDGET.md` を SoT とし、Hook 技術詳細は `.cursor/hooks/README.md` を参照する旨を書く（AGENTS には短い規範のみ置き、内容を二重管理しない）。

> 重複防止: この節は新規 Meta doc（例: `docs/CONTEXT_BUDGET_PROTOCOL.md`）として切り出さない。詳細 doc の役割は既に `docs/CONTEXT_BUDGET.md` が担っており、`AGENTS.md` には Layer 1 の短い入口だけを置く方針とする。

#### `01-critical-constraints.mdc` の出力仕様

**評価根拠**: 評価レポート §3.4（89点）— A2 重複行 / A3 空行不足 / B2 整合性 / B4 フォーマット

**`01-critical-constraints.mdc` テンプレートが満たすべき最低要件**:

- **重複排除（SoT 一元化）**: `project.boundaries.always` のうち「ファイル操作」セクション（ハードコード）と意味が重複する項目を、テンプレートの `仕様確認` セクションに展開しない。重複排除は `manifest.yaml` から対象項目を除外し、`AGENTS.md` テンプレートの Boundaries Always にはハードコードで維持する方法を取る。根拠: 同一制約が `ファイル操作` と `仕様確認` の2箇所に異なる表現で存在すると、AI が矛盾と解釈するリスクがある。
- **Markdown セクション境界**: 各 `##` 見出しの直前には空行を1行入れ、セクション境界を視覚的に明確にする。

#### `.cursor/hooks/README.md` の出力仕様

**評価根拠**: 評価レポート §3.7（89点）— A2 リンク集/チェックリスト/統合確認なし / B1 人間可読表記/挙動説明なし / B3 共通テスト/統合確認なし / B4 運用ガイドとしてコンパクトすぎ

**`.cursor/hooks/README.md` テンプレートが満たすべき最低要件**:

- **しきい値テーブルの人間可読表記**: `shell_bytes` 列に加え、`shell (可読)` 列を追加する。値は `resolve_budget_thresholds.py` が `shell_bytes_label`（1024 基数 KiB/MiB）として manifest に書き込み、テンプレートは `{{framework.budget_thresholds.*.shell_bytes_label}}` で展開する。バイト数だけでは運用者が直感的に把握できない。
- **Yellow / Red 到達時の挙動**: 各レベルの通知メッセージ（`[CONTEXT_BUDGET=YELLOW]` / `[CONTEXT_BUDGET=RED]`）と AI が取るべきアクションをテーブルで明記する。`last_warning_level` による重複通知抑止（`none` → `yellow` → `red` の昇格時のみ通知）も説明する。
- **Hook 追加チェックリスト**: 新規 Hook 追加時に確認すべき項目をチェックリスト形式で記載する。最低限の項目: hooks.json 登録 / 実行ビット付与 / フェイル戦略決定 + README 一覧表追記 / テストケース追加 / `manifest.yaml > outputs[]` 追加 / Cursor Settings 確認 / 再生成 + audit PASS。
- **Cursor 統合確認**: Cursor Settings > Features > Hooks での有効化確認手順を記載する。
- **関連ドキュメントリンク集**: `AGENTS.md > Context Budget Protocol` / `docs/QUALITY_GATE.md §2.1` / `docs/CONTEXT_BUDGET.md` / `docs/DECISIONS.md` / `.cursor/hooks.json` へのリンクテーブルを設ける。

#### `session-planning/SKILL.md` の出力仕様

**`session-planning/SKILL.md` テンプレートが満たすべき最低要件**:

- **開発型固定の宣言**: `workflow_pattern` は `"開発型"` 固定であり、パターン選択フローは不要であることを明記する。
- **新キャンペーン開始フロー**: 追跡ドキュメントが存在しない場合に新キャンペーンと判断し、追跡ドキュメントを新規作成して `framework.plan_required_sections` の必須セクションをすべて設ける。

### Phase 1.5: init.yaml 適用（apply_kit_init.py）

`init.yaml`（リポジトリ直下の初期入力 SoT）を読み込み、root `manifest.yaml` の `project.*` と `context_budget` を適用する。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/apply_kit_init.py
```

**`init.yaml` の役割**:

- 配置: リポジトリ直下 `init.yaml`。kit 導入時から存在し、初回スキル実行前に PO が設定する。
- 生成物ではない。`outputs[]` に含めず、generator は作成・上書きしない。
- SoT 境界: `project.name` と `context_budget.min_context_window_tokens` のみ。`framework` / `tech_stack` / `quality_gate*` / feature フラグは書かない。

**apply が書くもの**:

1. `project.name`（`init.yaml` の値。null / 省略時はリポジトリのディレクトリ名から導出）
2. `project.slug`（name から自動導出）
3. `project.workflow_pattern: "開発型"`（固定）
4. `project.context_budget.min_context_window_tokens`

**apply が書かないもの**: `framework.accd_axes`（seed/bootstrap 固定値）、feature フラグ一式（`code_review` / `github_pr` / `github_issue` / `coderabbit` / `agent_workflow` / `cross_repo_knowledge` / `deep_thinking` 等）、`tech_stack`、`quality_gate*`、固定説明文（`one_liner` / `agent_role` / `priorities` / `boundaries` / `doc_navigation`）。

feature を変えたい場合は、init 後に root `manifest.yaml` を直接編集して再生成する。

**バリデーション**:

- `init.yaml` 不在時は exit 2（必須初期設定の欠落）
- `version` は `1` 必須
- `project.workflow_pattern` / `features` / `deep_thinking` / `cross_repo_knowledge` キーが `init.yaml` にあれば exit 2（禁止キー）
- `project.name` は文字列または null（空文字 / 非 string は exit 2）
- `context_budget.min_context_window_tokens` は正の整数かつ 50000 以上（省略時 200000）
- 未知キーは exit 2
- apply 後に所有キーに `"開発型"` 以外の `workflow_pattern` や `[要確認]` が残存なら exit 1

**冪等性**: `init.yaml` が不変なら再 apply しても root manifest は変化しない。

### Phase 1.55: budget_thresholds 算出（resolve_budget_thresholds.py）

Phase 1.5 で確定した `project.context_budget.min_context_window_tokens` から `framework.budget_thresholds` を決定論的に算出し、root `manifest.yaml` に書き込む。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_budget_thresholds.py
```

- `project.context_budget` が未設定の場合は WARN（exit 1）で seed default（200K tier）にフォールバックする。
- bootstrap（Phase 1.45）が seed から同期した `framework.budget_thresholds` を上書きするため、最終値は resolver 由来になる。
- `--check` フラグで dry-run（書き込みなし）を実行可能。
- exit 2 は致命的エラー（manifest 破損等）。

### Phase 1.6: techstack 取り込み

`.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` がある場合、§9 の技術スタック表を生成済みのリポジトリ直下 `manifest.yaml > tech_stack` に取り込む。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/ingest_tech_stack.py
```

- 設計書が無い場合は WARN でスキップし、既存 root `manifest.yaml > tech_stack` を維持する。
- 生成前の `docs/tech-stack.md` は存在しなくてよい。ここで更新するのは生成元データ root `manifest.yaml > tech_stack`。
- seed manifest には具体スタックを焼き込まない。プロジェクトへ設置される具体値は、この Phase の入力（techstack 設計書）から決まる。

### Phase 1.65: G-* / script contract 自動決定

root `manifest.yaml > tech_stack` から、開発型の `G-GEN` / `G-BUILD` / `G-LINT` / `G-TEST` と package script contract を決定論的に導出する。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_quality_gate.py
```

- Phase 1.65 の責務は実 script の検出ではなく contract の決定である。`package.json` の有無に依存せず、実 script の検出や優先採用は行わない。
- 開発型 Web スタック（pnpm / Next.js / Hono / TypeScript / Cloudflare Workers / OpenAPI / Redocly / Spectral / Vitest）では、backend command を `pnpm run gen` / `build` / `lint` / `test` に一意決定する。公開コマンドは `bin/quality-gate <subcmd>` に統一される（ADR-0001）。
- `G-GEN` は開発中の OpenAPI bundle / 型・client 生成 / 生成物差分チェックを担い、`G-BUILD` は生成済み成果物を前提にデプロイ直前やローカル実行直前の build を担う。
- root `manifest.yaml > quality_gate_contract` へ、`package.json` scripts が満たすべき gen / build / lint / test の内訳（contract）を書き込む。
- `session.verification.gate_command` は標準検証として build / lint / test のみを含め、`G-GEN` は OpenAPI 定義や生成設定を変更した開発中に個別実行する。
- exit 0 → 決定済みまたは対象外として継続可。WARN があれば報告する。
- exit 2 → manifest 破損など致命的エラー。中断する。

### Phase 1.66: CodeRabbit 設定自動決定

**発火条件**: `coderabbit.enabled: true` の場合のみ実行する。`coderabbit.enabled: false`（Phase 1.5 で No を選択）の場合はスキップし、`.coderabbit.yaml` は Phase 2 でも生成されない（`feature: coderabbit` による条件生成）。

本フェーズは **AI ステップ（path_instructions 生成）** と **スクリプトステップ（ツール・フィルタ決定）** の 2 段階で構成される。

#### Step 1: スクリプトステップ（決定論的）

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_coderabbit.py
```

- `tech_stack.items` のテクノロジー名をカテゴリ分類（TypeScript / React / Workers / OpenAPI / Python / Go 等）し、各カテゴリに紐づく CodeRabbit ツールの有効/無効を決定する。
- path_filters はロックファイル・生成物・一時ファイルの除外パターンを生成する（pnpm 検出時は `pnpm-lock.yaml` も除外）。
- `path_instructions` は manifest の既存値をパススルーする（スクリプトは生成しない）。
- `_tech_stack_hash` を計算し manifest に書き込む。hash が前回と異なる場合は `[ACTION]` で AI 再生成を促す。
- スクリプトは既存の `coderabbit.enabled` 値を保持したまま、tech_stack 由来のツール・フィルタのみを更新する。
- 出力は root `manifest.yaml > coderabbit` セクションに書き込む。Phase 2 でテンプレートから `.coderabbit.yaml` が生成される。
- exit 0 → 決定済みとして継続可。
- exit 2 → manifest 破損など致命的エラー。中断する。

#### Step 2: AI ステップ（path_instructions 生成 — 条件付き）

**発火条件**: スクリプトが `[ACTION] path_instructions の AI 再生成が必要です` を出力した場合のみ実行する。hash 一致時（`更新なし=冪等`）はスキップする。

1. `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` と root `manifest.yaml > tech_stack.items` を読む。
2. 以下の観点で path_instructions を生成する:
   - 検出された各テクノロジーカテゴリに対応するファイルパターンとレビュー指示
   - テクノロジー間の組み合わせ（例: React + Workers → OpenNext 整合性確認）
   - Agentic Workflow 基盤ファイル（`.cursor/skills/**` / `.cursor/rules/**` / `.cursor/hooks/**` / `docs/**` / `manifest.yaml` / `.github/workflows/**`）の固定レビュー指示
3. 生成した path_instructions を root `manifest.yaml > coderabbit.path_instructions` に書き込む。
4. 書き込み後、Step 1 のスクリプトを再実行して hash が一致し `更新なし=冪等` になることを確認する。

**冪等性保証（パターン B）**: path_instructions は manifest に永続化される。`tech_stack.items` が変更されない限りスクリプトは既存値をパススルーし、AI ステップは発火しない。tech_stack 変更時のみ AI 再生成が走り、新しい hash で安定する。

### Phase 1.67: Domain 層ドキュメント変数自動決定

root `manifest.yaml > tech_stack` から、Domain 層ドキュメント（spec.md / architecture.md / api.md / data-models.md / coding-standards.md / workflows.md）のテンプレートで使用する変数（`domain_docs.*`）を決定論的に導出する。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/resolve_domain_docs.py
```

- `tech_stack.items` の `layer` / `technology` フィールドを分析し、主要言語・API スタイル・DB・フレームワーク・テストフレームワーク・パッケージマネージャを検出する。
- 検出結果に基づき、各ドキュメントの tech-stack 固有セクションリスト（`spec_sections` / `architecture_sections` / `api_sections` / `data_model_sections` / `coding_standards_sections` / `workflow_sections`）を組み立てる。
- テンプレート DSL の `#if` 制約を回避し、resolve スクリプト側で条件分岐を解決する。テンプレートは `{{#each domain_docs.xxx_sections}}` でセクションを展開する。
- root `manifest.yaml > domain_docs` へ書き込む。`run_resolved_engine.py` の `ROOT_OVERLAY_KEYS` に `domain_docs` が含まれており、resolved manifest に overlay される。
- exit 0 → 決定済みとして継続可。
- exit 2 → manifest 破損など致命的エラー。中断する。

### Phase 1.7: techstack 整合ゲート

root `manifest.yaml > tech_stack`（policy）を確認する。本ゲートの責務は policy↔reality の照合であり、reality 側の `package.json` が存在しない場合は照合対象が無いものとして fail-open する（不在は違反ではなく対象外）。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/check_tech_stack_conformance.py
```

- exit 0 → PASS。WARN があっても生成へ進める。
- exit 1 → 不採用ライブラリや major policy 違反などの意味的違反。PO に報告して中断する。
- exit 2 → manifest 破損など致命的エラー。中断する。

### Phase 2: 生成

基盤一式と session 系3スキルを、immutable design docs、スキル内 seed、**リポジトリ直下 manifest.yaml** の per-project 値を重ねた一時 resolved manifest を正として生成する。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py generate
```

- `run_resolved_engine.py` は `.cursor/skills/` 配下に一時 resolved skill-dir を作り、統一設計書メタデータと root `manifest.yaml` の `project` / `framework.accd_axes` / `tech_stack` / `session` / `quality_gate_contract` / `code_review` / `github_pr` / `github_issue` / `coderabbit` を seed manifest へ overlay してから engine を呼ぶ。終了時に一時ディレクトリは削除する。
- engine は統一設計書や root `manifest.yaml` を直接読まない。unified design / root manifest overlay は foundation 固有の入力解決であり、engine の How 境界へ混ぜない。
- manifest + templates から全出力ファイルを生成/上書きする（冪等）。生成ファイルの評価は PO が行う。
- `.gitignore` / `.cursorignore` はマーカーブロックを upsert（既存内容は保持。`marker_id: agentic-foundation`）。
- Hook スクリプトと `session-handover/scripts/verification-gate.sh` には実行ビットを付与する。
- `bin/github-pr-create-safe` / `bin/_github-app-auth.sh` は基盤の**必須出力**として常に `bin/` に生成し実行ビットを付与する（ADR-0001）。`code_review.enabled` が `true` の場合は追加で `bin/github-pr-{reviews,comment,reply}-safe` も生成する。`.cursorignore` のマーカーブロックに `bin/` を含めて AI アクセスを遮断する。GitHub App が未設定の場合、wrapper は exit 2（致命的エラー）で終了する。
- `session-planning` / `session-handover` は本スキルの `templates/skills/*` から生成する。別スキルの orchestration は行わない。

### Phase 3: 監査ゲート

resolved manifest で親 skill-dir 相当の出力だけを監査する。session 系出力も親 `outputs[]` に含まれる。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py audit
```

- exit 0 → 冪等性 + required sections OK（`[要確認]` は WARN 表示だが PASS）。
- exit 1 → drift / 必須要件欠落 / ファイル不在。原因を特定し Phase 2 から再生成して修正する。
- exit 2 → テンプレート不在 / manifest 破損。中断してユーザーに報告する。

冪等性の最終確認は次でも確認できる。

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py check
```

### Phase 4: 報告

以下を報告する。

- Phase 1.6 / 1.7 の結果（techstack 取り込み・整合ゲート）
- Phase 1.65 の結果（G-GEN を含む G-* / script contract 自動決定）
- 生成/更新した出力ファイル一覧（generate.py の出力）
- audit.py の結果（PASS / FAIL）
- Phase 1.5 で確定した `project.*` 値一覧と `framework.accd_axes` の採用/非採用一覧
- 実行できなかったゲートがあれば理由

## 重要な制約

- **出力ファイルを直接編集しない**。変更は必ず immutable upstream docs / seed `manifest.yaml` / 生成済み root `manifest.yaml` / `templates/` / stateless resolver を編集して再生成する。
- **root `manifest.yaml` の `framework:` ブロックを手編集しない**。framework の SoT は seed `manifest.yaml` であり、root へは Phase 1.45 の `run_resolved_engine.py bootstrap` で同期する。ただし `framework.budget_thresholds` は Phase 1.55 の `resolve_budget_thresholds.py` が `project.context_budget.min_context_window_tokens` から算出して上書きする（唯一の例外）。root を直接書き換えてよいのは Phase 1.5/1.55/1.6/1.65 が扱う `project.*` / `framework.budget_thresholds`（resolver 経由）/ `tech_stack` / `quality_gate*` / `session` の per-project 値（およびスクリプトによる自動反映）に限る。
- **unified/bas は immutable 実行時入力として扱う**。読み取り専用で、スキル内部に前回実行状態を保存しない。seed manifest/templates を実行結果で永続更新しない。
- **techstack は root `manifest.yaml > tech_stack` へ取り込んでから生成する**。生成物 `docs/tech-stack.md` を事前入力として扱わない。
- **unified design / root manifest overlay は foundation 側の `run_resolved_engine.py` で行う**。engine に foundation 固有の upstream / per-project 解決ロジックを追加しない。
- **`project.*` は AskQuestion / 自動導出 / 固定値の3分類で確定し、`framework.accd_axes` は自動導出で確定する**。`framework.accd_axes` は開発型 / パイプライン型 / ドキュメント型では軽量実装を自動導出し、ACCD 軸ごとの AskQuestion は行わない。未確定で残った `[要確認]` は audit が WARN 扱い。
- **`quality_gate` は `workflow_pattern` × `tech_stack` から導出する**。導出の責務は backend command（tech stack 依存）の決定であり、`package.json` の有無に依存しない。公開入口は `bin/quality-gate`（ADR-0001）。OpenAPI 由来の生成は `G-GEN`、実行/デプロイ前 build は `G-BUILD` として分離する。
- **wrapper スクリプト（`bin/`）は生成物であり直接編集しない**。変更は `templates/bin/*.template` を編集して再生成する。`.cursorignore` により AI のコンテキストから除外されるが、`templates/bin/` は除外対象外であり SoT として編集可能。`bin/github-pr-create-safe` と `bin/_github-app-auth.sh` は基盤の**必須出力**であり、GitHub App のセットアップが foundation kit の前提要件となる（ADR-0001）。GitHub App 未設定時は wrapper が exit 2（致命的エラー）で終了する設計とし、今後 git 操作に関する skill が追加される場合も同様に wrapper + GitHub App 経由を前提とする。
- 既存の `.gitignore` / `.cursorignore` の他の行を消さない（マーカーブロックのみ管理）。
- 不要になった `agentic-session-management` は再作成しない。session 系出力は生成済み root manifest から生成する。
- **`AGENTS.md` 出力仕様の変更（例: `Context Budget Protocol` 節の追加）は、本来 `templates/AGENTS.md.template` と、必要なら `manifest.yaml` / `references/design-conformance.md` を更新して再生成する対象である**。ただし PO が明示的に「`SKILL.md` 内部のみの修正」を指定した場合は、生成物（`AGENTS.md` / `templates/*` / `manifest.yaml`）を変更せず、要件と手順の文書化だけに留める。その場合 `SKILL.md` の記述と実出力の間に一時的な乖離が残ることを許容し、後続の再生成タスクで解消する。

## スコープ外

- **生成/監査エンジン `agentic-workflow-engine` 自体の生成**。エンジン（How）は独立スキルで、本スキルは `--skill-dir` 付きで呼び出すだけ。
- プロジェクト固有の業務仕様 docs（`docs/spec.md` / `docs/api.md` / curated 目次等）の生成。
- feature 単位の Design Doc 作成。
- unified/bas への永続同期、前回実行結果を前提にした stateful drift 追跡。
