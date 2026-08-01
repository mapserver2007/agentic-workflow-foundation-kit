---
name: agentic-workflow-engine
description: >-
  Agentic Workflow 基盤の「生成/監査エンジン（How）」。設定スキル（`agentic-workflow-foundation` 等）の
  `manifest.yaml` + `templates/` から出力ファイルを
  100% 決定論的に生成（`generate.py`）し、冪等性と必須要件を監査（`audit.py`）する。
  共有ライブラリ `genlib.py`（標準ライブラリのみの最小 YAML ローダ / ハッシュ / パス解決 /
  テンプレート描画）を提供する。設定スキルから `--skill-dir` 付きでシェル起動される
  決定論ツールであり、モデルが自律的に発動するスキルではない（`disable-model-invocation: true`）。
  本スキルは「How（生成機構）」専任で、「What（自己完結 SoT の設定 = manifest + templates）」は設定スキル側が持つ。
  Deterministic generation/audit engine for the agentic workflow foundation toolchain.
disable-model-invocation: true
---

# agentic-workflow-engine

Agentic Workflow 基盤の **生成/監査エンジン（How）** を提供する独立スキル。設定スキル（What）が持つ `manifest.yaml`（YAML 正本）と `templates/` から、出力ファイル群を **100% 決定論的**に生成・監査する。

> **位置づけ（重要）**: 本スキルは **ツール（How エンジン）** であり、設定スキルの**自己完結 SoT（`manifest` + `templates`）を入力に取る決定論変換器**である。本スキルの正本は**エンジン自身の工学仕様 / コード**であって設定スキルの内容ではない。したがって `agentic-workflow-foundation` の `outputs` の対象外（固定部品として足場配布）で、セットアップ時に配置される。詳細は [`agentic-workflow-foundation` のアーキテクチャ節](../agentic-workflow-foundation/SKILL.md)を参照。

## なぜ独立スキルか（設定スキルに畳み込まない理由）

- **設定スキルと独立して共有される**。`agentic-workflow-foundation` は `generate.py` / `audit.py` を `--skill-dir` 付きで実行し、さらに `agentic-workflow-foundation/scripts/`（`ingest_tech_stack.py` / `check_tech_stack_conformance.py`）は `genlib` をスキル境界を越えて import する。エンジンを設定スキルに埋め込むと、設定スキルが自分の内部ツールを生成・監査する循環結合（reach-in / bootstrap 問題）になる。
- **What / How の分離**。設定スキルは「自己完結 SoT（manifest + templates）」を担い、本スキルは「決定論変換の機構」を担う。境界を保つことでエンジンの進化（新出力モード・条件分岐描画など）を設定スキルの編集と独立に管理できる。
- **bootstrap（鶏と卵）の回避**。エンジンは「正本 → 出力」変換を*実行する主体*であり、自分自身を自分で生成することはできない。よって設定スキルの生成出力には置けず、独立した足場部品として供給する。

## 構成（scripts/）

| ファイル | 役割 |
| --- | --- |
| `scripts/genlib.py` | 共有ライブラリ。最小 YAML ローダ（`load_manifest`）/ `sha256_file` / `skill_dir_of` / `root_from_skill_dir` / `deep_merge` / `apply_inherited_project`（project 継承）/ `YamlError` / テンプレート描画ヘルパ。`generate.py` と `audit.py` が同一描画ロジックを共有するための土台。 |
| `scripts/generate.py` | `--skill-dir <dir>` の `manifest.yaml` + `templates/` から `outputs[]` を生成。モードは `render`（ファイル全体）/ `marker`（`.gitignore` 等のマーカーブロック upsert）/ `seed`（不在時のみ初期生成・存在時は不可侵）。`--check` で冪等性ドライラン。`executable: true` の出力には実行ビット付与。 |
| `scripts/audit.py` | `--skill-dir <dir>` を監査。(1) 冪等性（出力 == 再生成結果、差分があれば直接編集とみなす）、(2) `outputs[].required_sections` の充足を検査し、exit code を返す。 |

> 依存: **Python 3.9 以上（標準ライブラリのみ、PyYAML 不要）**。`manifest.yaml` は次の最小 YAML サブセットで記述する: block style のみ（flow `{}` / `[]` 不可）/ インデント半角スペース2 / スカラは 裸・`"…"`・`'…'`・整数・真偽値 / マッピング・シーケンス（`- item` / `- key: value`）/ 行頭・行中 `#` コメント。**複数行ブロックスカラ（`|` / `>`）は非対応**（現行 manifest は不使用）。

> 実装メモ: `scripts/genlib.py` / `generate.py` / `audit.py` は本スキルのデリバリ（ツール本体＝正本）。生成物ではないため改修時は直接編集してよい（設定スキルの生成出力ではない）。`agentic-workflow-foundation/scripts/`（`ingest_tech_stack.py` / `check_tech_stack_conformance.py`）はスキル境界を越えて `genlib` を import するため、本スクリプト群は同梱前提とする。

## project 継承（`inherits_project`）

設定スキルの `manifest.yaml` トップレベルに `inherits_project: <親設定スキルのルート相対パス>` を置くと、`generate.py` / `audit.py` はロード直後に親 manifest の `project` を子 `project` へ **deep-merge（子優先）** してから描画/監査する（`genlib.apply_inherited_project`）。

- 共有 SoT は親（例: `agentic-workflow-foundation`）の `project.*`。子は差分のみを `project` に書けばよく、未指定キーは親値を継承する。
- dict は再帰マージ、スカラ/リストは子値で置換。`inherits_project` がなければ無変換（後方互換）。
- 親 manifest が読めない場合は `YamlError` → exit 2。
- 互換機能として残す。子設定スキルを追加した場合、その `audit.py` は継承解決後の `project` を検査する。

## テンプレート構文（`genlib.render`）

`templates/` のファイルは以下の最小 DSL で記述する。**置換対象は二重括弧 `{{ … }}` のみ**で、bash の `${…}` や JSON の単一 `{ }` は温存される。

| 構文 | 意味 |
| --- | --- |
| `{{ dotted.path }}` | `manifest.yaml` 上のスカラ（`project.*` / `framework.*`）を文字列展開。未解決パスは `RenderError`（= audit/generate が exit 2） |
| `{{#each dotted.path}} … {{/each}}` | リストを反復描画（**ネスト不可**）。対象が非リストなら `RenderError` |
| `{{this}}` | `#each` 本体内で現在のスカラ要素 |
| `{{this.field}}` | `#each` 本体内でマップ要素のフィールド（ドット可） |
| `{{@index}}` | `#each` 本体内の **1 始まり**連番（人間可読の番号付きリスト用） |

- **standalone 改行制御**: `{{#each}}` / `{{/each}}` がその行で単独（前後が空白のみ）の場合、その行の空白と改行を畳む（Handlebars 互換）。`{{/each}}- 次の項目` のように同一行に後続テキストがある場合は畳まない。これによりテンプレート作者が意図した空行数で出力される。

## 使い方（設定スキルから呼ばれる）

```bash
# 生成（親 → 子の順で設定スキルごとに実行）
python3 .cursor/skills/agentic-workflow-engine/scripts/generate.py --skill-dir <config-skill-dir>

# 冪等性ドライラン
python3 .cursor/skills/agentic-workflow-engine/scripts/generate.py --skill-dir <config-skill-dir> --check

# 監査（冪等性 + 必須要件）
python3 .cursor/skills/agentic-workflow-engine/scripts/audit.py --skill-dir <config-skill-dir>
```

## exit code（QUALITY_GATE 3段階に準拠）

| code | 意味 |
| --- | --- |
| 0 | 冪等性 OK + 必須要件充足（`project.*` の `[要確認]` 残存は WARN だが PASS） |
| 1 | drift（出力の直接編集）/ 必須要件欠落 / 出力ファイル不在 |
| 2 | 致命的エラー（テンプレート不在 / `manifest.yaml` 破損） |

## スコープ外

- 各設定スキルの `manifest.yaml` / `templates/` の**内容**（What）。本エンジンはそれらを入力として受け取るだけで、定義しない。
- 設定スキル固有のロジック（例 `agentic-workflow-foundation` の tech_stack 取り込み / 整合ゲート）は各設定スキル側に置く（本エンジンは `genlib` を提供するのみ）。
