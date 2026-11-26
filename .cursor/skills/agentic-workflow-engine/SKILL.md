---
name: agentic-workflow-engine
description: >-
  Agentic Workflow 基盤の「生成/監査エンジン（How）」。設定スキル（`agentic-workflow-foundation` 等）の
  `manifest.yaml` + `templates/` から出力ファイルを
  100% 決定論的に生成（`generate.py`）し、冪等性と必須要件を監査（`audit.py`）する。
  共有ライブラリ `genlib.py`（標準ライブラリのみの最小 YAML ローダ / ハッシュ / パス解決 /
  テンプレート描画）と、Markdown の正本を見出し単位で機械的に分割する `mode: split` の
  計算 `splitlib.py` を提供する。設定スキルから `--skill-dir` 付きでシェル起動される
  決定論ツールであり、モデルが自律的に発動するスキルではない（`disable-model-invocation: true`）。
  本スキルは「How（生成機構）」専任で、「What（自己完結 SoT の設定 = manifest + templates）」は設定スキル側が持つ。
  Deterministic generation/audit engine for the agentic workflow foundation toolchain.
disable-model-invocation: true
---

# agentic-workflow-engine

Agentic Workflow 基盤の **生成/監査エンジン（How）** を提供する独立スキル。設定スキル（What）が持つ `manifest.yaml`（YAML 正本）と `templates/` から、出力ファイル群を **100% 決定論的**に生成・監査する。

> **位置づけ（重要）**: 本スキルは **ツール（How エンジン）** であり、設定スキルの**自己完結 SoT（`manifest` + `templates`）を入力に取る決定論変換器**である。本スキルの正本は**エンジン自身の工学仕様 / コード**であって設定スキルの内容ではない。したがって `agentic-workflow-foundation` の `outputs` の対象外（固定部品として足場配布）で、セットアップ時に配置される。詳細は [`agentic-workflow-foundation` のアーキテクチャ節](../agentic-workflow-foundation/SKILL.md)を参照。

## なぜ独立スキルか（設定スキルに畳み込まない理由）

- **設定スキルと独立して共有される**。`agentic-workflow-foundation` は `generate.py` / `audit.py` を `--skill-dir` 付きで実行し、さらに `agentic-workflow-foundation/scripts/`（`tech_contract.py` / `check_tech_stack_conformance.py`）は `genlib` をスキル境界を越えて import する。エンジンを設定スキルに埋め込むと、設定スキルが自分の内部ツールを生成・監査する循環結合（reach-in / bootstrap 問題）になる。
- **What / How の分離**。設定スキルは「自己完結 SoT（manifest + templates）」を担い、本スキルは「決定論変換の機構」を担う。境界を保つことでエンジンの進化（新出力モード・条件分岐描画など）を設定スキルの編集と独立に管理できる。
- **bootstrap（鶏と卵）の回避**。エンジンは「正本 → 出力」変換を*実行する主体*であり、自分自身を自分で生成することはできない。よって設定スキルの生成出力には置けず、独立した足場部品として供給する。

## 構成（scripts/）

| ファイル | 役割 |
| --- | --- |
| `scripts/genlib.py` | 共有ライブラリ。最小 YAML ローダ（`load_manifest`）/ `sha256_file` / `skill_dir_of` / `root_from_skill_dir` / `deep_merge` / `apply_inherited_project`（project 継承）/ `YamlError` / テンプレート描画ヘルパ。`generate.py` と `audit.py` が同一描画ロジックを共有するための土台。 |
| `scripts/splitlib.py` | `mode: split` の分割と索引の計算。正本のテキストから、分割ファイル、索引の描画用データ（`_split`）、書式契約の違反・警告を決定論で返す（`build`）。`generate.py` と `audit.py` が同じ関数を呼ぶ。 |
| `scripts/generate.py` | `--skill-dir <dir>` の `manifest.yaml` + `templates/` から `outputs[]` を生成。モードは `render`（ファイル全体）/ `marker`（`.gitignore` 等のマーカーブロック upsert）/ `seed`（不在時のみ初期生成・存在時は不可侵）/ `split`（正本の分割ファイル群 + 索引。下記）。`--check` で冪等性ドライラン。`executable: true` の出力には実行ビット付与。 |
| `scripts/audit.py` | `--skill-dir <dir>` を監査。(1) 冪等性（出力 == 再生成結果、差分があれば直接編集とみなす）、(2) `outputs[].required_sections` の充足を検査し、exit code を返す。`mode: split` は、連結一致・残骸・サイズ上限・参照切れ・索引の網羅・プレースホルダの照合も検査する。`--skip-seed-required-sections` は consumer updater が適用対象外の既存 seed を存在のみ検査する場合に限る。 |

> 依存: **Python 3.9 以上（標準ライブラリのみ、PyYAML 不要）**。`manifest.yaml` は次の最小 YAML サブセットで記述する: block style のみ（flow `{}` / `[]` 不可）/ インデント半角スペース2 / スカラは 裸・`"…"`・`'…'`・整数・真偽値 / マッピング・シーケンス（`- item` / `- key: value`）/ 行頭・行中 `#` コメント。**複数行ブロックスカラ（`|` / `>`）は非対応**（現行 manifest は不使用）。

> 実装メモ: `scripts/genlib.py` / `splitlib.py` / `generate.py` / `audit.py` は本スキルのデリバリ（ツール本体＝正本）。生成物ではないため改修時は直接編集してよい（設定スキルの生成出力ではない）。`agentic-workflow-foundation/scripts/`（`tech_contract.py` / `check_tech_stack_conformance.py`）はスキル境界を越えて `genlib` を import するため、本スクリプト群は同梱前提とする。

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
- **値内のリテラル保護**: manifest 由来のスカラ値に `{{variable}}` や `{{#each}}` が含まれていても、後続の描画 pass ではテンプレート構文として再解釈せず、そのままリテラル出力する。テンプレート本体に直接書かれた未解決参照は従来どおり `RenderError` とする。

## `mode: split`（Markdown の正本を分割して出力する）

見出し構造を持つ Markdown の正本を、人や LLM の判断を挟まず、見出し単位に機械的に分割した**逐語ファイル群**と、その**索引**として出力する（エージェントが必要な節だけを読めるようにするため）。本文は逐語のままで、`{{...}}` も加工しない（`render` を通さない）。

### `outputs[]` のエントリ

```yaml
- path: docs/tech-stack/                  # 出力ディレクトリ（末尾 /、深さ2以上）。kit が専有する
  mode: split
  template: docs/tech-stack.md.template   # 索引のテンプレート（templates/ 配下）
  index_path: docs/tech-stack.md          # 索引の出力先（出力ディレクトリの外）
  source_dir: .cursor/docs                # 正本の置き場（root 相対）
  source_key: project.tech_stack_design_filename   # 正本のファイル名（basename の .md）を持つ manifest のキー
  max_bytes: 16384                        # 分割ファイルの本文サイズの上限（UTF-8 のバイト数。ヘッダ行を除く）
  min_bytes: 3200                         # 下限（これ未満の節は、隣の節と結合する）
  placeholder_check:                      # 任意。正本の `{{...}}` が、このファイルの節に存在するか照合する
    path: docs/architecture.md
    heading: 技術ブループリントの適用
  required_sections: ["..."]              # 索引に対して検査する（出力ディレクトリには適用しない）
```

1つの manifest に `mode: split` のエントリは1つまで。

### 分割アルゴリズム（構造だけで決める。節番号と内容に依存しない）

1. コードフェンスの外の見出しだけを解析する。番号ではなく見出しレベルを使う。frontmatter は本文に含めない。
2. 再帰的に分割する。節の合計サイズが上限以下なら、その節を1ファイルにする。上限を超えるなら、1段深い見出しで分ける。
3. 本文が下限未満の親節は、先頭の子に結合する。
4. 下限未満の小さな兄弟節は、隣の節と結合する（結合後が上限以下のときだけ）。
5. 末端節が1つで上限を超える場合は、途中で切らない。違反として報告し、`audit` が失敗にする。

### 出力

- 分割ファイル: `{連番}_{slug}.md`。slug は、ファイルの最初の番号付き節の番号を `.` から `-` にして先頭に `s` を付けたもの（例 `s3-4-2a`）。番号付き節がなければ `intro`。
- 各ファイルの先頭は、ヘッダ1行 `<!-- split NN/MM of <source> (generated; do not edit) -->` と空行1行。`audit` は連結時にこの2行を除く。
- 索引: `template` を、manifest の複製に一時キー `_split` を足して描画する（manifest は変更しない。永続化しない）。`_split` は、同じ実行内の**すべてのテンプレート**（`render` と `seed` と `marker` を含む）に渡される。たとえば seed のテンプレートが、正本のプレースホルダの記入欄を `_split.placeholders` から作れる（`{{#if _split.placeholders}}` で、`_split` が無い描画でも失敗しないようにする）。`_split` のキーは、`source`、`title`、`version`、`status`、`file_count`、`total_bytes`、`placeholders`、`placeholders_line`、`toc`（`num`、`title`、`file`、`refs`）、`tasks`（`name`、`starts`、`refs`、`files`）、`warnings`。`#each` はネストできないため、すべて平らなリストで渡す。
- 出力ディレクトリは kit が専有する。`generate` は、期待するファイル集合との過不足を直し（残骸ファイルを削除する）、内容が同じファイルには書き込まない。削除は出力ディレクトリ直下のファイルに限る。symlink と下位ディレクトリがある場合は、何も削除せず exit 2 にする。

### 正本が満たす書式契約（`audit` が検査する）

- 見出しは階層構造にする。H2 以下の見出しには、節番号を付ける（番号のない見出しは参照できず、警告になる）。
- 節番号は、見出しテキストの先頭の `\d+(\.\d+)*[a-z]?`（`3.4.2a` のような英字サフィックスを許す）。
- 節の参照は `§<番号>` の書式で書く。`§<番号>` は、その節と子の節すべてを指す。範囲指定（`§3.1〜§3.5`）は契約外で、警告になる。参照は、フェンスの中のコメントも含めて抽出する。
- 1つの末端節は、上限サイズ以内にする。
- 索引表を持つ。ヘッダ行の先頭2セルが `タスク種別` と `必読節` の Markdown 表で、列は `タスク種別 | 必読節 | 参照先` の3列。`必読節` は起点の節（人が書く）、`参照先` は起点の節の本文が `§` で直接指す節。「常時読む」は、1列目が `常時` の行に書く。索引表自身の中の `§` 参照は、参照先の算出から除く。

### `audit` の検査（`mode: split`）

1. 各分割ファイルと索引が、再生成結果と一致する（直接編集は drift）。
2. 分割ファイルをヘッダ行を除いて順に連結すると、正本の本文と一致する。
3. 出力ディレクトリに、残骸ファイルがない。
4. 各ファイルがサイズ上限を超えない（超える末端節は、ブループリント側で節を分ける）。
5. `§` 参照に、存在しない節がない。
6. 索引表が存在し、指す節が実在し、どの行にも属さないファイルがない（新設節の取りこぼしの検知）。参照先の列が、必読節の直接の参照先（必読節またはその祖先に含まれるものを除く）を欠く場合は警告にする。
7. `placeholder_check` がある場合、正本から抽出した `{{...}}` がすべて、指定ファイルの指定の節（`## <heading>`）に存在する。

## 使い方（設定スキルから呼ばれる）

```bash
# 生成（親 → 子の順で設定スキルごとに実行）
python3 .cursor/skills/agentic-workflow-engine/scripts/generate.py --skill-dir <config-skill-dir>

# 冪等性ドライラン
python3 .cursor/skills/agentic-workflow-engine/scripts/generate.py --skill-dir <config-skill-dir> --check

# 監査（冪等性 + 必須要件）
python3 .cursor/skills/agentic-workflow-engine/scripts/audit.py --skill-dir <config-skill-dir>

# consumer updater の候補検証（既存 seed の required_sections は検査しない）
python3 .cursor/skills/agentic-workflow-engine/scripts/audit.py \
  --skill-dir <config-skill-dir> \
  --skip-seed-required-sections
```

## exit code（QUALITY_GATE 3段階に準拠）

| code | 意味 |
| --- | --- |
| 0 | 冪等性 OK + 必須要件充足（`project.*` の `[要確認]` 残存は WARN だが PASS） |
| 1 | drift（出力の直接編集）/ 必須要件欠落 / 出力ファイル不在 / `mode: split` の書式契約違反（サイズ上限、参照切れ、索引の網羅、プレースホルダの照合、残骸ファイル） |
| 2 | 致命的エラー（テンプレート不在 / `manifest.yaml` 破損 / `mode: split` の入力が契約外: 正本の不在、設定の不備、出力ディレクトリの symlink・下位ディレクトリ） |

## consumer updater の seed 監査例外

既定の `audit.py` は、`mode: seed` を含む全 outputs[] について
`required_sections` を検査する。この既定動作は foundation 自己検証
（`bin/foundation-gate audit` / `self`）のテンプレート準拠検査として維持する。

consumer updater の `plan` は、kit が適用対象にしない既存 seed
（ADR / GOTCHAS / Domain docs / skill config）を内容変更せず保護する。
この経路だけ `--skip-seed-required-sections` を指定し、seed は存在のみ、
render / marker は従来どおり drift と required_sections を検査する。
ファイル不在、未知の mode、テンプレート不在、描画失敗はこの例外で緩和しない。

## スコープ外

- 各設定スキルの `manifest.yaml` / `templates/` の**内容**（What）。本エンジンはそれらを入力として受け取るだけで、定義しない。
- 設定スキル固有のロジック（例 `agentic-workflow-foundation` の `tech_contract` / 整合ゲート）は各設定スキル側に置く（本エンジンは `genlib` を提供するのみ）。
