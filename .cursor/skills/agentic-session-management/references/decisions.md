# decisions — 本スキル新設キャンペーンの設計判断（ADR 控え）

> `docs/DECISIONS.md` は `agentic-workflow-foundation` の seed 出力（対象プロジェクト用）であり、本キット作業時点では未生成。
> そのため本キャンペーンで確定した設計判断を本ファイルに控える。基盤生成後、必要に応じて `docs/DECISIONS.md` へ正式転記する。

## ADR-0007: 設定スキルの親子分離と `inherits_project` 継承

- **Significance**: D-ARCH（レイヤー責務） / D-PATTERN（再利用パターン）。
- **Decision**: Layer 3「セッション管理」を、Meta 層基盤を担う `agentic-workflow-foundation`（親）とは別の独立設定スキル `agentic-session-management`（子）として同階層に分離する。共有 `project.*`（`workflow_pattern` / `tracking_artifact` / `name` 等）は親 manifest を単一 SoT とし、子は `inherits_project: .cursor/skills/agentic-workflow-foundation` で継承する。
- **Alternatives Considered**:
  - 子に `project.*` を複製 → SoT 二重化で親子の値ズレが起きるため却下。
  - Layer 3 を親 `agentic-workflow-foundation` に畳み込む → Meta 層と Layer 3 の責務が混在し、再生成単位・テンプレート所有が不明瞭になるため却下。
- **Consequences**: 親→子の順で生成する必要がある（子の `audit.py` は継承解決後の `project` を検査）。親の `[要確認]` は子の WARN にも現れる（親へ1度記入すれば解消）。

## ADR-0008: 生成/監査エンジンを `deterministic-generator` へ改名

- **Significance**: D-NAMING（命名規約）。
- **Decision**: How エンジンを `manifest-generator` → `deterministic-generator` に改名。本質は「決定論的な生成/監査エンジン（ドメイン非依存）」であり、`manifest`（入力契約）を冠する名は (1) 「manifest を生成する」と誤読され (2) 入力の片割れ templates を落とす。`generation` の多義性（世代/生成）を避け、`deterministic`（冪等再生成＝監査の基盤）を冠する。
- **Alternatives Considered**:
  - 現状維持 `manifest-generator` → 上記の誤読リスクで却下。
  - `foundation-generator` → ドメイン非依存（子も処理する）と矛盾するため却下。
  - `generation-engine` / `manifest-engine` → 多義性・契約偏重で次点。
- **Consequences**: ディレクトリ + 全参照（親 `SKILL.md` / `check_design_drift.py` の import / `source-mapping` / `design-conformance`）を追従更新。スクリプト本体ファイル名は据え置き。

## ADR-0009: エンジンに `inherits_project` を実装

- **Significance**: D-ARCH / D-PATTERN。
- **Decision**: `deterministic-generator` に `genlib.deep_merge` / `genlib.apply_inherited_project` を追加し、`generate.py` / `audit.py` がロード直後に親 `project` を子 `project` へ deep-merge（子優先）する。`check_design_drift.py` は不変。
- **Alternatives Considered**: 子 manifest での複製（ADR-0007 と同理由で却下）。
- **Consequences**: `inherits_project` 未指定の設定スキルは無変換（後方互換）。親 manifest 読込失敗は exit 2。

## 子スキル命名: `agentic-session-management`

- **Significance**: D-NAMING。
- **Decision**: `create-session-workflow` → `agentic-session-management`。SoT 用語「セッション管理」に直結し、`agentic-` で親と族の凝集を取り、`-management`（対象=session を明示するドメイン名詞）で What の責務に整合させる。
- **Alternatives Considered**: `-foundation`（親と同格に読め階層を消す）/ `-workflow`（射程過大・非 SoT 用語）/ `-generator`（エンジンと衝突）/ `-manager`（能動アクター含意＝消費される config と不一致）を却下。
