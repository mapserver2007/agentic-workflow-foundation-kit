---
status: Proposed
provisional_id: ADR-0002
dimension: D-SOT D-QUALITY
title: "Runtime Materialization — tech stack から quality-gate 実行前提を自動物質化する"
---

## ADR-0002: Runtime Materialization — tech stack から quality-gate 実行前提を自動物質化する

**Status**: Proposed

### Significance

- 設計次元: D-SOT D-QUALITY
- 波及範囲:
  - `.cursor/skills/agentic-workflow-foundation/SKILL.md` — Phase 1.68 追加
  - `.cursor/skills/agentic-workflow-foundation/scripts/materialize_runtime.py` — 新設スクリプト
  - `.cursor/skills/agentic-workflow-foundation/scripts/check_tech_stack_conformance.py` — fail-closed 化
  - `docs/QUALITY_GATE.md` — package script contract の実体所有権
  - `README.md` — 責務境界（呼び出し可能まで）

### Context

Phase 1.65 で quality-gate 契約（`pnpm run gen/build/lint/test`）は決定されるが、その実行前提（`package.json` の scripts / deps / packageManager）は生成されない。tech stack から pnpm の使用が確定しているにもかかわらず、`package.json` が存在しないため `bin/quality-gate verify` は起動直後に失敗する。Phase 1.7 は `package.json` 不在を fail-open でスキップするため、この欠落は検出されない。

kit の責務は「tech stack から実行前提を推論し物質化する」ことであり、明示設定を要求すべきではない。

### Decision

Phase 1.68（materialize_runtime）を新設し、tech_stack の capability から `package.json`（scripts / devDependencies / packageManager）等を動的合成する。

- 深さ: 呼び出し可能まで。`pnpm install` / 最小アプリ生成 / ゲート PASS 保証は非目標
- 所有権: `package.json` はアプリ所有ファイル。kit 所有キーは `scripts.gen|build|lint|test` / `packageManager` / tech_stack 由来 deps。kit 所有 scripts は契約更新時に上書き可
- 導出: スタック別テンプレートではなく capability 断片の動的合成
- 適格条件: Phase 1.65 と同一判定式を共有する（1.65 成功 ⇔ 1.68 実行）
- Phase 1.7 変更: 契約確定後の `package.json` 不在は fail-closed（exit 1）

### Consequences

- **Positive**: kit 生成後に `bin/quality-gate` が起動可能になる。「pnpm が必要なのは自明」を人手で解決する必要がなくなる
- **Negative**: kit が `package.json` の一部キーを所有するため、PO の手編集と衝突しうる（kit 所有 scripts は上書き方針で対処）
- **Follow-up**: 1.65 の固定 contract / seed 焼き付きの一般化は別タスク。deps バージョンを npm registry latest から取得する実装のネットワーク依存

### Alternatives Considered

- 手動で package.json を作成させる — kit の「自動解決」責務に反する。tech stack から必要性が推論可能なのに人手を介在させるのは設計思想と矛盾
- ゲート PASS まで担保する（最小アプリ生成込み） — 責務が肥大化し、スタック追加時の保守コストが不釣り合い。呼び出し可能境界で実行時 FAIL に気付ける
- スタック別 YAML テンプレートで静的マップ — manifest seed のキー爆発を招く。capability 合成の方が新スタック追加時に断片追加だけで済む
