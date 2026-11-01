---
name: technology-stack-unified-design
description: >-
  ユーザーが手動 clone / update した clean なローカル Git worktree の既存実装を、
  ネットワーク通信と対象への書き込みなしで全可読ファイルまで読み、kit 正本 B と同水準
  （原則表・責務表・構成図・ツリー・フロー・比較・優先度付きチェックリスト・証跡台帳）の
  TECHNOLOGY_STACK_UNIFIED_DESIGN.md reverse-draft を docs/gen/ に作る。
  「既存リポジトリから技術スタック設計書をリバース」「tech stack unified design を
  生成」等で使う。Do NOT use for: repository の clone/update、foundation の生成物化、
  正本設計書の自動置換。
disable-model-invocation: true
---

# technology-stack-unified-design

既存実装のローカル snapshot を**全可読ファイルまで**読み、技術非依存の 5 Part 構造を持つ技術スタック統一設計書を作る単独スキル。出力は証跡ログではなく、正本 B（`.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md`）と同水準の設計書である（定義は [`quality-bar.md`](references/quality-bar.md)）。foundation / engine の manifest・template・生成済み `bin/*`・`github_access`・認証 helper には依存しない。

## 実行契約

- Python 3.9 以上、標準ライブラリのみ。全 Python ファイルは `from __future__ import annotations` を使用する。
- `git clone` / `fetch` / `pull` / `checkout` / `ls-remote`、`gh`、`curl` 等のネットワーク取得を行わない。対象の取得・更新はユーザーが事前に行う。
- `source_repository` は単一のローカル `origin` を自動検出して canonical GitHub URL に正規化する。URL をユーザーへ質問せず、自己申告値との照合も行わない。
- 対象 worktree では build / test / install をせず、ファイル・index・設定・権限を変更しない。Git 操作は `GIT_OPTIONAL_LOCKS=0` の読み取り専用 command に限定する。survey の出力先は source root の**外**（既定 `tmp/tech-stack-survey/`）。
- shard 読解を sub-agent へ委譲してよい。sub-agent も読み取り専用で、書き込みは担当 shard の note だけとする（[`shard-review-protocol.md`](references/shard-review-protocol.md)）。
- 既存の kit 正本 `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` を上書きしない。
- 本文の表現・粒度・章題は再実行で変わってよく、byte-identical な冪等性は要求しない。validator は構造・来歴・証跡（台帳引用の逐語実在を含む）・本文品質の床・調査範囲の到達を検査するが、宣言の真偽、説明の妥当性、slug の意味的な妥当性は保証しない。最終判断はユーザーレビューで行う。

exit code は `0=通過`、`1=状態または候補を直して再実行`、`2=入力・環境が契約外`。

## 手順

1. AskQuestion で手動 clone / update 済み worktree root の絶対パスを確定する。GitHub URL は質問しない。
2. ローカル snapshot を検証する。

   ```bash
   python3 .cursor/skills/technology-stack-unified-design/scripts/inspect_local_repository.py \
     --source-root <absolute-path>
   ```

3. **全量走査（survey）**: 全 tracked 可読ファイルを決定論的に走査し、構造 card・facts・shard 作業指示・note 雛形を作る。

   ```bash
   python3 .cursor/skills/technology-stack-unified-design/scripts/survey_repository.py survey \
     --source-root <absolute-path> --out-dir tmp/tech-stack-survey
   ```

   `tmp/tech-stack-survey/overview.md`（全体像・生成物・entry・外部依存頻度・層間 import 集計）と `facts/*.md`（`path#L行 | 逐語テキスト` 形式。台帳の引用元になる）を読む。

4. **shard 読解**: `tmp/tech-stack-survey/shards/shard-NN.md` を全 shard 読み、`notes/shard-NN.note.md` を完成させる。手順・禁止・品質基準は [`shard-review-protocol.md`](references/shard-review-protocol.md)。shard が複数ある場合は **1 メッセージで sub-agent を並列起動**する。全 shard 完了後に次を通す。

   ```bash
   python3 .cursor/skills/technology-stack-unified-design/scripts/survey_repository.py check \
     --survey-dir tmp/tech-stack-survey --source-root <absolute-path>
   ```

   PASS 時に出る `調査範囲:` 行（tracked・skipped・generated・read（full / card）・shards）を控える。FAIL 時は列挙された shard だけを再依頼する。

5. **起草**: [`quality-bar.md`](references/quality-bar.md)（B 水準の定義と床）と [`section-playbook.md`](references/section-playbook.md)（節別の作業）に従い、[`document-skeleton.md`](references/document-skeleton.md) の骨格で `tmp/tech-stack-reverse-candidate.md` を作る。
   - inspect の `source_*` JSON 文字列を frontmatter にそのまま貼り、`status: reverse-draft`、JSON 文字列の `title` / `generated_at`（`YYYY-MM-DD`）/ `stack_slug` を記録する。絶対パスは残さない。§9 の代表的な技術・役割から owner / repo 名を使わず `stack_slug` を推論する。
   - 導入部に手順 4 の `調査範囲:` 行を**逐語で**置く。
   - 全 shard の `## 所見` を読んで設計を組む。証跡は 2 通りで台帳化する。(1) `collect_ledger.py collect` が全 note の `## 証跡候補` を逐語検証して台帳候補（`ledger-candidates.md`、ID は安定採番）にする。(2) 本文中に `[[path#L行 :: 主張]]`（行範囲可。`:: 主張` は省略可）と書くと、`sync` が実ファイルのその行から**逐語引用を機械的に作って**採番し `[E<n>]` に置換する。書き終えたら `sync` が参照された行だけを Appendix B へ書き出す（未参照行は除かれる）。

     ```bash
     python3 .cursor/skills/technology-stack-unified-design/scripts/collect_ledger.py collect \
       --source-root <absolute-path> --survey-dir tmp/tech-stack-survey
     python3 .cursor/skills/technology-stack-unified-design/scripts/collect_ledger.py sync \
       tmp/tech-stack-reverse-candidate.md --survey-dir tmp/tech-stack-survey --source-root <absolute-path>
     ```

     マーカーは fenced code の外に書く。Appendix B には空の台帳表（ヘッダ行 `| ID | 証跡 | 引用 | 裏付け |` と区切り行）を置いておく。
   - 本文は**部品ファイル**（`tmp/draft/00-front.md` = 導入と `{{COVERAGE}}`、`10-*.md` 以降 = Part / 節 / Appendix）に分けて書く。`assemble_candidate.py` が部品を結合し、frontmatter・調査範囲行・`## 目次` を自動生成して、台帳同期（`sync`）と validator まで一度に実行する（手順 6 の検証を兼ねる）。目次のリンクずれ・区切りの欠落・調査範囲行の転記ミスを防げる。

     ```bash
     python3 .cursor/skills/technology-stack-unified-design/scripts/assemble_candidate.py \
       --parts-dir tmp/draft --source-root <absolute-path> --survey-dir tmp/tech-stack-survey \
       --title "<設計書の title>" --slug <stack_slug> --out tmp/tech-stack-reverse-candidate.md
     ```
   - 本文は「主張 → 構造（表・図・ツリー・フロー）→ 根拠」。観測・推定・未確定を書き分け、未確定は Appendix E へ優先度付きで集約する。`## 目次` と `---` 境界、Part role labels、Appendix 責務トークンを満たす。

6. 候補を来歴・台帳・調査範囲込みで検証する。FAIL したら、メッセージが指す節・台帳行だけを直して再実行する（**床を満たすための水増しをしない**。分量不足は設計の記述を深めて解消する）。

   ```bash
   python3 .cursor/skills/technology-stack-unified-design/scripts/validate_design_doc.py \
     tmp/tech-stack-reverse-candidate.md \
     --source-root <absolute-path> --survey-dir tmp/tech-stack-survey
   ```

7. [`quality-bar.md`](references/quality-bar.md) §7 の自己レビューを行い、PASS 後にユーザーへ `[要確認]`・`該当なし`・Appendix E の P0 項目・調査範囲の概要を提示する。既存成果物がある場合は上書きを AskQuestion で確認し、承認済みの場合だけ `--approve-overwrite` を付ける。

   ```bash
   python3 .cursor/skills/technology-stack-unified-design/scripts/publish_design_doc.py \
     --candidate tmp/tech-stack-reverse-candidate.md \
     --source-root <absolute-path> --survey-dir tmp/tech-stack-survey \
     [--approve-overwrite]
   ```

8. 出力 `docs/gen/<stack_slug>/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` をユーザーとレビューする。slug が §9 の技術スタックを適切に要約しているかも確認する。保管・Git・正本への昇格は [`draft-lifecycle.md`](references/draft-lifecycle.md) に従う。スキルは commit も正本昇格も行わない。

MUST の詳細な単一入口は `validate_design_doc.py` と [`document-skeleton.md`](references/document-skeleton.md)、品質の床は [`quality-bar.md`](references/quality-bar.md) §4（`document_quality.py` と 1 対 1）。構文だけを確認する場合に限り `--syntax-only`、本文品質を除く旧契約だけを確認する場合に限り `--structure-only` を使えるが、いずれも publish には使えない。publish 先は常に `docs/gen/<stack_slug>/` であり、`.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md` を上書きしない。

## 同梱ファイル

| ファイル | 役割 |
| --- | --- |
| `scripts/inspect_local_repository.py` | ローカル worktree の clean 状態・来歴の検証 |
| `scripts/survey_repository.py` | 全量走査（inventory / facts / shard / note 雛形）と台帳の完全性検査 |
| `scripts/assemble_candidate.py` | 部品の結合・frontmatter / 目次 / 調査範囲行の自動生成・台帳同期・検証 |
| `scripts/collect_ledger.py` | note の証跡候補の逐語検証・`[[path#L行]]` マーカーの台帳化・Appendix B の同期 |
| `scripts/validate_design_doc.py` / `scripts/document_quality.py` | 構造・来歴・証跡・本文品質・台帳・調査範囲の検査 |
| `scripts/publish_design_doc.py` | 検証済み候補の atomic publish |
| `references/quality-bar.md` | B 水準の定義・機械検査の床・事実/推定/未確定の書き分け |
| `references/section-playbook.md` | §1〜§24 と Appendix の作業手順・構造要素の形 |
| `references/shard-review-protocol.md` | 全量読解（shard / note / 証跡候補）の手順 |
| `references/document-skeleton.md` | 構造・§9・evidence・台帳の契約とコピー用骨格 |
| `references/evidence-signals.md` | 読むファイルの優先順・値の分類・除外リスト |
| `references/draft-lifecycle.md` | `docs/gen/` の保管・昇格 |

## 既知の制限

- `source_ref: "detached"` は detached HEAD の予約値で、同名 branch と区別しない。
- 全量読解の到達は**台帳の自己申告**である。validator は note の完全性（全可読ファイルの行・tier-1 の full・所見の分量・reviewed）と `調査範囲:` 行の一致を検査するが、AI が実際にファイルを開いたかは検査できない。`full` / `card` の内訳は本文の `調査範囲:` 行に出るため、読者が深さを判断できる。
- 台帳の引用は証跡ファイルに逐語で実在することを検査するが、**引用が主張を十分に裏付けるか**、§9 の意味的な正しさ、方針と観測の分類は機械検査しない。
- validator は Git LFS pointer を検出しない。調査時に先頭行を確認し、該当時は分析制限として記録する。
- ローカル HEAD が GitHub 上の最新かは確認しない。取得・revision 選択はユーザー責任とする。
- `stack_slug` が §9 の内容を十分に表すかは機械検査しない。同一 slug の既存成果物は衝突として扱い、明示承認なしに上書きしない。
- survey の import 解像度と facts 抽出は、Go・Python・JS/TS・JVM と主要な manifest / container / CI / proto / SQL / IaC 形式に対応する。他言語は構造 card が簡素（先頭コメント行）になるため、shard 読解で補う。
