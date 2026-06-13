---
name: agentic-workflow-foundation
description: >-
  統一設計書を immutable upstream SoT として読み、スキル内 seed
  manifest + templates + root manifest から一時 resolved skill-dir を
  stateless に作成して Python generator に渡し、
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
       ├─ Phase 1.5: project 設定 + ACCD 採用/非採用 確定 → root manifest.yaml 生成
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
- **リポジトリ直下 `manifest.yaml` は本スキル実行で生成される正式 project manifest**。`project.*` / `framework.accd_axes` / `tech_stack.*` / `session.verification.*` は生成後の root manifest で PO が評価する。
- **techstack は per-project パラメータ**。配布時点の seed manifest には具体スタックを焼き込まず、`ingest_tech_stack.py` が `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` を読んで生成済み root `manifest.yaml` を更新する。`resolve_quality_gate.py` はこの `tech_stack` だけから root scripts の canonical G-* を決める。
- **生成/監査エンジン（how）は独立スキル [`agentic-workflow-engine`](../agentic-workflow-engine/SKILL.md) に分離**。本スキルは「what（manifest + templates + 固有の取り込み/整合ロジック）」を担う設定スキル。
- **unified design / root manifest overlay は本スキルの前処理責務**。`run_resolved_engine.py` が immutable design docs、seed manifest、root `manifest.yaml` の per-project 値を合成した一時 skill-dir を作り、engine には解決済み入力だけを渡す。
- **session 管理（Layer 3）は親に内包**。`session-planning` / `session-handover` / `decisions-record` は本スキルの `outputs[]` から生成し、別の `agentic-session-management` スキルは不要。

### 構成ファイル

| ファイル | 役割 |
| --- | --- |
| `.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md` / `.cursor/docs/AI_BUSINESS_AGENT_SUITE.md` | immutable upstream SoT。session handoff を含む基盤思想と本番運用知の上流入力 |
| `.cursor/skills/agentic-workflow-foundation/manifest.yaml` | スキル内 seed YAML（framework 要件 / handoff schema-default / outputs カタログ / `marker_id` / project / tech_stack の初期雛形） |
| `manifest.yaml` | スキル実行で生成されるリポジトリ直下の正式 project manifest（project 設定 / ACCD 採用・非採用 / tech_stack / session.verification） |
| `references/source-mapping.md` | manifest キー → 出力ファイル のトレーサビリティ |
| `references/design-conformance.md` | audit 判定の設計根拠 |
| `templates/*` | 出力ファイルのテンプレート |
| `scripts/ingest_tech_stack.py` | techstack 設計書 §9 → root `manifest.yaml > tech_stack` 取り込み |
| `scripts/resolve_quality_gate.py` | root `manifest.yaml > tech_stack` → `project.quality_gate` / `quality_gate_contract` 決定（`G-GEN` 含む） |
| `scripts/check_tech_stack_conformance.py` | root `manifest.yaml > tech_stack` と、存在する場合の `package.json` の意味的整合チェック |
| `scripts/run_resolved_engine.py` | immutable design docs + seed manifest + root `manifest.yaml` の per-project 値から一時 resolved skill-dir を作り、engine を呼び出す stateless resolver |

> 生成エンジン（`generate.py` / `audit.py` / `genlib.py`）は本スキルには含まれず、[`agentic-workflow-engine`](../agentic-workflow-engine/SKILL.md) が提供する。engine は統一設計書や root `manifest.yaml` を直接読まず、渡された一時 skill-dir の `manifest.yaml + templates/` だけを決定論変換する。
> 依存: Python 3 標準ライブラリのみ（PyYAML 不要）。Hook 実行時は `jq` を推奨（未インストール時はフェイルオープン）。

## ワークフロー（6フェーズ）

Phase は番号順に実行する。「不要」と自己判断してスキップしない。

```text
- [ ] Phase 1: unified design resolver / manifest / templates のフレームワーク変更（必要時のみ。PO 確定事項は再質問しない）
- [ ] Phase 1.5: プロジェクト設定確定（AskQuestion / 自動導出 / 固定値）
- [ ] Phase 1.6: techstack 取り込み（ingest_tech_stack.py）
- [ ] Phase 1.65: G-* / script contract 自動決定（resolve_quality_gate.py）
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

### Phase 1.5: プロジェクト設定 / ACCD 対応確定（AskQuestion / 自動導出 / 固定値）

**発火条件**: `project.*` の必須フィールドに `[要確認]` が残っている場合。確定済みなら再質問せず Phase 1.6 へ進む。`framework.accd_axes` は開発型 / パイプライン型 / ドキュメント型の全てで軽量実装を自動採用するため、AskQuestion の発火条件にしない。

`project.*` は manifest への PO 直接手入力・自由入力を原則廃止し、**AskQuestion / 自動導出 / 固定値**で確定する。`framework.accd_axes` は開発型 / パイプライン型 / ドキュメント型では軽量実装へ自動導出する。

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
- `framework.accd_axes`: 開発型 / パイプライン型 / ドキュメント型では、BAS 固有の重い機構を丸移植せず、下表の軽量実装を自動採用する。
- `quality_gate.{gen,build,lint,test}_cmd`: Phase 1.65 で `workflow_pattern` × `tech_stack` から導出する。開発型 Web スタックでは root scripts（`pnpm run gen` / `pnpm run build` / `pnpm run lint` / `pnpm run test`）を canonical entrypoint とする。

| workflow_pattern | tracking_artifact |
| --- | --- |
| 開発型 | `plan.md` |
| パイプライン型 | `playbook.md` |
| ドキュメント型 | `session_plan.md` |

| ACCD 軸 | 自動採用する軽量実装 | 意図的に非採用とする BAS 固有の重い機構 |
| --- | --- | --- |
| A 制約の補完 | `AGENTS.md` 参照順序 / `.cursor/rules/*.mdc` / 追跡ドキュメント / handoff manifest | YAML 正本 + Markdown 生成 / Context Loading Table の機械検証 |
| B 専念の委譲 | 品質ゲート / `verification-gate.sh` / `guard-git-write.sh` | Finding Code 79 種体系 / Deterministic Guard の数値判定基盤 |
| C 認知的多様性 | `Task` subagent 並列探索 / 自己反論 / review スキル | engine / model resolver による異モデル強制 |
| D 段階的圧縮 | `templates required_sections` / `handoff-active.md` / Documentation Navigation / 追跡ドキュメント archive 境界 | 提案書 7 ステップパイプライン |
| E 自律的進化 | `GOTCHAS.md` / `DECISIONS.md` / Hook 昇格パス | 仮説シミュレーション全タスク必須化 |

> 重量型は、上記 3 workflow pattern ではなく、経営課題分析のように入力 / 出力のバリエーションが広く、複数 PO・仮説並列生成・異モデル批判・構造化状態管理が必要な「経営型」で検討する。本プロジェクトで軽量実装だけが選ばれるのは意図した設計であり、問題ではない。

**(3) 固定値**

- `one_liner` / `agent_role` / `priorities` / `boundaries.{always,ask_first,never_extra}` / `doc_navigation.domain[]`
- これらは本基盤の機能・運用制約を説明する固定値。コピー先リポジトリが変わっても不変。

**確定後**

- 確定値はすべて、スキル実行で生成されるリポジトリ直下 `manifest.yaml > project.*` に記入する。
- ACCD の自動確定値は、スキル実行で生成されるリポジトリ直下 `manifest.yaml > framework.accd_axes[].adopted` / `not_adopted` に記入する。
- 「複合型」になりそうな場合は、ワークスペース分離判断を PO に確認してから主パターンを確定する。

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

- `package.json` はこの時点では存在しない前提。実 script の検出や優先採用は行わない。
- 開発型 Web スタック（pnpm / Next.js / Hono / TypeScript / Cloudflare Workers / OpenAPI / Redocly / Spectral / Vitest）では、`G-GEN = pnpm run gen`、`G-BUILD = pnpm run build`、`G-LINT = pnpm run lint`、`G-TEST = pnpm run test` に一意決定する。
- `G-GEN` は開発中の OpenAPI bundle / 型・client 生成 / 生成物差分チェックを担い、`G-BUILD` は生成済み成果物を前提にデプロイ直前やローカル実行直前の build を担う。
- root `manifest.yaml > quality_gate_contract` へ、将来の `package.json` scripts が満たすべき gen / build / lint / test の内訳を書き込む。
- `session.verification.gate_command` は標準検証として build / lint / test のみを含め、`G-GEN` は OpenAPI 定義や生成設定を変更した開発中に個別実行する。
- exit 0 → 決定済みまたは対象外として継続可。WARN があれば報告する。
- exit 2 → manifest 破損など致命的エラー。中断する。

### Phase 1.7: techstack 整合ゲート

root `manifest.yaml > tech_stack`（policy）を確認する。`package.json` はこの時点では未生成のため、存在しない場合は正常な初期状態として fail-open する。

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

- `run_resolved_engine.py` は `.cursor/skills/` 配下に一時 resolved skill-dir を作り、統一設計書メタデータと root `manifest.yaml` の `project` / `framework.accd_axes` / `tech_stack` / `session` / `quality_gate_contract` を seed manifest へ overlay してから engine を呼ぶ。終了時に一時ディレクトリは削除する。
- engine は統一設計書や root `manifest.yaml` を直接読まない。unified design / root manifest overlay は foundation 固有の入力解決であり、engine の How 境界へ混ぜない。
- manifest + templates から全出力ファイルを生成/上書きする（冪等）。生成ファイルの評価は PO が行う。
- `.gitignore` / `.cursorignore` はマーカーブロックを upsert（既存内容は保持。`marker_id: agentic-foundation`）。
- Hook スクリプトと `session-handover/scripts/verification-gate.sh` には実行ビットを付与する。
- `session-planning` / `session-handover` / `decisions-record` は本スキルの `templates/skills/*` から生成する。別スキルの orchestration は行わない。

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
- **unified/bas は immutable 実行時入力として扱う**。読み取り専用で、スキル内部に前回実行状態を保存しない。seed manifest/templates を実行結果で永続更新しない。
- **techstack は root `manifest.yaml > tech_stack` へ取り込んでから生成する**。生成物 `docs/tech-stack.md` を事前入力として扱わない。
- **unified design / root manifest overlay は foundation 側の `run_resolved_engine.py` で行う**。engine に foundation 固有の upstream / per-project 解決ロジックを追加しない。
- **`project.*` は AskQuestion / 自動導出 / 固定値の3分類で確定し、`framework.accd_axes` は自動導出で確定する**。`framework.accd_axes` は開発型 / パイプライン型 / ドキュメント型では軽量実装を自動導出し、ACCD 軸ごとの AskQuestion は行わない。未確定で残った `[要確認]` は audit が WARN 扱い。
- **`quality_gate` は `workflow_pattern` × `tech_stack` から導出する**。`package.json` 未生成段階のため、実 script 検出ではなく canonical root scripts と script contract を決定する。OpenAPI 由来の生成は `G-GEN`、実行/デプロイ前 build は `G-BUILD` として分離する。
- 既存の `.gitignore` / `.cursorignore` の他の行を消さない（マーカーブロックのみ管理）。
- 不要になった `agentic-session-management` は再作成しない。session 系出力は生成済み root manifest から生成する。

## スコープ外

- **生成/監査エンジン `agentic-workflow-engine` 自体の生成**。エンジン（How）は独立スキルで、本スキルは `--skill-dir` 付きで呼び出すだけ。
- プロジェクト固有の業務仕様 docs（`docs/spec.md` / `docs/api.md` / curated 目次等）の生成。
- feature 単位の Design Doc 作成。
- unified/bas への永続同期、前回実行結果を前提にした stateful drift 追跡。

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
