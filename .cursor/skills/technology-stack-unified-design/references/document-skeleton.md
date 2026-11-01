# 技術スタック統一設計書の骨格

本文の書き方・品質基準は [`quality-bar.md`](quality-bar.md)（B 水準の定義と機械検査の床）、節ごとの作業は [`section-playbook.md`](section-playbook.md)。本書は **validator が検査する構造・来歴・証跡の契約**を定義する。

## 強制レベル

- **MUST**: `validate_design_doc.py` が検査する不変条件。下の対応表に検査項目を示す。
- **SHOULD**: 調査・記述品質の推奨。validator は検査しない。
- **MAY**: 対象実装に合わせて変更できる表現・粒度・記述順。

## MUST と validator の対応

| MUST | validator の検査 |
| --- | --- |
| JSON文字列の候補 identity・来歴 frontmatter | `title`、`generated_at`、既存来歴5キー、重複、JSON decode、revision、`stack_slug` 形式、現在のworktreeとの一致 |
| 情報ナビゲーション | 単一の `## 目次`、実本文へ対応する §1〜§24 / Appendix A〜E リンク、単独行 `---` の境界 |
| Part / 節 / Appendix 構造 | `PART_SECTIONS` / `APPENDIX_IDS`、欠落・重複・順序・所属、Part role labels、Appendix責務トークン |
| 各節の根拠 | 空本文でないこと、節内に `[E<n>]` / `evidence:` / `[要確認]:` / `該当なし:` のいずれか、placeholder の拒否 |
| 本文品質の床（B 水準） | `document_quality.py`: 節ごとの分量・参照数・構造要素（表・図・ツリー・フロー・小見出し）、`[要確認]` / `該当なし` の上限、§9 の行数、Appendix A〜E の床 |
| 証跡台帳 | Appendix B の台帳表（`ID \| 証跡 \| 引用 \| 裏付け`）、ID 重複・未参照・未定義参照、**引用の逐語実在**、全 evidence の行範囲の実在 |
| 全量読解の到達 | `調査範囲:` 行が survey の再計算値と逐語一致、全 shard note の完全性（`survey_repository.py check`） |
| fenced code / HTML comment の除外 | `_mask_markdown`。ただし§9はingest互換のraw line検査 |
| §9入力互換 | `_validate_section9` |
| evidence字句・実在性・安全性 | `EVIDENCE_TOKEN_RE`、`lstat`、全量 `git ls-files -z` set、除外リスト |
| 来歴・非混入 | `inspect_repository` 再実行、`_validate_provenance`、`_validate_non_inclusion` |

`--structure-only` は本文品質・台帳・調査範囲を検査しない旧契約（構造・来歴・証跡の存在だけ）で、**publish には使えない**。

## stack slug 契約

`stack_slug` は §9 の代表的な技術・役割を短く要約して LLM が推論する。owner / repo 名は材料にしない（SHOULD）。例: runtime が Python、API framework が FastAPI、storage が PostgreSQL なら `python-fastapi-postgresql`。

- frontmatter に JSON 文字列リテラルとして1件だけ置く（MUST）。
- 1〜63文字の lowercase kebab-case `[a-z0-9]+(?:-[a-z0-9]+)*` とする（MUST）。
- publisher は検証済みの値だけを `docs/gen/<stack_slug>/` のディレクトリ名に使う（MUST）。
- §9 を適切に要約しているかは validator では判定せず、ユーザーレビューで確認する（SHOULD）。
- 同じ stack を再調査するときは既存 slug を維持する（SHOULD）。異なる対象が同じ slug になった場合も暗黙に区別子を足さず、既存成果物の上書き承認で衝突を顕在化する。

## 構造契約

次の対応は **MUST**。章題は **MAY** とし、対象実装に合わせて言い換えてよい。

| Part | 役割 | 所属する節 |
| --- | --- | --- |
| Part 1 | 概念編（なぜ） | §1〜§5 |
| Part 2 | アーキテクチャ編（何を） | §6〜§8 |
| Part 3 | 技術スタック編（具体） | §9〜§15 |
| Part 4 | 開発・運用と横断ルール編（どう動かす） | §16〜§23 |
| Part 5 | 意思決定編（意思決定） | §24 |
| Appendix | Partの外の付録 | Appendix A〜E |

Part 見出しには括弧で上表の role label（`なぜ` / `何を` / `具体` / `どう動かす` / `意思決定`）を含める（MUST）。章題のそれ以外の文言は MAY。

Appendix A〜E は順に、`比較`、`根拠`、`用語`、`参照`、`チェックリスト` の責務トークンを見出しに含める（MUST）。技術固有の題名・本文は MAY。

`#` のタイトルまたは導入の後に単独行 `---` を置き `## 目次` を置く。目次には実際の本文見出しへ一致する §1〜§24 の番号付きリンクと Appendix A〜E のリンクを置く（MUST）。TOC内の見出し風テキストは本文見出しにならない。

目次→Part 1、Part間、同一Part内の後続節、Appendix開始、Appendix B〜E の各境界には、後続見出しの直前に単独行 `---` を置く（MUST）。Part見出し直後の先頭節、および `## Appendix` 直後の Appendix A の前には余分な separator を置かない。§9表の直後の `---` は §10 への境界であり、§9本文には含めない。

導入部（`#` タイトルと目次の間）には、対象・読み方（`§N` と `[E<n>]` の意味）・位置づけ（reverse-draft であり SoT ではない）と、survey が出力した **`調査範囲:` 行を逐語で**置く（MUST）。

各 § は番号と Part 所属で次の役割に対応する。validator はこの対応と構造を検査するが、本文が役割を意味的に充足することは保証しない。

| 節 | 責務 |
| --- | --- |
| §1〜§5 | 方針・正本・採否・整合・原則 |
| §6〜§8 | 全体構成・リポジトリ構成・レイヤ境界 |
| §9〜§15 | 技術一覧・契約・生成・interface・backend・data・test |
| §16〜§23 | 開発・実装順序・CI・デプロイ・API・認可・制約・利用フロー |
| §24 | reverse-draftとしての結論とレビュー判断 |

## 各節の根拠と宣言

各§の本文には、次のいずれか1つ以上を置く（MUST）。品質の床（`quality-bar.md` §4）は別に検査される。

- 観測できる事実: `[E<n>]`（Appendix B 台帳への参照。推奨）または `evidence: path/to/file#L1-L10`
- 実装だけでは判断できない: `[要確認]: 判断に必要な情報と未確定理由`（1 節 2 件まで、本文合計の上限あり）
- 該当実装がない: `該当なし: 探した対象と、存在しないと判断した根拠`（20 文字以上、4 節まで）

理由を空にしたり、`<理由>`、`TODO`、`TBD`、`...` だけにしたりしない（MUST）。fenced code block と HTML comment 内は見出し・宣言・evidence として数えない（MUST）。§9だけは foundation ingest との互換のため raw line 規則も適用する。

## evidence 契約

書式は `evidence: <相対パス>[#L<開始>[-L<終了>]]`。1件ごとに `evidence:` を繰り返す（MUST）。全体をバッククォートで囲める。token終端は空白、バッククォート、`;`、`,`、`|`、`)`。空白や区切り文字を含むpathはv1では表現できないため `[要確認]` とする。

evidence は source root 内の tracked な通常ファイルで、経路上を含めsymlinkでなく、`references/evidence-signals.md` の除外対象でないこと（MUST）。品質検査（既定）では `#L` の **行範囲が実ファイルの範囲内**であることも検査する（`--syntax-only` / `--structure-only` では書式のみ）。

### 台帳（Appendix B）の契約

```text
| ID | 証跡 | 引用 | 裏付け |
| --- | --- | --- | --- |
| E1 | evidence: path/to/file#L3-L5 | `ファイルに実在する文字列の一部` | 何を裏付けるか |
```

- ヘッダは上記 4 列に完全一致。全行ちょうど 4 セル（引用に `|` を含めない）。ID は `E<数字>` で一意（MUST）。
- 各行の証跡セルは `evidence:` を 1 件だけ持つ。引用は 3〜120 文字で、**指定した行範囲に逐語で実在**する（空白の連続は 1 つに正規化して比較）（MUST）。
- 台帳 ID は本文から `[E<n>]` で必ず参照される。台帳に無い `[E<n>]` は不可（MUST）。

## §9 契約

見出しは `### 9.` で始め、表は次の4列にする（MUST）。

| レイヤ | 技術 | バージョン方針 | 備考 |
| --- | --- | --- | --- |
| 対象内の役割 | 観測した技術名 | 宣言: 明示constraint | 観測: 値 [E<n>] |

- データ行を1件以上置く（品質検査では standard で 12 行以上）。1・2列目は非空、1列目に `レイヤ` を含めない（MUST）。
- 方針列は `宣言: <値>`、`[要確認]`、`—` のいずれか。`観測` は方針列に置かない（MUST）。
- §9内の行頭パイプ行は単一の連続表だけ。全行4セルで、セル内パイプはescape形も含め不可（MUST）。
- 同一セルに `"` と `'` を併用しない。`>` 始まりの行は0または1行。`---` と追加の `###` 行は置かない（MUST）。
- 文書中の fenced code 内に番号付き `### 9.` 等を置かない（MUST）。
- §9の問いはblockquoteにしない。`>` 行を使うなら、foundationの `tech_stack.note` に取り込まれてよい観測事実を1行だけ書く（SHOULD）。
- 明示constraint / channel / pinだけを `宣言:` とし、lockfileの解決値は備考へ `観測:` として書く（SHOULD）。
- 備考の根拠は `[E<n>]`（または `evidence: path#L`）で示す（SHOULD）。

validator が保証するのは構文と `ingest_tech_stack.py` への入力互換だけである。分類・系列一般化・証跡の十分性など意味の正しさはユーザーがレビューする。

## コピー用骨格

値と問いを対象実装に合わせて埋める。章題・本文表現はMAY。**各節の `<!-- -->` は問いであり、本文に置き換える**（HTML comment は検査から除外される）。構造要素（表・図・ツリー）の必須性は `quality-bar.md` §4.2。

~~~markdown
---
status: reverse-draft
title: "対象実装の技術スタック統一設計書"
generated_at: "YYYY-MM-DD"
source_repository: "https://github.com/owner/repo"
source_ref: "main"
source_revision: "0000000000000000000000000000000000000000"
stack_slug: "runtime-framework-storage"
---

# 技術スタック統一設計書

* 対象: <この実装が何をするシステムか 1 行>
* スコープ: <設計書が扱う範囲>
* 読み方: `§N` は本書の節、`[E<n>]` は Appendix B の証跡台帳（ファイル・行・逐語引用）を指す
* 位置づけ: reverse-draft。仕様の SoT ではなく、ユーザーレビュー前の下書きである

調査範囲: tracked=0; skipped=0; generated=0; read=0 (full=0, card=0); shards=0; revision=0000000

---

## 目次

### Part 1
1. [全体方針](#1-全体方針)
2. [契約と正本](#2-契約と正本)
3. [採用・非採用方針](#3-採用非採用方針)
4. [技術間の整合](#4-技術間の整合)
5. [設計原則](#5-設計原則)

### Part 2
6. [全体アーキテクチャ](#6-全体アーキテクチャ)
7. [リポジトリ構成](#7-リポジトリ構成)
8. [レイヤ責務と契約境界](#8-レイヤ責務と契約境界)

### Part 3
9. [技術スタック一覧とバージョン方針](#9-技術スタック一覧とバージョン方針)
10. [契約・schema層](#10-契約schema層)
11. [生成・client層](#11-生成client層)
12. [利用者向けinterface層](#12-利用者向けinterface層)
13. [service・backend層](#13-servicebackend層)
14. [data・storage層](#14-datastorage層)
15. [mock・test層](#15-mocktest層)

### Part 4
16. [ローカル開発](#16-ローカル開発)
17. [実装順序](#17-実装順序)
18. [CI](#18-ci)
19. [デプロイ・環境分離](#19-デプロイ環境分離)
20. [API・interface設計](#20-apiinterface設計)
21. [認証・認可](#21-認証認可)
22. [制約と割り切り](#22-制約と割り切り)
23. [UI・利用フロー](#23-ui利用フロー)

### Part 5
24. [結論](#24-結論)

### Appendix
* [Appendix A: 比較](#appendix-a-比較)
* [Appendix B: 根拠](#appendix-b-根拠)
* [Appendix C: 用語](#appendix-c-用語)
* [Appendix D: 参照](#appendix-d-参照)
* [Appendix E: チェックリスト](#appendix-e-チェックリスト)

---

## Part 1: 概念編（なぜ）

### 1. 全体方針
<!-- この実装が解こうとしている問題と主要な技術方針は何か？ 箇条書き + 思想の一言要約 -->

---

### 2. 契約と正本
<!-- 仕様・schema・設定の正本はどこで、変更の起点と生成物は何か？ 表（対象 / 正本 / 生成物 / 検証） -->

---

### 3. 採用・非採用方針
<!-- 採用した選択と、観測できる代替・併存・移行途中は何か？ 表（選択 / 代替の痕跡 / 評価） -->

---

### 4. 技術間の整合
<!-- 主要要素はどの境界で接続され、何が揃っているべきか？ 接続図 + 境界表 -->

---

### 5. 設計原則
<!-- 反復して現れる制約・規約は何か？ 原則表（原則 / 要約 / 参照） -->

---

## Part 2: アーキテクチャ編（何を）

### 6. 全体アーキテクチャ
<!-- 実行時コンポーネントと配置・通信は何か？ 構成図 + デプロイ単位表 -->

---

### 7. リポジトリ構成
<!-- workspace・package・moduleの境界と分割原則は何か？ 役割付きツリー -->

---

### 8. レイヤ責務と契約境界
<!-- 依存方向と公開境界、やってはいけないことは何か？ 責務表 + import 集計の裏取り -->

---

## Part 3: 技術スタック編（具体）

### 9. 技術スタック一覧とバージョン方針
依存manifest、runtime constraint、CI matrix、container pin、生成 tool の pin から、何が明示されているか。

| レイヤ | 技術 | バージョン方針 | 備考 |
| --- | --- | --- | --- |
| 役割 | 技術名 | 宣言: 値 | 観測: 根拠 [E1] |

---

### 10. 契約・schema層
<!-- 公開契約・schemaはどこで定義され、どの処理が検証し、規模はどれほどか？ -->

---

### 11. 生成・client層
<!-- 生成物とclientは何を入力に作られ、誰が所有し、差分はどう検出されるか？ 生成パイプライン表 -->

---

### 12. 利用者向けinterface層
<!-- 利用者向けinterfaceはどのruntimeと境界を持つか？ -->

---

### 13. service・backend層
<!-- service・backendはどの契約を実装し、どの構造・規約で何を公開するか？ -->

---

### 14. data・storage層
<!-- dataの保存先、schema、migration、cache、寿命はどう定義されるか？ 保存先別の表 -->

---

### 15. mock・test層
<!-- mockとtestはどの境界・契約・runtimeを検証し、CIでどう実行されるか？ テスト種別表 -->

---

## Part 4: 開発・運用と横断ルール編（どう動かす）

### 16. ローカル開発
<!-- 開発者が安全に起動・反復・停止する標準手順は何か？ フロー -->

---

### 17. 実装順序
<!-- 契約・生成物・実装・testはどの順序で変更するか？ 番号付き手順 -->

---

### 18. CI
<!-- CIはどの品質条件と再現性を必須gateとして担保し、何をgateしないか？ ジョブ表 -->

---

### 19. デプロイ・環境分離
<!-- 環境ごとの設定・secret・resource・releaseはどう分離され、どこへ委譲されるか？ -->

---

### 20. API・interface設計
<!-- 公開interfaceの互換性、error、命名、versionはどう管理されるか？ -->

---

### 21. 認証・認可
#### 方針の要点
<!-- identity、権限、trust boundary、secretはどこで強制されるか？ -->

#### 責務分離と経路
<!-- 責務表・経路・将来の拡張 -->

---

### 22. 制約と割り切り
<!-- 実装が受容している制約・既知の限界・版の食い違い・代替案は何か？ -->

---

### 23. UI・利用フロー
<!-- UIまたは主要利用フローの状態・導線・正本はどこにあるか？ 無ければ 該当なし: 探した対象 -->

---

## Part 5: 意思決定編（意思決定）

### 24. 結論
<!-- 要約の図 + 判断。確定できないことは Appendix E へ -->

---

## Appendix

### Appendix A: 比較
<!-- 観点 × 選択肢の表と判断 -->

---

### Appendix B: 根拠
| ID | 証跡 | 引用 | 裏付け |
| --- | --- | --- | --- |
| E1 | evidence: path/to/tracked-file#L1-L3 | `ファイルに実在する文字列` | 何を裏付けるか |

---

### Appendix C: 用語
<!-- 用語表（8 行以上） -->

---

### Appendix D: 参照
<!-- リポジトリ内の主要ファイル（8 件以上） -->

---

### Appendix E: チェックリスト
<!-- 優先度 | 項目 | 理由 の表（P0〜P3、8 行以上）。未確定事項の集約先 -->
~~~
