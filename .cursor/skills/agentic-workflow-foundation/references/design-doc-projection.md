# Design Doc 投影 draft 起案ガイド

`designs/docs/designdoc.md` または `designs/docs/design-doc.md` の片方から、初回 Domain docs 生成用の `tmp/design-doc-projection-draft.yaml` を起案する。

## 原則

1. Design Doc に明示された内容だけを転記する。根拠節が無いフィールドはキーごと省略する。
2. 各フィールドは `body` と `evidence` の2キーだけを持つ。`evidence` は Design Doc 内に実在する ATX 見出しの本文（先頭の `#` を除いた完全な文字列）とする。
3. `body` は出力へそのまま展開できる Markdown とする。Mustache 構文の混入を避けるため `{{` / `}}` を含めない。
4. 曖昧な値を推測しない。必要なら本文に `[要確認]` と書く。
5. 画面設計、画像リンク、ER 図は投影しない。実ファイルが無い参照を生成物へ持ち込まない。
6. 5 つの doc（`spec` / `api` / `architecture` / `data_models` / `workflows`）は、それぞれ1フィールド以上を起案する。根拠となる節が Design Doc に無いときだけ、`omissions` に doc 名と省略理由を書く。省略理由は Design Doc を読んだ結果として具体的に書く（「記述なし」だけにしない）。同じ doc を投影と `omissions` の両方に書かない。

## フィールド対応

| doc | フィールド | 差し込み先 |
| --- | --- | --- |
| `spec` | `purpose` | `docs/spec.md > 目的と背景`。目的と非目標を1本文に含める |
| `spec` | `glossary` | `ドメイン用語集` |
| `spec` | `boundary` | `システム境界` |
| `spec` | `principles` | `不変の設計原則` |
| `spec` | `features` | `機能仕様`。1見出し1機能。個別 spec への詳細リンクは書かない |
| `spec` | `non_functional` | `非機能要件` |
| `spec` | `change_resilience` | `変更に強い点・弱い点` |
| `api` | `overview` | `API設計概要`。共通規約も本文に含める |
| `api` | `endpoints` | `エンドポイント一覧` |
| `api` | `errors` | `エラーハンドリング` |
| `api` | `details` | `API 詳細` として追加 |
| `architecture` | `overview` | `システム全体構成` |
| `architecture` | `modules` | `ディレクトリ/モジュール責務` |
| `architecture` | `components` | `主要コンポーネント詳細` |
| `architecture` | `dependencies` | `依存関係方針` |
| `data_models` | `principles` | `データベース設計思想` |
| `data_models` | `entities` | `主要テーブル/コレクション構成` |
| `data_models` | `access` | `データアクセスパターン` |
| `workflows` | `flows` | `主要ユースケースの処理フロー` |
| `workflows` | `retry` | `エラーハンドリング・リトライパターン` |
| `workflows` | `states` | `状態管理・状態遷移` |

`data_models` の ER 節は常にスケルトンを残す。長い `workflows.flows` は転記漏れの機械検出ができないため、起案後に Design Doc と段落単位で照合する。

### architecture の根拠対応

`architecture` は、Design Doc にディレクトリ構成やレイヤ依存の節が無くても省略しない。次の根拠から、Design Doc に明示された内容だけを起案する。見出し名はプロジェクトごとに異なるため、下表は探す対象を示す。

| フィールド | 探す根拠 | 書く内容 |
| --- | --- | --- |
| `overview` | シーケンス図の actor / participant、業務フローの画面・API・サーバーの責務分割、システム外の操作を述べた箇所 | 登場する構成要素と接続、システム外の操作。Mermaid 図は構成要素と呼び出し方向だけを描く |
| `modules` | 構成要素ごとの責務と呼び出し先を述べた箇所 | 構成要素ごとの責務と依存先の表。ディレクトリやパッケージの記述が Design Doc に無いときは、モジュール（構成要素）単位の表にし、パスを作らない |
| `components` | 構成要素ごとの振る舞い（周期的な取得、ロック、押し出しの有無、状態の保持場所など） | 構成要素ごとの節。節の見出しは `###` 以下にする（`##` にすると、生成物でその doc 固有の節と同じ階層に並び、構造が読み取りにくくなる） |
| `dependencies` | 呼び出しの向き、直接更新の禁止、外部連携の有無を述べた箇所 | 依存方向の規則と、外部連携を持たない旨の明示 |

Design Doc に根拠が1件も無いときだけ `architecture` を `omissions` に書く。`omissions` は doc ごとに具体的な理由を持つ。

### 本文中の見出しレベル

`body` に `##` を含めてよいのは、その doc の節構成を拡張するときだけである（例: `spec.features` の機能ごとの見出し）。生成時の節境界は、投影なしスケルトン由来の構造見出し（`##`）だけで決まる。`body` 中の `##` は節本文の一部として扱われる。階層を保つため、`architecture` の各フィールドでは `###` 以下を使う。

## draft 形式

```yaml
design_doc:
  schema_version: 1
  source_path: "designs/docs/designdoc.md"
  source_fingerprint: "<design_doc_projection.source_fingerprint>"
  projection:
    spec:
      purpose:
        body: |-
          Design Doc に明示された目的と非目標。
        evidence: "目的"
    workflows:
      flows:
        body: |-
          Design Doc に明示された業務フロー。
        evidence: "業務フロー"
  omissions:
    data_models: "Design Doc にデータベース設計の節が無い。永続化を持たない設計である。"
```

`omissions` は任意である。キーは doc 名、値は非空の理由とする。5 つの doc すべてに投影があるときは `omissions` を書かない。全 doc を `omissions` だけにした draft は拒否される（投影が 0 件のため）。

draft に `digest` / `approval` を書かない。`apply` が canonical digest を計算し、`approval.status: approved` と結合して root manifest へ固定する。

## 状態と exit code

| Design Doc | pin | Phase 1.69 | engine |
| --- | --- | --- | --- |
| なし | なし | 0（スケルトン） | 0 |
| なし | あり | 2（入力消失） | 2 |
| 2ファイル共存 | 任意 | 2（入力曖昧） | 2 |
| 片方あり | なし | 1（起案を促す） | 0（投影なし） |
| 片方あり | draft・doc 欠落（投影も `omissions` も無い doc がある） | 1（再起案） | — |
| 片方あり | あり・fingerprint 不一致 | 1（再起案） | 1 |
| 片方あり | あり・doc 欠落（旧規則で pin 済み） | 1（再起案） | 1 |
| 片方あり | あり・approval / digest 不整合 | 2 | 2 |
| 片方あり | あり・整合 | 0 | 0（投影） |

## 検証と固定

```bash
python3 .cursor/skills/agentic-workflow-foundation/scripts/design_doc_projection.py validate \
  --design-doc designs/docs/designdoc.md \
  --check

preimage="$(python3 -c 'import hashlib; print(hashlib.sha256(open("manifest.yaml","rb").read()).hexdigest())')"
python3 .cursor/skills/agentic-workflow-foundation/scripts/design_doc_projection.py apply \
  --design-doc designs/docs/designdoc.md \
  --preimage "$preimage"
```

validate PASS 後は AskQuestion を出さず、自動承認で apply する。validate FAIL の場合は投影を固定せず、Design Doc または draft の不整合を修正する。

doc 欠落（exit 1）は、欠けた doc の投影を起案するか、`omissions` に理由を書いて再 validate する。`omissions` の形式不正、投影との重複、全 doc が `omissions` のみの draft は exit 2 である。

## 生成時の追記の挙動

pin 後の generate は、5 つの Domain docs を次の順で扱う。

1. 既存ファイルが投影あり描画と一致するなら何もしない。
2. 既存ファイルが投影なしスケルトンと完全一致するなら、ファイル全体を投影あり描画に置き換える。
3. それ以外は構造節（投影なしスケルトン由来の `##` 見出し）ごとに比較し、本文が投影なしスケルトンのまま残っている節だけを投影あり描画の節で置き換える。手で書いた節と前文は保持する。構造見出しが既存ファイルから見つからないときは、そのファイルを変更せず `見出し構成不一致` を報告する。

節境界に管理マーカーは使わない。投影本文が出す追加見出し（例: `API 詳細`）は、直前の構造節の本文に含まれる。その塊は直前の節が置換されるときだけ挿入される。
