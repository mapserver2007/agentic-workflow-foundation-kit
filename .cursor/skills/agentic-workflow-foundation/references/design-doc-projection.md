# Design Doc 投影 draft 起案ガイド

`designs/docs/designdoc.md` または `designs/docs/design-doc.md` の片方から、初回 Domain docs 生成用の `tmp/design-doc-projection-draft.yaml` を起案する。

## 原則

1. Design Doc に明示された内容だけを転記する。根拠節が無いフィールドはキーごと省略する。
2. 各フィールドは `body` と `evidence` の2キーだけを持つ。`evidence` は Design Doc 内に実在する ATX 見出しの本文（先頭の `#` を除いた完全な文字列）とする。
3. `body` は出力へそのまま展開できる Markdown とする。Mustache 構文の混入を避けるため `{{` / `}}` を含めない。
4. 曖昧な値を推測しない。必要なら本文に `[要確認]` と書く。
5. 画面設計、画像リンク、ER 図は投影しない。実ファイルが無い参照を生成物へ持ち込まない。

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

`architecture` は根拠となる記述があるフィールドだけを起案する。`data_models` の ER 節は常にスケルトンを残す。長い `workflows.flows` は転記漏れの機械検出ができないため、起案後に Design Doc と段落単位で照合する。

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
```

draft に `digest` / `approval` を書かない。`apply` が canonical digest を計算し、`approval.status: approved` と結合して root manifest へ固定する。

## 状態と exit code

| Design Doc | pin | Phase 1.69 | engine |
| --- | --- | --- | --- |
| なし | なし | 0（スケルトン） | 0 |
| なし | あり | 2（入力消失） | 2 |
| 2ファイル共存 | 任意 | 2（入力曖昧） | 2 |
| 片方あり | なし | 1（起案を促す） | 0（投影なし） |
| 片方あり | あり・fingerprint 不一致 | 1（再起案） | 1 |
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
