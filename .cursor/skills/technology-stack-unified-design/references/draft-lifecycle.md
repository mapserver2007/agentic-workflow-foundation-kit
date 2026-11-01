# `docs/gen/` reverse-draft ライフサイクル

| 項目 | 定義 |
| --- | --- |
| 位置づけ | `docs/gen/` は生成ドラフトの保管場所。仕様のSoTではなく、G-DOC-SPEC・foundation Phase 1.6の入力のどちらにもならない |
| 配置・世代 | `docs/gen/<stack_slug>/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` の1ファイルだけ。`stack_slug` は§9の代表的な技術・役割から推論し、owner / repo 名には依存させない。世代管理せず、再生成は承認付きatomic replace、履歴はGitに任せる |
| 候補 identity | `status: reverse-draft`、JSON文字列の `title` / `generated_at`（`YYYY-MM-DD`）、`source_repository` / `source_ref` / `source_revision` / `stack_slug` を保持する。`title` / `generated_at` は候補の識別用であり、正本固有のメタデータを強制しない |
| Git管理 | `docs/gen/` は現状ignore対象外。スキルは `.gitignore` を変更せずcommitもしない。reverse-draftのままcommitするかはユーザー判断 |
| 保存期間 | 自動削除しない。不要時はユーザーが削除する。`status: reverse-draft` の間は正本でない |
| レビュー | PRに含めてよいが、reverse-draftであること、`stack_slug` が§9を適切に要約していること、`[要確認]` 件数、`該当なし` の根拠、evidenceの十分性を明示する |
| 更新 | validator PASS後、既存時はユーザー承認を得て同一ディレクトリ内の一時ファイルからatomic replaceする |

## 正本への手動昇格

v1ではスキルは昇格を実行しない。次はユーザー承認を前提とする手動手順。

1. 昇格先を、foundation Phase 1.6を実行する対象リポジトリにする。別リポジトリならユーザーがドラフトを手動で持ち込む。
2. 昇格先manifestの `project.tech_stack_design_filename` と同名で `.cursor/docs/` または `docs/` に置く。`tech_contract.resolve_design_doc` の探索順は `.cursor/docs/<name>`、`docs/<name>` で、`docs/gen/` は探索対象外。
3. `[要確認]` をすべて解消するか、残す項目をユーザーが明示承認する。`該当なし` の具体的根拠とevidenceが主張を支えるかもレビューする。
4. frontmatterの `status: reverse-draft` を正本の状態へ更新する。`source_repository`、`source_ref`、`source_revision`、`stack_slug` と候補 identity は来歴として残す。
5. 既存正本は上書きしない。別名配置か、差分レビューを経た置換かをユーザーが決める。Meta層入力正本の置換はAsk First。
6. 昇格後、`ingest_tech_stack.py --check` を先に実行し、取り込み件数と書き換え有無を確認する。PASS後だけ通常のPhase 1.6取り込みと `tech_contract` の承認フローへ進む。

ドラフトのcommit・削除・昇格、既存正本の置換をスキルが暗黙実行してはならない。
