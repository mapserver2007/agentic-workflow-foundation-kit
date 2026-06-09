---
name: agentic-session-management
description: >-
  統一設計書（.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md §2/§5/§6/§8-12/§13.2 +
  AI_BUSINESS_AGENT_SUITE.md）を正本に、Layer 3「セッション管理」スキル群
  （session-planning / session-handover / decisions-record）と検証ゲート雛形を
  YAML 正本(manifest.yaml) + テンプレート + deterministic-generator で冪等・再現的に
  生成/メンテナンスする設定スキル（What）。共有 project.* は親 agentic-workflow-foundation
  から inherits_project で継承する。通常は親スキルの Phase 2b から orchestrate され、
  単独でも「セッション管理スキルを生成して」「session-planning/handover を再生成して」
  等で発火する。Encode and generate the Layer 3 session-management skills deterministically.
  Do NOT use for: Meta 層基盤（AGENTS.md / rules / hooks 等）の生成（agentic-workflow-foundation）、
  生成/監査エンジン自体の改修（deterministic-generator）。
disable-model-invocation: true
---

# agentic-session-management

統一設計書の Layer 3「セッション管理」（追跡ドキュメント / 検証ゲート / 再開プロトコルの3構成要素）を**符号化(What)**し、セッション管理スキル群を**冪等・再現的**に生成する設定スキル。生成・監査の実体（How）は [`deterministic-generator`](../deterministic-generator/SKILL.md) が担う。

> **位置づけ**: 本スキルは `agentic-workflow-foundation`（Meta 層基盤）と**同種の設定スキル(What)**で、Layer 3 を担当する。親と同階層の独立スキルとして配置し、共有 `project.*` は親 manifest を SoT として `inherits_project` で継承する（ADR-0007）。本スキル自身は何も生成せず、`deterministic-generator` に `--skill-dir` で渡される入力である。

## アーキテクチャ（決定論型）

```
統一設計書(SoT) ──符号化──▶ manifest.yaml + templates ──100%決定論──▶ session 管理スキル群
   親 agentic-workflow-foundation/project.* ──inherits_project──┘（共有 SoT）
```

- **`manifest.yaml` + templates → 出力スキル** は完全決定論（再実行でバイト一致）。
- 共有 `project.*`（`workflow_pattern` / `tracking_artifact` 等）は親から継承。本スキルは記入しない。
- 本スキル固有値（`session.large_task_threshold` / `session.verification.gate_command`）のみ本スキルが持つ。`large_task_threshold` は統一設計書 §12 の推奨値で**固定**（質問しない）、`verification.gate_command` のみ Phase 1.5 の対話で確定する。

### 構成ファイル

| ファイル | 役割 |
| --- | --- |
| `manifest.yaml` | YAML 正本（`inherits_project` / `session.*` / `outputs` カタログ / `marker_id`） |
| `references/source-mapping.md` | 設計書セクション → manifest キー / テンプレート → 出力スキル のトレーサビリティ |
| `references/design-conformance.md` | 設計書由来の必須要件（`outputs[].required_sections` の設計根拠） |
| `templates/skills/*` | 生成されるセッション管理スキル（SKILL.md）と検証ゲートのテンプレート |

### 生成される出力（Layer 3 スキル群）

| 出力 | 由来 | 役割 |
| --- | --- | --- |
| `.cursor/skills/session-planning/SKILL.md` | unified §8/§12 | 大規模タスク検知 → パターン選択 → 追跡ドキュメント作成 |
| `.cursor/skills/session-handover/SKILL.md` | unified §2/§6 | 終了発話検知 → 検証ゲート → 追跡ドキュメント更新 → アーカイブ提案 |
| `.cursor/skills/session-handover/scripts/verification-gate.sh` | unified §9-11 | `session.verification.gate_command` を実行する境界ゲート |
| `.cursor/skills/decisions-record/SKILL.md` | unified Appendix B | 設計判断(D-*)検知 → docs/DECISIONS.md へ ADR 追記提案 |

## ワークフロー（親から orchestrate される / 単独実行も可）

通常は `agentic-workflow-foundation` の Phase 2b/3 から呼ばれる。単独実行時も同じ順序で行う。

```
- [ ] Phase 1.5: session.* の未確定（[要確認]）を対話で確定
- [ ] Phase 2: 生成（deterministic-generator/generate.py）
- [ ] Phase 3: 監査（deterministic-generator/audit.py）
- [ ] Phase 4: 報告
```

### Phase 1.5: session 固有値の確定（対話）

`session.*` に `[要確認]` が残る場合のみ発火する（確定済みは再質問しない＝冪等再生成で質問が膨れない）。`project.*` は親から継承するため**本スキルでは問わない**（親 `agentic-workflow-foundation` の Phase 1.5 で確定）。

1. **`session.large_task_threshold.{files,subtasks}`**: 統一設計書 §12 の推奨値（files=5 / subtasks=3）で**固定**する。`AskQuestion` で問わない（manifest に既定値が確定済みのため対象外）。
2. **`session.verification.gate_command`**: 確定手段は2段階。
   - 親 `agentic-workflow-foundation/manifest.yaml > project.quality_gate.test_cmd` 等が確定済みならそれを**流用候補**として提示する。
   - 未確定ならリポジトリ（`package.json` / `Makefile` / `pyproject.toml` 等）を調査して候補コマンドを抽出し `AskQuestion` の選択肢にする。
   - ゲートを敷けない場合は `[要確認]` のまま残してよい（`verification-gate.sh` が SKIP=exit 0 する。推測でコマンドを断定しない＝BAS Humble）。

確定値は `agentic-session-management/manifest.yaml > session.*` に記入する。

### Phase 2: 生成

```bash
python3 .cursor/skills/deterministic-generator/scripts/generate.py \
  --skill-dir .cursor/skills/agentic-session-management
```

- manifest + templates から出力スキルを生成/上書き（冪等）。`inherits_project` 解決で `project.*` は親から継承される。
- `verification-gate.sh` には実行ビットが付与される（`executable: true`）。

### Phase 3: 監査ゲート

```bash
python3 .cursor/skills/deterministic-generator/scripts/audit.py \
  --skill-dir .cursor/skills/agentic-session-management
```

- exit 0 → 冪等性 + 必須要件 OK（継承後 `project.*` の `[要確認]` 残存は WARN だが PASS）。
- exit 1 → drift / 必須要件欠落 / ファイル不在。**修正して Phase 2 から再実行**。
- exit 2 → テンプレート不在 / manifest 破損 / 親 manifest 読込失敗。報告して停止。

### Phase 4: 報告

- 生成/更新した出力スキル一覧。
- audit の結果（PASS / FAIL）。
- Phase 1.5 で確定した `session.*` 値（`large_task_threshold` は推奨値固定 / `gate_command` は調査流用の別）。
- `[要確認]` のまま残した任意項目（`gate_command` 未設定等）。

## 重要な制約

- **出力スキルを直接編集しない**。変更は `manifest.yaml` か `templates/` を編集して再生成する（直接編集は audit が drift 検出）。
- **`project.*` は親 SoT を継承**。本スキルの manifest に `project` を書かない（二重定義の値ズレを防ぐ）。
- **`session.verification.gate_command` を推測で埋めない**。敷けない場合は `[要確認]`（WARN）のまま残す。

## スコープ外

- Meta 層基盤（AGENTS.md / rules / hooks / docs）の生成。これは `agentic-workflow-foundation` の責務。
- 生成/監査エンジン（`deterministic-generator`）自体の改修。
- 生成された出力スキル（`session-planning` 等）の実行時ロジックの手編集。

## Gotchas

> 集約先: [docs/GOTCHAS.md](../../../docs/GOTCHAS.md)
>
> 起票トリガー（いずれか）: (1) 開発者から「期待と違う」指摘 / (2) 同じ問題で2回以上の修正 / (3) ドキュメント通りでも想定外の結果。
> 記録フォーマット: `- YYYY-MM-DD: {症状} / {原因} / {再発防止策} / {関連ファイル}`

### エントリ

(現時点のエントリは無し)
