# design-conformance — 設計書由来の必須要件（audit 判定基準）

> `deterministic-generator/audit.py` が検証する「設計書に準拠しているか」の判定基準の **設計根拠** を説明する。
> 機械可読な必須セクション一覧は `manifest.yaml > outputs[].required_sections` が SoT であり、
> 本ファイルはその各項目が **どの設計書要件に由来するか** を人間向けに記録する（重複定義しない）。

## 監査の2軸（QUALITY_GATE exit code 3段階に準拠）

1. **冪等性 / SoT 一元化**: 出力スキル == manifest + templates からの再生成結果。差分があれば直接編集 = exit 1。
2. **設計書準拠**: 各出力が `outputs[].required_sections` を全て含む。欠落は exit 1。
3. **致命的エラー**（テンプレート不在 / manifest 破損 / 親 manifest 読込失敗）は exit 2。
4. 継承後 `project.*` の `[要確認]` 残存、および `session.verification.gate_command` の `[要確認]` は **WARN（exit 0）**。確定は Phase 1.5 対話の責務であり生成基盤の欠陥ではない。

## 必須要件の設計根拠

### .cursor/skills/session-planning/SKILL.md（unified §8 / §12 Layer 3）
- `name: session-planning`: Layer 3 スキルの識別子（§12 description テンプレ例に準拠）。
- `## 大規模タスクの検知`: §12 の発火条件（変更ファイル / サブタスク閾値）。
- `## パターン選択フロー`: §8 の4問によるパターン確定（新キャンペーン判定）。
- `## 追跡ドキュメント`: §2 構成要素「追跡ドキュメント」+ 原則1（単一ファイル）。
- `## Gotchas`: §13.2 推奨（全スキルに Gotchas を設ける）。

### .cursor/skills/session-handover/SKILL.md（unified §2 / §6）
- `name: session-handover`: §12 description テンプレ例に準拠。
- `## 検証ゲート`: §2 構成要素「検証ゲート」+ 原則2（スクリプトで実装）。
- `## リンク衛生`: 原則5（セッションID / 大規模ファイルリンクを含めない）。
- `## 再開プロトコル`: §2 構成要素「再開プロトコル」（未完了を続行）。
- `## Gotchas`: §13.2 推奨。

### .cursor/skills/session-handover/scripts/verification-gate.sh（unified §9-11）
- `session.verification.gate_command`: §9-11 のパターン別検証スクリプトを単一コマンド値で吸収する設計（SoT は manifest）。
- `=== verification gate ===`: 境界ゲートの実行ログ（exit 0/1 による Pass/Fail 判定の入口）。

### .cursor/skills/decisions-record/SKILL.md（unified Appendix B / 設計次元 D-*）
- `name: decisions-record`: §12 スキル分類「知識外部化」に準拠。
- `D-BOUNDARY`: 8 設計次元の起票トリガー（DECISIONS 運用ルール）。
- `Alternatives Considered`: ADR テンプレートの必須セクション。
- `## Gotchas`: §13.2 推奨。

## 必須要件を増減する場合

1. `manifest.yaml > outputs[].required_sections` に文字列を追加/削除。
2. 本ファイルにその設計書由来を1行追記/削除。
3. 対応するテンプレートに当該セクションを追加/削除。
