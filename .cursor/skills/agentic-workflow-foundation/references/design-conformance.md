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
- `## Gotchas`: 原則8 自己改善サイクルのナビゲーションポインタ（`docs/GOTCHAS.md` への直接追記フローを参照）。

### .cursor/rules/02-agent-conduct.mdc（bas Agent Conduct）
- `Humble` / `Cautious` / `Thorough` / `Selective`: bas の4行動原則。各原則が宣言的制約として存在すること。

### .cursor/hooks.json（unified §13.5.2）
- `"version": 1`: Cursor 公式スキーマ。
- `sessionStart` / `stop`: Context Budget Auto-Handoff の最小構成イベント。

### .cursor/hooks/*.sh（unified §13.5 / ADR Context Budget）
- `guard-git-write.sh`: `beforeShellExecution` + `permission` deny/ask（Advisory→Deterministic 昇格）。`gh` CLI 全般を deny し、GitHub API 操作は wrapper (`bin/github-pr-*-safe`) 経由へ誘導する。`deny_class_failclose` で deny クラスは入力解析不能時もフェイルクローズ（`ask`）。
- `session-bootstrap.sh`: `additional_context` で handoff manifest 注入。
- `session-budget-evaluator.sh`: `followup_message` で `[CONTEXT_BUDGET=...]` を AI に通知。
- **二段階フェイル戦略**: `session-*` 系と `guard-git-write.sh` の deny 対象以外はフェイルオープン（`{}` 素通り）。`guard-git-write.sh` の deny クラスのみフェイルクローズ（解析不能時 `ask`）。

### docs/DECISIONS.md（DECISIONS 運用ルール）
- `D-BOUNDARY` 〜 `D-PATTERN`: 8 つの設計次元の定義。
- `Significance` / `Alternatives Considered`: ADR テンプレートの必須セクション。

### docs/QUALITY_GATE.md（unified §9 / exit code）
- `exit code`: 3段階（0/1/2）の定義。
- `G-GEN`: OpenAPI 由来の生成を `G-BUILD` から分離し、開発中の自動生成 / 生成物差分確認を独立して扱うこと（合格条件は exit 0 かつ生成物差分なし=コミット済み）。
- `Hook`: §2.1 Deterministic 強制範囲。根拠列・`gh api` 書込/`gh pr comment` 等の ask 行・二段階フェイル戦略（deny=フェイルクローズ / それ以外=フェイルオープン）を含むこと。
- `リンク衛生`: 原則5 コンテキスト保護。
- `package script contract`: 技術スタックから導出された G-* の内訳を、`package.json` の有無に依存せず復元できること。
- `検査 ID`: §1.4 スクリプト実装ゲートの安定検査 ID 命名規約（`G-{GATE}-{CATEGORY}-{NNN}`）。BAS Finding Code 79 種体系は採用せず軽量 ID 運用に留めること（`framework.accd_axes[B].not_adopted` の死守）。
- `セッション開始ゲート`: §1.5 クロスセッション整合性検査（handoff 未消費 / 追跡ドキュメント停滞 / `archive/` 取り残し）の定義と検査 ID を含むこと。
- `フェーズ境界`: §3 追跡ドキュメント（`tracking_artifact`）ライフサイクルの各境界に出口/入口条件と出口検査を割り当てること。専用 `gate-*.py` は持たず既存ゲート + Advisory ループで運用する軽量実装であること。

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
- `技術スタック一覧とバージョン方針`: §9 の技術スタック表（レイヤ/技術/バージョン方針/備考）を Domain 層へ符号化したもの。
- `TECHNOLOGY_STACK_UNIFIED_DESIGN.md`: per-project 入力への逆参照ポインタ。

### .cursor/skills/session-planning/SKILL.md（Layer 3 セッション管理）
- `name: session-planning`: Cursor skill としての識別子。
- `## 大規模タスクの検知`: セッション分割の発火条件。
- `## パターン選択フロー`: `workflow_pattern` と追跡ドキュメントの対応。
- `## 追跡ドキュメント`: セッションをまたぐ作業状態の SoT。

### .cursor/skills/session-handover/SKILL.md（Layer 3 セッション管理）
- `name: session-handover`: Cursor skill としての識別子。
- `## 検証ゲート`: 完了宣言前のゲート実行記録。
- `## リンク衛生`: 再開に必要な一次情報の保全。
- `## 再開プロトコル`: 中断/圧縮後の復旧手順。

### .cursor/skills/session-handover/scripts/verification-gate.sh
- `session.verification.gate_command`: 生成済み root `manifest.yaml` の検証コマンドが展開されていること。
- `=== verification gate ===`: 実行ログでゲート実行を識別できること。

### .cursor/skills/session-handover/scripts/session-start-gate.sh
- `=== session-start gate ===`: 実行ログでゲート実行を識別できること。
- `G-SESSION-HANDOFF-001` / `G-SESSION-DONE-001`: §1.5 の安定検査 ID で、handoff 未消費（WARN）と完了済み追跡ドキュメントの残存（WARN）を機械特定できること。`verification-gate.sh` と同クラスのシェルゲート（軽量実装 / 数値判定なし）として実装すること。

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

## 設計判断: フェーズ境界 / セッション開始ゲートの実装層（D-QUALITY）

QUALITY_GATE の本番運用比較で挙がった「フェーズ境界ゲート / セッション開始ゲート / 安定検査 ID の不在」を、**`framework.accd_axes[B].adopted` のシェルゲート層に厳密スコープ**して塞いだ。

- **採用（adopted 枠内）**: `verification-gate.sh` と同クラスのシェルゲート（`session-start-gate.sh`）、`G-{GATE}-{CATEGORY}-{NNN}` の軽量検査 ID、追跡ドキュメントライフサイクルのフェーズ境界表（Advisory ループ運用）。
- **非採用（not_adopted 死守）**: BAS の Finding Code 79 種体系、Deterministic Guard の数値判定基盤（スコアリング / 重み付け）。重量型の機械判定エンジンは「経営型」ワークフローでのみ検討対象とし、開発型では作らない。
- **判断根拠**: 機構（`session-bootstrap.sh` / handoff manifest / `archive/` 境界）は既に存在し、それを検証するシェルゲートは axis B が既に adopted としているクラスと同一。重量インフラを伴わずに Advisory（~80%）の隙間を機械強制で補える。

## 必須要件を増減する場合

必須要件を追加する場合は:
1. `.cursor/skills/agentic-workflow-foundation/manifest.yaml > outputs[].required_sections` に文字列を追加。
2. 本ファイルにその設計書由来を1行追記。
3. 対応するテンプレートに当該セクションを追加。
4. upstream docs から resolver が展開する項目の場合は、`run_resolved_engine.py` が一時 resolved manifest にのみ書き込み、seed manifest/templates を実行結果で永続更新しないことを確認する。
