# design-conformance — 必須要件（audit 判定基準）

> `audit.py` が検証する必須セクションの **設計根拠** を説明する。
> 機械可読な必須セクション一覧は `.cursor/skills/agentic-workflow-foundation/manifest.yaml > outputs[].required_sections` が SoT であり、
> 本ファイルはその各項目がなぜ必要かを人間向けに記録する（重複定義しない）。

## 監査の2軸

`audit.py` は次の2軸で exit code を返す（QUALITY_GATE exit code 3段階に準拠）。

1. **冪等性 / SoT 一元化**: 出力ファイル == immutable upstream docs + seed manifest + root `manifest.yaml` の per-project 値を overlay した一時 resolved manifest / templates の再生成結果。差分があれば「出力ファイルが直接編集された」= exit 1。
2. **required sections 準拠**: 各出力ファイルが `outputs[].required_sections` を全て含む。欠落は exit 1。
3. **致命的エラー**（テンプレート不在 / manifest 破損）は exit 2。
4. `project.*` / `session.*` の `[要確認]` 残存は **WARN（exit 0）**。確定は Phase 1.5 / 1.65 / 生成済み root `manifest.yaml` 設定の責務であり、生成基盤の欠陥ではないため FAIL にしない。キット配布時の初期状態を素の監査で壊さないことを優先する。

> **エンジン自体は監査の生成物対象外**: `audit.py` が検査するのは設定スキルの `outputs[]`（生成された出力ファイル）である。生成/監査エンジン `agentic-workflow-engine`（`generate.py` / `audit.py` / `genlib.py`）はどの設定スキルの `outputs` にも含まれないため、「出力 == 再生成結果」の冪等性検査の対象にならない。エンジンは設計符号化生成の出力ではなく、独立スキルとして工学仕様を正本に保守される。
>
> **resolved manifest は一時入力**: immutable upstream docs と root manifest overlay は foundation 固有の `run_resolved_engine.py` が担い、engine には解決済み skill-dir を渡す。これにより engine は統一設計書や root `manifest.yaml` を直接読まず、How ツールとしての境界を維持する。

## 必須要件の設計根拠

### AGENTS.md（unified §12 Layer1）
- `## Workflow Pattern`: §3 の3パターン分類を宣言（開発/パイプライン/ドキュメント型）。
- `## Documentation Naming Convention`: §12 semantic 2層モデル（Meta=大文字 / Domain=kebab-case）。
- `## Agent Role` / `## Boundaries`: §13.3 宣言的制約 + bas Interaction Principles。
- `## Session Protocol`: 3構成要素（追跡ドキュメント/検証ゲート/再開プロトコル）の手続き SoT。
- `## Gotchas`: 原則8 自己改善サイクルの入口（起票トリガー必須）。

### .cursor/rules/02-agent-conduct.mdc（bas Agent Conduct）
- `Humble` / `Cautious` / `Thorough` / `Selective`: bas の4行動原則。各原則が宣言的制約として存在すること。

### .cursor/hooks.json（unified §13.5.2）
- `"version": 1`: Cursor 公式スキーマ。
- `sessionStart` / `stop`: Context Budget Auto-Handoff の最小構成イベント。

### .cursor/hooks/*.sh（unified §13.5 / ADR Context Budget）
- `guard-git-write.sh`: `beforeShellExecution` + `permission` deny/ask（Advisory→Deterministic 昇格）。
- `session-bootstrap.sh`: `additional_context` で handoff manifest 注入。
- `session-budget-evaluator.sh`: `followup_message` で `[CONTEXT_BUDGET=...]` を AI に通知。
- フェイルオープン（`{}` 素通り）が全 hook の共通設計。

### docs/DECISIONS.md（DECISIONS 運用ルール）
- `D-BOUNDARY` 〜 `D-PATTERN`: 8 つの設計次元の定義。
- `Significance` / `Alternatives Considered`: ADR テンプレートの必須セクション。

### docs/QUALITY_GATE.md（unified §9 / exit code）
- `exit code`: 3段階（0/1/2）の定義。
- `G-GEN`: OpenAPI 由来の生成を `G-BUILD` から分離し、開発中の自動生成 / 生成物差分確認を独立して扱うこと。
- `Hook`: §2.1 Deterministic 強制範囲。
- `リンク衛生`: 原則5 コンテキスト保護。
- `package script contract`: `package.json` 未生成段階でも、技術スタックから導出された G-* の内訳を復元できること。

### docs/GOTCHAS.md（原則8）
- `起票トリガー`: 「期待と違う / 2回以上 / 想定外」の3トリガー。
- `Observe`: Observe → Amend → Evolve サイクル。

### docs/AGENT_RUNBOOK.md（unified Appendix E.4 / bas ACCD）
- `ACCD`: bas の5軸対応表。
- `5層モデル`: Context/Constraints/Capabilities/Automation/Delegation のマッピング。
- `復旧プロトコル`: セッション中断からの復旧手順。

### docs/session-handoff-guide.md（ADR Context Budget Auto-Handoff）
- `CONTEXT_BUDGET`: Yellow/Red プロトコル。
- `handoff-active.md`: manifest パス規約の SoT。
- `## 生成根拠`: immutable upstream docs の入力状態と fingerprint が出力から確認でき、SKILL 内部に永続状態を持たないことを説明できること。
- `## なぜ必要か`: Lost in the Middle とコンテキストドリフトの運用リスクを利用者が理解できること。
- `## 構成`: Hook スクリプトと `.cursor/.session/` 状態ファイルの責務が復元可能であること。
- `## 各指標の更新タイミング`: elapsed / prompt_count / shell_bytes の proxy 指標がいつ更新・リセットされるかを明示すること。
- `## チェックリスト`: 新メンバーが初回セットアップで Hook 登録・実行権限・state 生成を確認できること。
- `単一 manifest 制約`: `handoff-active.md` の誤 consume と並行キャンペーン非対応を明示し、手動退避で事故を回避できること。

### docs/tech-stack.md（techstack §9）
- `技術スタック一覧とバージョン方針`: §9 の技術スタック表（レイヤ/技術/バージョン方針/備考）を Domain 層へ符号化したもの。
- `TECHNOLOGY_STACK_UNIFIED_DESIGN.md`: per-project 入力への逆参照ポインタ。

### .cursor/skills/session-planning/SKILL.md（Layer 3 セッション管理）
- `name: session-planning`: Cursor skill としての識別子。
- `## 大規模タスクの検知`: セッション分割の発火条件。
- `## パターン選択フロー`: `workflow_pattern` と追跡ドキュメントの対応。
- `## 追跡ドキュメント`: セッションをまたぐ作業状態の SoT。
- `## Gotchas`: 運用失敗の Observe → Amend → Evolve 入口。

### .cursor/skills/session-handover/SKILL.md（Layer 3 セッション管理）
- `name: session-handover`: Cursor skill としての識別子。
- `## 検証ゲート`: 完了宣言前のゲート実行記録。
- `## リンク衛生`: 再開に必要な一次情報の保全。
- `## 再開プロトコル`: 中断/圧縮後の復旧手順。
- `## Gotchas`: 運用失敗の Observe → Amend → Evolve 入口。

### .cursor/skills/session-handover/scripts/verification-gate.sh
- `session.verification.gate_command`: 生成済み root `manifest.yaml` の検証コマンドが展開されていること。
- `=== verification gate ===`: 実行ログでゲート実行を識別できること。

### .cursor/skills/decisions-record/SKILL.md
- `name: decisions-record`: Cursor skill としての識別子。
- `D-BOUNDARY`: ADR 起票対象の設計次元を含むこと。
- `Alternatives Considered`: 判断理由を復元可能にすること。
- `## Gotchas`: ADR 運用失敗の Observe → Amend → Evolve 入口。

## 必須要件を増減する場合

必須要件を追加する場合は:
1. `.cursor/skills/agentic-workflow-foundation/manifest.yaml > outputs[].required_sections` に文字列を追加。
2. 本ファイルにその設計書由来を1行追記。
3. 対応するテンプレートに当該セクションを追加。
4. upstream docs から resolver が展開する項目の場合は、`run_resolved_engine.py` が一時 resolved manifest にのみ書き込み、seed manifest/templates を実行結果で永続更新しないことを確認する。
