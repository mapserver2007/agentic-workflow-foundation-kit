# shard 読解プロトコル（全量読解の実行手順）

`survey_repository.py survey` が作った shard を 1 つずつ読み、台帳（note）を完成させる手順。オーケストレータ（親エージェント）は shard ごとに sub-agent を並列起動してよい。sub-agent には **このファイルのパスと担当 shard 番号・source root・survey dir** だけを渡せば足りる。

## 目的

統一設計書の本文を、代表ファイルの印象ではなく **全可読ファイルの読解** に基づいて書く。deterministic な走査（survey）は全ファイルの構造 card を作る。この手順は、その上で人間（AI）が読んだ範囲を `level` として台帳に記録し、読んだ根拠のある所見を残す。

## 禁止（MUST）

- 対象 worktree への書き込み、build / test / install、`git` の状態変更、ネットワーク取得。読み取り専用の `Read` / `Grep` / `rg` / `git ls-files` / `git grep` だけを使う。
- 書き込みは担当 shard の note（`<survey-dir>/notes/shard-NN.note.md`）だけ。他の shard の note・inventory・facts は編集しない。
- secret の値（password / token / key / credential）を note に書かない。環境変数は名前だけ。ローカル絶対パスを書かず、source root 相対パスだけを使う。
- 開いていないファイルを `full` にしない。台帳行の追加・削除・path 変更をしない。

## 手順

1. `<survey-dir>/shards/shard-NN.md` を読む。担当ファイルと structural card（package・型・関数・internal import・proto の service/rpc・SQL table など）が並ぶ。`T1` は tier-1。
2. **tier-1 は全文を読む（MUST）**: manifest / build / ci / container / iac / contract / schema / readme。台帳の level を `full` にする。
3. それ以外は、次の優先順で **全文を読む**（SHOULD。時間・分量の許す限り）。読み切れない残りは card を精査し `card` のままにする。
   1. entrypoint（`main`）、DI / wiring、設定・環境変数の読込
   2. interface / port 定義、domain の型・不変条件、usecase の入口
   3. adapter / repository 実装、外部 SDK・DB・queue との境界、認証・認可、middleware / interceptor
   4. テスト（テスト方式・fixture・mock の作り方が分かる代表）
   5. 残り（類似構造が繰り返されるファイルは、代表を全文読み、他は card と grep で差異を確認する）
4. 台帳 `## ファイル台帳` の各行 `- <path> :: <level> :: <card>` で、全文を開いたファイルの level を `card` → `full` に変える。多数を一括変更する場合は `python3` の小スクリプトで path 完全一致置換してよい（開いたファイルだけ）。
5. `## 所見` を書き、frontmatter の `reviewed: no` を `reviewed: yes` に変える。**1,000〜2,500 字**を目安に、次を具体的に書く。
   - (a) この shard の責務と構造（ディレクトリ → 役割）
   - (b) 反復して現れる設計パターン・規約（命名・層・エラー処理・DI・テスト方式）。**どのファイルで確認したか**を相対パスで示す
   - (c) 使用技術・外部依存と境界（DB / 外部 API / SDK / 生成物の入力）
   - (d) 他 shard・他層への依存方向（import の向き、呼び出しの向き）
   - (e) 設計判断が読み取れる箇所（コメント・ADR への言及・非対称な実装・TODO・移行途中の痕跡）
   - (f) 逸脱・不整合・技術的負債の疑い（件数と代表例）
   推測は「推定」と明示する。ファイルから判断できない採用理由を事実として書かない。
6. 最終返信（400 字以内）: 担当 shard、full / card 件数、最重要の発見 3 点、懸念（読めなかった範囲）。

## 品質基準

- 「ファイル一覧の言い換え」は所見ではない。**このコードベースが何を、どの規約で、なぜそう作っているか**が読み取れる記述にする。
- 同じパターンが N 件ある場合は、件数と代表 2〜3 件のパスを書く。例外（パターンから外れるファイル）は必ず挙げる。
- 外部境界（HTTP・gRPC・DB・queue・外部 SDK・認証）は、入口ファイルと設定の読込箇所を所見に含める。

## オーケストレータ向け

- shard 数が多い場合は、**1 メッセージで複数 sub-agent を並列起動**する。sub-agent の最終返信は要約だけで、本体は note に残る。
- 全 shard 完了後、`survey_repository.py check --survey-dir <dir> --source-root <root>` が PASS することを確認する。PASS しない場合は、列挙された shard だけを再依頼する。
- 親は全 note の `## 所見` を読み、設計書の本文に統合する。本文の根拠は、親が対象ファイルの該当行を開いて確かめ、`evidence: path#L行` で示す。
