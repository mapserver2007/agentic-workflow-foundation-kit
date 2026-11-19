# design-conformance — 必須要件（audit 判定基準）

> `audit.py` が検証する必須セクションの **設計根拠** を説明する。
> 機械可読な必須セクション一覧は `.cursor/skills/agentic-workflow-foundation/manifest.yaml > outputs[].required_sections` が SoT であり、
> 本ファイルはその各項目がなぜ必要かを人間向けに記録する（重複定義しない）。

## 監査の2軸

`audit.py` は次の2軸で exit code を返す（QUALITY_GATE exit code 3段階に準拠）。

1. **冪等性 / SoT 一元化**: 出力ファイル == immutable upstream docs + seed manifest + root `manifest.yaml` の per-project 値を overlay した一時 resolved manifest / templates の再生成結果。差分があれば「出力ファイルが直接編集された」= exit 1。
2. **required sections 準拠**: 既定の `audit.py` では各出力ファイルが `outputs[].required_sections` を全て含む。欠落は exit 1。consumer updater の候補検証だけは `--skip-seed-required-sections` を指定でき、適用対象外の既存 `mode: seed` は存在のみ検査する。
3. **致命的エラー**（テンプレート不在 / manifest 破損）は exit 2。
4. `project.*` / `session.*` の `[要確認]` 残存は **WARN（exit 0）**。確定は Phase 1.5 / 1.65 / 生成済み root `manifest.yaml` 設定の責務であり、生成基盤の欠陥ではないため FAIL にしない。キット配布時の初期状態を素の監査で壊さないことを優先する。

> **エンジン自体は監査の生成物対象外**: `audit.py` が検査するのは設定スキルの `outputs[]`（生成された出力ファイル）である。生成/監査エンジン `agentic-workflow-engine`（`generate.py` / `audit.py` / `genlib.py`）はどの設定スキルの `outputs` にも含まれないため、「出力 == 再生成結果」の冪等性検査の対象にならない。エンジンは設計符号化生成の出力ではなく、独立スキルとして工学仕様を正本に保守される。
>
> **resolved manifest は一時入力**: immutable upstream docs と root manifest overlay は foundation 固有の `run_resolved_engine.py` が担い、engine には解決済み skill-dir を渡す。これにより engine は統一設計書や root `manifest.yaml` を直接読まず、How ツールとしての境界を維持する。

## consumer updater の監査範囲

consumer updater は、対象アプリへ適用する `render` / `marker` 成果物と lock の差分を計画する。
kit が適用しない既存 seed（ADR / GOTCHAS / Domain docs / skill config）は project-owned
append-log または設定として保護し、内容を再生成・適用しない。そのため updater の候補検証だけは
`audit.py --skip-seed-required-sections` を使用し、seed のファイル存在を確認したうえで
`required_sections` の一致を要求しない。

このフラグは foundation の公開監査契約を変更しない。`bin/foundation-gate audit` / `self`
は既定のフラグなし経路で、seed の `required_sections` を含むテンプレート準拠検査を継続する。
seed の不在、未知の mode、テンプレート不在、render / marker の drift または必須要件欠落は、
consumer 経路でも引き続き失敗とする。

## 必須要件の設計根拠

### AGENTS.md（unified §12 Layer1）
- `## Workflow Pattern`: 開発型専用の宣言。
- `## Documentation Naming Convention`: §12 semantic 2層モデル（Meta=大文字 / Domain=kebab-case）。
- `## Agent Role` / `## Boundaries`: §13.3 宣言的制約 + bas Interaction Principles。
- `## Session Protocol`: 3構成要素（追跡ドキュメント/検証ゲート/再開プロトコル）の手続き SoT。
- `## Gotchas`: 原則8 自己改善サイクルのナビゲーションポインタ（`docs/GOTCHAS.md` への直接追記フローを参照）。

### .cursor/rules/02-agent-conduct.mdc（bas Agent Conduct）
- `Humble` / `Cautious` / `Thorough` / `Selective`: bas の4行動原則。各原則が宣言的制約として存在すること。

### .cursor/hooks.json（unified §13.5.2）
- `"version": 1`: Cursor 公式スキーマ。
- `sessionStart` / `stop`: Context Budget Auto-Handoff の最小構成イベント。

### .cursor/hooks/*.sh（unified §13.5 / ADR Context Budget）
- `guard-git-write.sh`: `beforeShellExecution` + `permission` deny/ask。`gh` CLI 全般と AI シェルからの credential store 取得を deny し、GitHub API / Git network operation は `github_access` の選択 provider を使う wrapper へ誘導する。wrapper 内 subprocess は Hook の直接入力外。raw AI SSH は論理禁止で、物理的な fail-closed 遮断はしない。
- `認証設定ファイルの読み取りはブロック`: `AGENTS.md > Boundaries > Never` の gh 設定ファイル・SSH 鍵の直接読み取り禁止を Hook で deterministic 強制する。
- `.env / .pem / .key ファイルの読み取りはブロック`: `AGENTS.md > Boundaries > Never` の秘匿ファイル直接読み取り禁止を Hook で deterministic 強制する。
- `security[[:space:]]+(find-generic-password|find-internet-password|dump-keychain) ]]`: Keychain deny クラスを解析不能入力でも fail-close する契約に由来する。
- `git[[:space:]]+credential[[:space:]]+(fill|approve|reject) ]]`: Git credential deny クラスを解析不能入力でも fail-close する契約に由来する。
- `session-bootstrap.sh`: `additional_context` で handoff manifest 注入。
- `session-budget-evaluator.sh`: `followup_message` で `[CONTEXT_BUDGET=...]` を AI に通知。
- **二段階フェイル戦略**: `session-*` 系と `guard-git-write.sh` の deny 対象以外はフェイルオープン（`{}` 素通り）。`guard-git-write.sh` の deny クラスのみフェイルクローズ（解析不能時 `ask`）。

### .cursor/hooks/README.md（Hook 運用契約）
- `find-generic-password|find-internet-password|dump-keychain`: Keychain の3 deny サブコマンドを fail-close 対象として運用文書に固定する。
- `git credential fill|approve|reject`: Git credential の3 deny アクションを fail-close 対象として運用文書に固定する。

### docs/DECISIONS.md（DECISIONS 運用ルール）
- `D-BOUNDARY` 〜 `D-PATTERN`: 8 つの設計次元の定義。
- `Significance` / `Alternatives Considered`: ADR テンプレートの必須セクション。

### docs/QUALITY_GATE.md（unified §9 / exit code）
- `exit code`: 3段階（0/1/2）の定義。
- `G-GEN`: OpenAPI 由来の生成を `G-BUILD` から分離し、開発中の自動生成 / 生成物差分確認を独立して扱うこと（合格条件は exit 0 かつ生成物差分なし=コミット済み）。
- `Hook`: §2.1 Deterministic 強制範囲。根拠列・`gh api` 書込/`gh pr comment` 等の ask 行・二段階フェイル戦略（deny=フェイルクローズ / それ以外=フェイルオープン）を含むこと。
- `リンク衛生`: 原則5 コンテキスト保護。
- `quality gate backend contract`: 承認済み `tech_contract.quality_gate` から導出された G-* backend argv とセマンティクスを、`package.json` の有無に依存せず復元できること。
- `検査 ID`: §1.4 スクリプト実装ゲートの安定検査 ID 命名規約（`G-{GATE}-{CATEGORY}-{NNN}`）。BAS Finding Code 79 種体系は採用せず軽量 ID 運用に留めること（`framework.accd_axes[B].not_adopted` の死守）。
- `セッション開始ゲート`: §1.5 クロスセッション整合性検査（handoff 未消費 / 追跡ドキュメント停滞 / agent_workflow 有効時の reports archive 取り残し・reports 停滞）の定義と検査 ID を含むこと。
- `フェーズ境界`: §3 追跡ドキュメント（`tracking_artifact`）ライフサイクルの各境界に出口/入口条件と出口検査を割り当てること。専用 `gate-*.py` は持たず既存ゲート + Advisory ループで運用する軽量実装であること。
- `cat ~/.config/gh/*`: `AGENTS.md > Boundaries > Never` の gh 認証設定ファイル直接読み取り禁止を secret 表へ投影する。
- `cat ~/.ssh/*`: `AGENTS.md > Boundaries > Never` の SSH 認証ファイル直接読み取り禁止を secret 表へ投影する。
- `cat .env`: `AGENTS.md > Boundaries > Never` の `.env` 直接読み取り禁止を secret 表へ投影する。
- `cat *.pem`: `AGENTS.md > Boundaries > Never` の PEM 認証ファイル直接読み取り禁止を secret 表へ投影する。
- `cat *.key`: `AGENTS.md > Boundaries > Never` の鍵ファイル直接読み取り禁止を secret 表へ投影する。

### docs/GOTCHAS.md（原則8）
- `起票トリガー`: 「期待と違う / 2回以上 / 想定外」の3トリガー。
- `Observe`: Observe → Amend → Evolve サイクル。

### docs/AGENT_RUNBOOK.md（unified Appendix E.4 / bas ACCD）
- `ACCD`: bas の5軸対応表。
- `5層モデル`: Context/Constraints/Capabilities/Automation/Delegation のマッピング。
- `復旧プロトコル`: セッション中断からの復旧手順。

### docs/CONTEXT_BUDGET.md（ADR Context Budget Auto-Handoff）
- `CONTEXT_BUDGET`: Yellow/Red プロトコル。
- `handoff-{session_id}.md`: manifest パス規約の SoT（並行セッション対応）。
- `## 生成根拠`: 設計入力の役割と入力状態が出力から確認でき（正本ファイル名・ハッシュは出力へ露出しない）、SKILL 内部に永続状態を持たないことを説明できること。
- `## なぜ必要か`: Lost in the Middle とコンテキストドリフトの運用リスクを利用者が理解できること。
- `## 構成`: Hook スクリプトと `.cursor/.session/` 状態ファイルの責務が復元可能であること。
- `## 各指標の更新タイミング`: prompt_count / shell_bytes の proxy 指標がいつ更新・リセットされるかを明示すること。
- `## チェックリスト`: 新メンバーが初回セットアップで Hook 登録・実行権限・state 生成を確認できること。
- `## 参考リンク`: 採用根拠（DECISIONS）・Hook 技術詳細・AI 振る舞い規範への安定リンクを提示し、判断の裏取り経路を保全すること。プロジェクト固有チケットや未検証の外部引用は焼き込まない（`framework.handoff.references` が SoT）。
- `並行セッション対応`: セッションごとの独立した handoff manifest（`handoff-{session_id}.md`）による並行セッション管理と、stale-handoff の検出・選択機構を説明できること。
- `意図的に採用しない設計`: 閾値の外部設定機構・個人別オーバーライドを YAGNI で非採用とし、manifest を SoT とする判断を復元可能にすること（`framework.handoff.non_goals`）。`将来拡張候補`（`framework.handoff.future_notes`）は preCompact による proxy 指標補完の方向性を残すこと（unified の preCompact 行が根拠）。

### docs/tech-stack.md（techstack §9）
- `技術スタック一覧とバージョン方針`: §9 の技術スタック表（レイヤ/技術/バージョン方針/備考）を Domain 層へ符号化したもの。テンプレート内のリンクは `project.tech_stack_design_filename`（manifest 値）で動的解決される。

### .cursor/skills/session-planning/SKILL.md（Layer 3 セッション管理）
- `name: session-planning`: Cursor skill としての識別子。
- `## 大規模タスクの検知`: セッション分割の発火条件。
- `## ワークフローパターン`: 開発型固定の宣言と追跡ドキュメントの対応。
- `## 追跡ドキュメント`: セッションをまたぐ作業状態の SoT。

### .cursor/skills/session-handover/SKILL.md（Layer 3 セッション管理）
- `name: session-handover`: Cursor skill としての識別子。
- `## 検証ゲート`: 完了宣言前のゲート実行記録。
- `## リンク衛生`: 再開に必要な一次情報の保全。
- `## 再開プロトコル`: 中断/圧縮後の復旧手順。

### .cursor/skills/campaign-cleanup/SKILL.md（runtime cleanup）
- `name: campaign-cleanup`: current campaign の runtime を保護する専用 skill の識別子。
- `apply`（既定、承認なし） / `inventory`（任意 dry-run）: `--current-session-id` による current campaign 解決と削除境界。
- `reports / Domain docs`: runtime cleanup の責務外を明示し、report archive と Domain docs 更新を混同しないこと。

### .cursor/skills/campaign-cleanup/scripts/campaign-cleanup.sh
- allowlist 内 runtime の current campaign 保護と、他 campaign runtime の承認なし apply を実装する。
- artifact の所属は current tracker と他 tracker の明示参照で判定する。どの tracker にも参照されず current tracker から所有キーも得られない artifact は、全体停止せず `undetermined (retained)` として保持する（tracker と artifact の削除循環を作らない）。

### .cursor/skills/session-handover/scripts/verification-gate.sh
- `session.verification.gate_command`: 生成済み root `manifest.yaml` の検証コマンドが展開されていること。
- `=== verification gate ===`: 実行ログでゲート実行を識別できること。

### .cursor/skills/session-handover/scripts/session-start-gate.sh
- `=== session-start gate ===`: 実行ログでゲート実行を識別できること。
- `G-SESSION-HANDOFF-001` / `G-SESSION-STALE-001` / `G-SESSION-DONE-001`: §1.5 の安定検査 ID で、handoff 未消費（WARN）、tracker mtime 停滞（WARN）、完了済み追跡ドキュメントの残存（WARN）を機械特定できること。`G-SESSION-STALE-001` は全 consumer で required_sections に含める。
- `G-SESSION-ARCH-001` / `G-SESSION-ARCH-002` / `G-SESSION-REPORT-001` は agent_workflow 有効時だけ描画する条件付き契約であり、feature 無効 consumer を壊さないため required_sections には追加しない。

## 設計判断: Domain docs の器は kit、Design Doc 由来の本文は domain-docs とする（D-SOT / D-BOUNDARY）

`designs/docs/` 直下の `*.md`（見本 `*.sample.md` を除く）を、PO が選ぶ per-project 入力とする。kit（foundation の生成プロセス）は Domain 層ドキュメントの器（見出し・節順・`[TODO]`・`tech_contract` 由来の節）だけを決定論で生成し、Design Doc を読まない。Design Doc はプロジェクトごとに作られ、その都度 Domain docs を更新するため、kit の初回生成で本文を埋める意味が小さい。本文の充填と更新は、seed の `outputs[]` から生成する `domain-docs` を単独で起動して行う。起案は起動したエージェント自身が行い、`scripts/domain_docs_apply.py` が検証して書き込む。

- **SoT**: Design Doc が上流入力、投影後の `docs/*` が日常の Domain 正本である。root `manifest.yaml > design_doc` は `source_path` と `source_fingerprint` の2キーで、最後に適用した Design Doc の変更検知にだけ使う（foundation の生成は書かない）。手で書いた節の更新は `maintenance-docs-workflow` が担う。
- **推論と書込みの分離**: domain-docs を起動したエージェントは docs を直接編集せず、`tmp/domain-docs-result.yaml` だけを書く。書込みは `domain_docs_apply.py` だけが行う。foundation の生成プロセスは本文を起案せず、`domain_docs_apply.py` を呼ばない。結果ファイルの検証を通らない限り、docs は変更されない。機械の柵は、`state` から `apply` の間の digest 検査（docs・manifest・Design Doc が変わっていないこと）だけで、従来から変わらない。起案エージェントは docs とコードベースを読んでよいが、書いてよいのは結果ファイルだけである。
- **Design Doc の選択方式**: 自動検知は行わない。起動したエージェントが `designs/docs/*.md`（見本を除く）を Glob で列挙し、root `manifest.yaml > design_doc.source_path` で固定済みのファイルに印を付け、`AskQuestion` で PO に1つ選ばせる（`PRD.md` など Design Doc でない文書が混じるときは注記する）。候補の列挙用サブコマンドは持たない。`--design-doc` は `tech_contract.py` の `--design-doc`（`.cursor/docs/` の技術スタック設計書）とは別物である。
- **マージとコード整合**: 起案は既存本文を起点にし、旧記述は、新しい Design Doc に根拠のある差分を除いて保持する。docs と新しい Design Doc の記述が矛盾したとき、および Design Doc とコードが食い違うときは、推測で決めず、推奨案を添えて `AskQuestion` で PO に確認する（「併記する」「両方残す」とは書かない）。コードベースがあれば、関連する実装（API、スキーマ、状態遷移）を読んで docs と照合する。照合は食い違いの報告に限り、コード由来の事実を本文に書かない（本文の出典は Design Doc と契約の guidance だけである）。
- **所有権表**: domain-docs が書ける節は `OWNERSHIP`（`domain_docs_apply.py`）で固定する（`ER図・関係性` を含む23節）。`参照` と各ファイルの前文は kit 所有で、書込みを拒否する。`spec_sections` / `architecture_sections` の契約節はテンプレートに受け皿が無く、対象にしない。所有権表とテンプレートの見出しは `test_domain_docs_apply.py` が突き合わせる。
- **`ER図・関係性`**: Design Doc のデータベース設計の記述から起こした Mermaid の `erDiagram` だけを書ける。画像リンクは拒否のままである（Design Doc の ER が画像でも、テーブルの記述から起こす）。エンティティ名は、適用後の `docs/data-models.md` の本文（ER 図以外）に実在するものに限り、雛形名（`ENTITY_A` など）は拒否する。`erDiagram` は他の節では拒否する。テーブルの記述が無ければ `omissions` で見送り、テンプレートに偽の図の雛形は残らない（テンプレートは `[TODO]` だけを持つ）。
- **契約節の例外（`api_sections` / `data_model_sections` / `workflow_sections`）**: 見出し名は consumer の契約が決めるため、固定の所有権表には入れない。kit が描画した器の `docs/api.md`、`docs/data-models.md`、`docs/workflows.md` で、見出し名がそのファイルの契約の配列（`CONTRACT_SECTION_KEYS`。resolved manifest から取る）の title と完全一致し、所有権表の節でも `参照` でもなく、引用段落と単独行の `[TODO]` だけでできている節を契約節（`placeholders`）とする。器から求めるので、既存ファイルの手書きの節は対象にならない。埋めてよいのは fill-only だけで、本文が器と完全一致する節に限る。apply は kit の引用を残して `[TODO]` だけを置換し、結果の `body` に引用を含めることを拒否する。update（`mode: refresh`）では対象にせず、結果に含めても拒否する。`state` が targets の `files[].guidance`（契約節名 → 引用の本文）で規約を渡す（targets の `schema_version` は 1 のまま、任意キーの追加）。本文の規則はファイルごとに `domain-docs` SKILL の `## 契約節` が定める。`api` は Design Doc に明示された JSON とエラー応答の外形に限り、型・シリアライザ・gRPC status・OpenAPI の required・各 API の JSON 例は書かない。`data-models` と `workflows` は引用の規約・手順を本文へ写し、引用にも Design Doc にも無い事実を補わない。契約節の `evidence` は、Design Doc の見出しのほかに固定値 `contract`（引用だけが根拠）を許可する。所有権表の節では `contract` を許可しない。
- **契約の起案規則**: `tech_contract.domain_docs.resolved` は技術スタック設計書の見出しの役割で節を選ぶ（起案プレイブック。`SKILL.md` の Phase 1.67）。guidance は技術規約に限り、業務語彙を入れない。`domain_docs_apply.py state` は、Design Doc のコードスパンの識別子が guidance に現れたとき WARN を出す（報告専用）。`tech_contract.py validate` は技術スタック設計書だけを入力に取るので、この検査は持たない。
- **結果ファイルの `schema_version`**: 1 と 2 を受け付ける。2 は `sections` と `spec_files` に任意の `supporting_evidence`（Design Doc に実在する見出しの配列）を許可する。targets の `schema_version` は 1 のままである。一意性・既存 slug との対応・README の根拠は、主根拠だけに適用する。update では、既存の機能仕様の補足に限り、主根拠の Design Doc 見出し実在検査を免除する（後述の「機能仕様（docs/spec/*.md）」）。
- **機能仕様の規則**: `body` は `## 概要` を必須とする。新しい機能仕様の主根拠は、Design Doc に `業務フロー` 見出しがあるとき、その直下の見出しに限る（細分化の防止。既存の機能仕様の根拠は変えない。見出しが無ければ検査しない）。`## エラーハンドリング` の欠落は `G-DOCFILL-005`（WARN）で報告する。
- **決定論ゲート（`domain_docs_gate.py`）**: apply が書込み前に、今回置換する本文と適用後の docs に対して `G-DOCFILL-001`（FAIL: `[TODO]` と雛形名の残存）、`002`〜`005`（WARN: 図の本数、テーブルと列、エンドポイント、エラーハンドリング節）を実行し、`tmp/domain-docs-findings.yaml` へ書く。FAIL は検証失敗（exit 1）、WARN は報告だけで修復を起動しない。数値の閾値と割合の指標は持たない（`docs/QUALITY_GATE.md` の「数値スコアリングをしない」に合わせる）。設計書が標準の見出し構造を持たない検査は `skipped` にする。
- **`apply --check` と修復**: 書込み・pin・片付けをせず、`apply` と同じ検証とゲートだけを実行する。update のとき（targets の `mode: refresh`）は `--refresh` を付ける。exit 1 のとき、起案エージェントは findings を読み、結果ファイルを最大 1 回だけ直し、再度 `--check` を実行する。2 回目も exit 1 なら PO へ報告して停止する。`--check` が PASS した後の `apply` は、直接編集の検知などを除き exit 1 にならない。
- **fill と update**: fill は、本文が kit の器と完全一致する節だけを埋める（手で書いた節と `maintenance-docs-workflow` の反映は変更しない）。update は、所有権表の全節を、既存本文を起点にマージした本文で置換する（更新しない節は `omissions` で既存本文を保つ）。update では手で書いた節も置換の対象になり、保持は `omissions` と承認で担保する（pin が無く手で書いた節がある docs も update になる）。engine（`generate.py`）は既存の seed を常にスキップし、Design Doc を一切知らない。fill の節の保持は `merge_seed_sections` を `domain_docs_apply.py` が再利用して行う。
- **update は承認付き**: update は `apply --refresh` で diff と digest を提示し、承認後に `--approve <digest>` で適用する。承認時は、起案エージェントが diff の `-` 行（削除・置換される旧記述）と、旧世代のまま残る契約節の件数と名前を要約して添える。見送り（`--decline`、docs 不変、fingerprint のみ更新）は、同じ Design Doc の stale だけに許す。switched / pin なし / 強制 update（`state --refresh`）では `--decline` は exit 2 とし、見送りは `apply` を実行しないことで表す（pin は動かず、反映していない Design Doc を既読にしない）。fingerprint は、fill の初回成功時（pin が無いとき）と、update の適用時、stale の `--decline` で更新する。
- **機能仕様（docs/spec/*.md）**: 件数と名前は Design Doc ごとに変わるため、seed の `outputs[]` には登録しない。`docs/spec.md` の機能仕様、`docs/spec/README.md` の収録仕様（行ごとに根拠見出しを併記）、`docs/spec/*.md` の3者が一致することを apply が検証する。再実行時は根拠見出しから既存の slug を引き当て、既存ファイルを再作成しない。結果から外した既存の slug は、変更も削除もしない（収録仕様の既存行と `docs/spec.md` のリンクも維持する）。別の Design Doc を根拠にした既存行は、今回の Design Doc に根拠の見出しが無くても正常な状態であり、`ORPHAN` の注記は出さない。update で既存の機能仕様を補足するときは、収録仕様の既存行の根拠が非空で、結果の `evidence` が既存行と一致するときだけ、`evidence` の Design Doc 見出し実在検査を免除する。この免除を使うときは、`supporting_evidence`（`schema_version: 2`）を1件以上必須にし、その見出しは今回の Design Doc に実在すること。既存行の根拠が空のとき、および fill では免除せず、従来どおり検査する。
- **原子性**: すべての検証が通ってから全ファイルを atomic に書く。途中で失敗したら書込み前へ戻す。戻せないときは変更したファイルを列挙して exit 2 にする。
- **状態境界**: Design Doc は `--design-doc` で PO が選ぶ（`designs/docs/` 直下の `*.md`。`..`、見本 `*.sample.md`、シンボリックリンク、存在しないファイルは exit 2）。固定済みの `design_doc` と比べた状態は `unpinned` / `fresh` / `stale` / `switched`（固定済みと別のファイルを選んだ。固定が指すファイルが消えていても、別のファイルを選べば switched）で、いずれも exit 0 で報告する。action は `skip`（対象なし）/ `fill`（器のままの節がある）/ `update`（stale / switched、pin が無く埋め済み、または `state --refresh`）である。「埋め済み」は、所有権表の節に本文が器と一致しないものがある状態を指す。fingerprint の形式不正は exit 2。
- **承認の要否**: fill に承認の AskQuestion は不要で、検証 PASS の apply がそのまま書込みまで行う。使う Design Doc の選択は、常に `AskQuestion`（推奨案を添える）で PO が行う。update は diff と digest の承認が要る。
- **意味検証の限界**: `evidence` は Design Doc 内の ATX 見出し名が存在することだけを機械検証する。決定論ゲートは、図の本数、テーブル名と列名、エンドポイント、必須見出しの有無といった構造だけを検査する。本文の意味的正確性（`docs` 間の記述の食い違いを含む）と、update で「旧内容を落とさず矛盾なく統合したか」は、機械で保証しない。担保は、承認時の diff（`-` 行）、矛盾時の PO への質問、承認なしでは書かない digest の3つと、PO の生成結果評価である。新しい Design Doc の内容をどの既存機能へ対応させるかは起案エージェントの判断であり、誤対応は承認時の diff で確認する。すでに埋まった契約節は fill-only のままで、旧世代の内容が残る（承認時の提示で件数と名前を報告する）。
- **実行タイミングと起動方式**: foundation の生成プロセス（generate / audit）の外で、domain-docs を単独で起動する。実行はキャンペーン外か実装開始前に限り、Step③以降の実差分は `G-WRITE-SCOPE-DOMAIN-001` が Domain docs の変更として拒否する。
- **ADR 境界**: これは kit 自身の生成仕様であり、`docs/DECISIONS.md` の「起票しないケース」に従い、適用先プロジェクトの ADR には記録しない。根拠は本節と seed manifest コメントに保持する。

### .cursor/skills/domain-docs/SKILL.md

seed の `outputs[]` から `mode: render` で生成する。feature 条件は付けない。適用スクリプトの書込み範囲は、所有権表と契約節（上記の例外）に限る。

- `name: domain-docs`: Cursor skill としての識別子。単独で起動する（`disable-model-invocation: true`。foundation の生成プロセスからは起動しない）。
- `## 起動手順`: 候補の列挙（Glob と root manifest）、`AskQuestion` での Design Doc 選択（推奨案つき）、`state --design-doc`、起案、`apply --check`（update は `--refresh`）、fill の `apply`、update の `apply --refresh` と承認、update 後の再 `state`。
- `tmp/domain-docs-result.yaml`: 起動したエージェントが書いてよい唯一のファイル。`## 入力と出力` は、選んだ Design Doc、targets、既存の Domain docs、コードベースを読んでよいと定める。
- `## マージとコード整合`: 既存本文を起点にしたマージ、既存の機能仕様の補足の書き方（`evidence` は既存行の根拠、`supporting_evidence` は今回の見出し）、矛盾時の `AskQuestion`、コードは食い違いの報告に限る規則、承認時の提示項目を定める。
- `## 所有権表`: `domain_docs_apply.py` の `OWNERSHIP` と同じ節を手順に持つ。
- `## 持ち込む内容`: Design Doc に記載があれば落とさず持ち込む項目を、ファイルごとに定める。記載が無い項目は書かず、`omissions` に理由を書く。
- `## 図の引継ぎ`: sequence と state の Mermaid を `docs/workflows.md` へ引き継ぐ規則。本数は Design Doc 以上。見本の図を写さない。
- `## 契約節`: `files[].placeholders` の節だけ、`[TODO]` の置換文を書く。ファイルごとの本文規則（`api` は外形に限る、`data-models` と `workflows` は引用の規約・手順を写す）と `evidence: contract` を定める。
- `docs/spec/{slug}.md`: 機能仕様の出力先。`docs/spec.md` の機能仕様、`docs/spec/README.md` の収録仕様と3者一致させる。

### .cursor/skills/agent-maintenance-docs/SKILL.md（feature: agent_workflow.maintenance_docs）
- `name: agent-maintenance-docs`: Cursor skill としての識別子。
- `## 責務範囲`: docs 反映 + archives 移動の責務テーブル。
- `G-DOC-SPEC`: Domain 層ドキュメント仕様反映ゲートのスコープ定義。
- `責務境界テーブル`: Meta 層（AGENTS.md 等）を除外する責務境界。AGENTS.md 技術スタック欄の除外根拠（SoT フロー一方向 / Boundaries 違反）を含むこと。

### .cursor/skills/deep-thinking/SKILL.md（feature: deep_thinking）
- `name: deep-thinking`: Cursor skill としての識別子。
- `## 内部フロー`: Phase 1〜6 の構造的評価フロー（入力解析→ブリーフ作成→A/B 並列分析→統合裁定→再審→応答生成）が存在すること。
- `## 応答の契約`: 応答品質基準（一次証跡優先の採用順位）と禁止事項が定義されていること。
- `応答品質の基準`: 一次証跡の直接性 → 問いへの適合性 → 再現可能性 → A/B の一致、の採用順位。
- `高影響領域`: `config.yaml > high_impact_categories` を SoT とする判断基準。

### .cursor/skills/deep-thinking/config.yaml（feature: deep_thinking / seed）
- `models`: A（推進分析）/ B（反証分析）のモデル割り当てが定義されていること。C（裁定者）はスキルを呼び出す親エージェントであり、そのモデルは呼び出し時に選択する。SKILL.md の起動前チェックが config.yaml から A/B のモデル設定を読み込み、同一モデル時は `MODEL_HOMOGENEOUS` を記録する前提。
- `execution`: `max_rounds` / `max_rebuttal_turns_per_issue` / `max_issues_per_round` / `model_unavailable` / `stop_when` 等の実行パラメータが定義されていること。
- `high_impact_categories`: 高影響カテゴリの機械可読な分類値一覧が定義されていること。SKILL.md の高影響判定はこの列挙のみで行い、非定義語での運用判断を許容しない。

## 設計判断: runtime 物質化の `outputs[]` 対象外（D-SOT / D-QUALITY）

Phase 1.68 で `provision_runtime --apply` が materialize する `package.json` / `tsconfig.json` / `pnpm-workspace.yaml` は **`outputs[]` / audit の対象外**。`materialize_runtime.py` は `--check` のみ（write 禁止）。

- **理由**: runtime file の所有権と更新方式は、承認済み `tech_contract.runtime_materialization.actions` が決定する。`json-key-merge` は宣言した owned keys を更新し、`owned-text-render` は契約で指定した完全内容を materialize する。いずれも `outputs[]` の byte-for-byte audit から分離する。
- **整合性の担保**: Phase 1.7（`check_tech_stack_conformance.py`）が承認済み `tech_contract.provisioning.preflight_checks` を generic に評価する（subprocess 禁止）。`json-value-pattern` は契約が宣言した形式 pattern への `re.fullmatch` のみ（版の数値は持たない）。`installed-marker` は closed `validation` object（`json-field` / `executable-file`）で marker 内容を意味検証し、`covers_packages` は schema で `required_packages` を exact cover する。`forbidden_packages` は `absent-marker` + `covers_packages` で exact cover する。
- **postcondition ordering**: command 直後は postcondition が生成する marker を除いた command-owned `writes` のみ存在検査。postcondition 実行（atomic marker write）後に全 `writes` を再検査し、`changed_targets` を digest 差分で再収集する。
- **postcondition plan 境界**: postcondition の全 payload は親 command の `payload_digest` と承認 plan に含める。`capture-toolchain-version` の subprocess は PATH 上の executable 名 + closed version-query 引数1個だけを許可し、任意 path / script / eval 引数を schema と runtime の双方で拒否する。marker write は plan の `effects` / `writes` に明示する。version query 前後の project tree metadata snapshot に差分があれば exit 2 とし、未宣言変更 path を部分適用レポートへ含める。
- **state-digests**: apply 後に記録した manifest/lockfile digest を preflight の `state-digests` check が marker 記録値と比較する。全対象 path の存在が必須で、`absent` digest の記録・比較は拒否する。
- **exit 境界**: 修正可能な command nonzero=1、missing executable / postcondition 不能 / schema 不正 / 環境不能=2。traceback 禁止。
- **導出方式**: tech 依存値は承認済み `tech_contract` の構造化データから投影する。consumer は契約を解釈せず、技術名・カテゴリ・外部 registry への fallback を持たない。

## 設計判断: command `writes` 宣言境界（D-QUALITY / D-BOUNDARY）

`provisioning.command_actions` で `project_write` / `lockfile_write` effect を宣言する action は **非空 `writes` 必須**（schema 拒否）。apply は command 前後に宣言 path の digest を比較し、変更を `changed_targets` へ記録する。

- **検知限界**: 宣言外 path への変更を OS レベルで完全検知することは不可能。契約境界として **宣言漏れは schema で拒否**し、宣言済み path の変更のみ機械追跡する。
- **host_write-only**: `host_write` / `network` のみの action は project `writes` 不要。
- **read-only preflight**: preflight は subprocess を起動せず、宣言的 check（`installed-marker` / `absent-marker` / `json-value-pattern` / `state-digests` / lockfile-present 等）のみ。`installed-marker` は `validation` 成功時のみ package coverage として扱い、schema が `covers_packages` exact cover を検証する。
- **writes → ignore 投影（ADR-0001）**: `contract_projection.project_ignore_dirs` が `writes` / postcondition `marker` の先頭ドットディレクトリだけを `project.ignore_dirs` へ投影し、`.gitignore` managed ブロックが消費する。ルート直下ファイルと技術名推論は対象外。`.cursorignore` には投影しない。

## 設計判断: quality_gate_contract の非永続化（D-SOT / D-QUALITY）

`quality_gate_contract`（quality gate backend contract の具体文言）は **root `manifest.yaml` に永続化しない**。

- **SoT**: 承認済み `tech_contract.quality_gate`。同一契約なら同一出力となる。
- **描画経路**: Phase 2 generate 直前に `run_resolved_engine.py` が承認済み contract の値を一時 resolved manifest へ overlay 注入し、`docs/QUALITY_GATE.md` 等へ展開する。
- **Phase 1.65 の責務**: `project.quality_gate.*_cmd`（抽象 backend）と `session.verification.gate_command` のみ root へ書き込む。移行時は既存 root の `quality_gate_contract` ブロックを削除する。
- **Follow-up**: なし（loop 4 で `gen_artifact_paths` を `tech_contract.quality_gate` へ統一済み）。

## 設計判断: 承認済み tech_contract の consumer 境界（ADR-0002）

`tech_contract` は技術設計書から対話 SKILL が起案し、`scripts/tech_contract.py` の
schema・canonical digest・source fingerprint・approval 検査を通過した後だけ root
manifest へ pin する派生 SoT である。品質ゲート、runtime、review、Domain docs の
tech 依存値はこの契約を consumer とし、registry の live compose や runtime LLM
fallback を持たない。

- **安全境界**: `apply` は root manifest 全体 preimage を再照合し、tool-owned
  `tech_contract` block だけを atomic replace する。未承認 draft は manifest、host、
  dependencies、lockfile を変更できない。
- **実行境界**: contract command は shell string ではなく argv とし、pipe、redirect、
  command substitution、secret 参照、破壊的コマンドを検証時に拒否する。
- **Provisioning**: `bin/project-setup --plan` は read-only、`--apply --plan-file` は
  contract digest と各 target preimage が一致する場合だけ実行する。品質ゲートは
  `--preflight` と同等の read-only 検査以外の install/network/write を行わない。

## 設計判断: 契約に版の数値を持たない（D-QUALITY / D-DEPENDENCY）

`tech_contract` の file action の `content`、preflight、postcondition、command の `argv` に、版の数値（exact・範囲・pattern 内の数字）を書かない。版の正本はプロジェクト自身の宣言ファイル（契約が宣言する path）だけとし、契約の検査は存在と形式に限る。

- **決定**: preflight / postcondition の `pattern` は数字クラスで書く形式 pattern にし、`installed-marker` は `name` など版以外のフィールドで識別する。command の `argv` には版を渡さず、依存は名前だけを command で追加する。版の解決と充足は、command が起動する各エコシステムのツール（install / build）が担保し、lockfile が記録する。
- **理由**: 版が契約内の複数箇所（file action、preflight、postcondition、command の `argv`）に重なると、プロジェクトが版を更新したときに preflight が不一致になり、契約の再起案と再承認が要る。契約に宣言の写しがあると、版の正本が二つになる。設計書 §9 のバージョン方針セルは `宣言:` / `[要確認]` / `—` でエコシステムごとの記法になり、範囲 pattern への変換は言語別の解釈を要する。
- **対象外**: `tech_stack.items[].version_policy` の Domain 要約表示（`docs/tech-stack.md`）。設計書から写すだけで、検査には使わない。
- **戻さないもの**: registry からの版取得は、ADR-0002 の consumer 境界により戻さない。
- **移行**: 既存の封印済み契約は kit の更新では自動で直らない。版の数値を持つ契約は、再起案（`tech_contract.py validate --check` → 承認 → `apply`）で置き換える。`load_approved` は読み込みのたびに `validate` を実行するため、この方針は schema の拒否条件にはしない（既存契約を壊さない）。
- **非採用**: 設計書のバージョン方針セルから範囲を導く案（記法が言語ごとに違う）、言語・ツールごとの記述表を kit に持つ案（新しい言語に対応できない）。

## 設計判断: root manifest の `outputs` 非保持（D-SOT）

`outputs[]`（生成カタログ）は **seed manifest が単一 SoT** であり、root manifest には保持しない。

- **根拠**: `resolved_manifest()` は seed を基底にし、root からは `ROOT_OVERLAY_KEYS` のみ overlay する。`outputs` は `ROOT_OVERLAY_KEYS` に含まれず、非テストの全スクリプトに root `outputs` の消費者が存在しない。root に複製しても生成に使われない死蔵であり、drift 源になる。
- **bootstrap の責務**: 新規 root 生成時は seed から `outputs` / `quality_gate_contract` を除去して書き出す。既存 root からも framework 同期後に同ブロックを除去する。

## 設計判断: フェーズ境界 / セッション開始ゲートの実装層（D-QUALITY）

QUALITY_GATE の本番運用比較で挙がった「フェーズ境界ゲート / セッション開始ゲート / 安定検査 ID の不在」を、**`framework.accd_axes[B].adopted` のシェルゲート層に厳密スコープ**して塞いだ。

- **採用（adopted 枠内）**: `verification-gate.sh` と同クラスのシェルゲート（`session-start-gate.sh`）、`G-{GATE}-{CATEGORY}-{NNN}` の軽量検査 ID、追跡ドキュメントライフサイクルのフェーズ境界表（Advisory ループ運用）。
- **非採用（not_adopted 死守）**: BAS の Finding Code 79 種体系、Deterministic Guard の数値判定基盤（スコアリング / 重み付け）。重量型の機械判定エンジンは本キットのスコープ外。
- **判断根拠**: 機構（`session-bootstrap.sh` / handoff manifest / `archive/` 境界）は既に存在し、それを検証するシェルゲートは axis B が既に adopted としているクラスと同一。重量インフラを伴わずに Advisory（~80%）の隙間を機械強制で補える。

## 必須要件を増減する場合

必須要件を追加する場合は:
1. `.cursor/skills/agentic-workflow-foundation/manifest.yaml > outputs[].required_sections` に文字列を追加。
2. 本ファイルにその設計書由来を1行追記。
3. 対応するテンプレートに当該セクションを追加。
4. upstream docs から resolver が展開する項目の場合は、`run_resolved_engine.py` が一時 resolved manifest にのみ書き込み、seed manifest/templates を実行結果で永続更新しないことを確認する。
