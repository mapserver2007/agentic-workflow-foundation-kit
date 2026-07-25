---
title: AI Agent 基盤 統一設計書（開発責任者版）
exported_at: 2026-04-20
updated_at: 2026-04-23
version: 3.0（命名規約 semantic 2層モデルの正式採用）
status: 正本（Source of Truth）
reference_specs:
  - Anthropic Agent Skills (https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
  - Anthropic Agent Skills Best Practices (https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
  - Cursor Rules (https://cursor.com/docs/rules)
  - Cursor Skills (https://cursor.com/docs/skills)
  - Cursor Subagents (https://cursor.com/docs/subagents)
  - Cursor Hooks (https://cursor.com/docs/hooks)
---

# AI Agent 基盤 統一設計書（開発責任者版） v3

* 作成日: 2026-04-20（v1.0）/ 更新日: 2026-04-23（v3.0）
* プロジェクト: AI エージェント開発基盤（ai-agent-dev-infra）
* 想定ロール: **開発責任者** — PO / PdM / PjM / PL / TL（以下まとめて「PO」と表記）
* 元資料: `ai-agent-unified-design.md`（経営視点版）を開発ドメインに再構成したもの
* v2 での主な変更: Opus 4.7 High レビュー（22件）の反映。公式仕様（Anthropic / Cursor）と齟齬のあった箇所を修正し、独自ルール部分は「本設計の推奨」として明示
* **v3 での主な変更**: ドキュメント命名規約を **semantic 2層モデル（Meta = 大文字 / Domain = 小文字）** として正式採用。§12 Layer 1 に命名原則セクションを新設し、Appendix E を「Meta 層」と「Domain 層」で明示的に分類。本リポジトリでの運用実態（`docs/DECISIONS.md` や `docs/spec/master-sync.md` の共存）を設計書に逆輸入した形

本ドキュメントは AI エージェント（Cursor Agent、Claude Code 等）を **開発プロジェクトに組み込む** ための基盤設計を、**設計 → 実装 → レビュー → QA → リリース** の開発プロセスに沿って解説する。用語は [Appendix C](#appendix-c-用語集) を参照。

---

## 目次

### Part 1: 概念編（なぜ・何を）

1. [セッション管理とは何か](#1-セッション管理とは何か)
2. [3つの構成要素](#2-3つの構成要素)
3. [パターンを決める2つの軸](#3-パターンを決める2つの軸)
4. [設計原則](#4-設計原則)
5. [5層モデル（開発プロセス対応）](#5-5層モデル開発プロセス対応)
6. [追跡ドキュメントのライフサイクル](#6-追跡ドキュメントのライフサイクル)
7. [コンパクション回避の考え方](#7-コンパクション回避の考え方)


### Part 2: 実践編（どう使う）

8. [パターン選択フロー](#8-パターン選択フロー)
9. [開発型のセットアップ](#9-開発型のセットアップ)
10. [パイプライン型のセットアップ](#10-パイプライン型のセットアップ)
11. [ドキュメント型のセットアップ](#11-ドキュメント型のセットアップ)
12. [5層の実装方法](#12-5層の実装方法)
13. [Skill・Rule・Subagent・Hook の設計仕様](#13-skillrulesubagenthook-の設計仕様)
14. [スキル・ルールの配置戦略](#14-スキルルールの配置戦略)
15. [クロスツール連携](#15-クロスツール連携)
16. [新規ワークスペースの立ち上げ](#16-新規ワークスペースの立ち上げ)
17. [コンパクション回避の実践](#17-コンパクション回避の実践)


### Appendix

* [A: 設計原則の根拠と一次情報ソース](#appendix-a-設計原則の根拠と一次情報ソース)
* [B: 実運用から得た知見](#appendix-b-実運用から得た知見)
* [C: 用語集](#appendix-c-用語集)
* [D: 参照](#appendix-d-参照)
* [E: 開発責任者視点で作るべきドキュメントリスト](#appendix-e-開発責任者視点で作るべきドキュメントリスト)
* [F: v2 変更履歴（公式仕様レビュー反映）](#appendix-f-v2-変更履歴公式仕様レビュー反映)

---

## Part 1: 概念編（なぜ・何を）

### 1. セッション管理とは何か

AI エージェントには**コンテキストウィンドウ**という、一度に処理できるテキスト量の上限がある。これはプロセスの RAM に相当し、セッション終了やウィンドウ超過で情報は揮発する。さらに、コンテキストが長くなると中央付近の情報が無視されやすくなる（Lost in the Middle 問題）。

大きな実装タスクを複数セッションに分割した瞬間に**文脈の断絶**が起きる。前のセッションで何を決め、何を実装し、何が残っているかが失われ、次セッションで同じ調査・同じ議論が繰り返される。

この断絶を最小化することがセッション管理の本質であり、それは**コンテキストアーキテクチャ**の問題として捉える。

> 知識をどう分割し、同期し、圧縮し、再構築するか — これがセッション管理の設計課題

開発プロセス上の位置付け: **要件 → 設計 → 実装 → テスト → リリース** の全フェーズで、AI が「前回の判断」を失わずに継続できるかどうかがスループットを決める。

---

### 2. 3つの構成要素

セッション管理を構成する要素は3つに集約される。

| 構成要素 | 役割 | コンテキストアーキテクチャとの対応 |
| --- | --- | --- |
| **追跡ドキュメント** | 計画・進捗・引き継ぎを兼ねる単一ファイル | コンテキストの永続化 |
| **検証ゲート** | セッション終了時にアウトプットの品質を検証する仕組み | コンテキストドリフトの検知 |
| **再開プロトコル** | 次セッション開始時の手順 | コンテキストの圧縮と再構築 |

いずれかが欠けると問題が生じる:

| 欠けている要素 | 起きる問題 |
| --- | --- |
| 追跡ドキュメント | plan.md / handover / チャット履歴に情報が分散し、Source of Truth が不明になる |
| 検証ゲート | 品質劣化に気づけないままコミットが進み、リグレッションが後工程で発覚する |
| 再開プロトコル | セッション再開のたびに複数ファイルを手動ロードさせる儀式が発生し、実装時間を圧迫する |

---

### 3. パターンを決める2つの軸

**軸1: アウトプットの性質**

| アウトプット | 特徴 | 例 |
| --- | --- | --- |
| コード / アプリケーション | 機械的に検証可能、リグレッションリスク | Web アプリ、CLI ツール、ライブラリ |
| データ / 生成物 | スクリプトで検証可能、AI幻覚リスク | スクレイピング結果、バッチ生成データ、機械学習データセット |
| ドキュメント / 仕様 | 人間レビューで検証、不完全・不整合リスク | 要件定義書、設計書、ADR、ランブック |

**軸2: 検証可能性 → 検証方法**

| 検知したい失敗モード | 検証方法 | 自動化度 |
| --- | --- | --- |
| リグレッション（既存機能の破壊） | 自動テスト + ビルド + 型チェック | 完全自動 |
| 生成データの不整合・幻覚 | スクリプト出力のスキーマ/件数/整合性チェック | 半自動 |
| ドキュメントの不完全・不整合 | 完了基準チェックリスト + 人間レビュー | 半手動 |

**2軸の組み合わせで3パターンが決まる:**

| パターン | アウトプット | リスク | 検証方法 | 追跡ドキュメント |
| --- | --- | --- | --- | --- |
| **開発型** | 動くアプリケーション | リグレッション | 自動テスト + ビルド + 型チェック | `plan.md` |
| **パイプライン型** | スクリプト生成データ | AI幻覚 | スクリプト出力の整合性チェック | `playbook.md` |
| **ドキュメント型** | ドキュメント群（SDD成果物） | 不完全・不整合 | 完了基準チェックリスト | `session_plan.md` |

---

### 4. 設計原則

本設計は8つの原則に基づく。各原則の詳細な根拠と一次情報ソースは [Appendix A](#appendix-a-設計原則の根拠と一次情報ソース) を参照。

| 原則 | 要約 |
| --- | --- |
| 1. 追跡ドキュメントは単一ファイル | 計画・進捗・引き継ぎを1ファイルに集約し、Source of Truth を一元化する |
| 2. 検証ゲートはスクリプトで実装 | 品質チェックを自然言語指示ではなくスクリプト（exit code ベース）で実装し、確実に実行する |
| 3. 最小 Human-in-the-Loop | 開発者の介入を「判断基準の策定」「分岐点の確認」「最終レビュー」の3点に限定 |
| 4. コンテキストの即時外部化 | 意思決定・発見・進捗をファイルに即時書き込み、コンテキストウィンドウに頼らない |
| 5. コンテキスト保護 | (a) リンク衛生: 追跡ドキュメントにセッションIDを含めない (b) アーカイブ境界: 完了した追跡ドキュメントを隔離 |
| 6. コンテキストコストの管理 | トークン量制約とルール探索コスト O(N) を意識し、冗長な指示・無関係なスキルをロードしない |
| 7. Advisory vs Deterministic | Rules（~80%遵守）と Hooks（~100%遵守）を使い分け、データ損失級の制約は Hooks で強制 |
| 8. 自己改善サイクル | Observe（失敗検知）→ Amend（Gotchas更新）→ Evolve（構造リファクタ）で継続改善（= 開発のレトロ/ポストモーテムに相当） |

---

### 5. 5層モデル（開発プロセス対応）

セッション管理はスキル・ルール・設定ファイルを通じて実装される。これらの関係を**5層モデル**として、**ソフトウェア開発プロセス（設計〜QA）のアナロジー**で整理する。

```
┌─────────────────────────────────────────
│  Layer 1: Context（文脈）
│  プロジェクトの設定ファイル
│  = 要件定義書・仕様書（What / Why）
├─────────────────────────────────────────
│  Layer 2: Constraints（制約）
│  常時適用されるルール
│  = コーディング規約・設計ガイドライン
├─────────────────────────────────────────
│  Layer 3: Capabilities（能力）
│  必要時に呼び出されるスキル
│  = 実装手順書・ランブック・再利用可能モジュール
├─────────────────────────────────────────
│  Layer 4: Automation（自動化）
│  ツール実行前後の自動処理
│  = CI / 静的解析 / QA ゲート
├─────────────────────────────────────────
│  Layer 5: Delegation（委譲）
│  子エージェントへのタスク委譲
│  = 並列ワーカー / 専門ビルドジョブ
└─────────────────────────────────────────
```

各層は開発プロセスの成果物・工程にマッピングできる。AI エージェントに対して、**開発チームが新メンバーをオンボードするのと同じ構造**で文脈・制約・能力を提供する。

| Layer | 役割 | 開発プロセスのアナロジー | 読み込みタイミング |
| --- | --- | --- | --- |
| 1. Context | プロジェクトの目的・判断基準を定義 | 要件定義書 / 仕様書 / README | セッション開始時に自動 |
| 2. Constraints | 全セッションで守るべきルール | コーディング規約 / lint ルール / 設計原則 | セッション開始時に自動 |
| 3. Capabilities | 必要時に呼び出される専門手順 | 実装手順書 / ランブック / 再利用モジュール | トリガー条件合致時 |
| 4. Automation | ツール実行の前後で自動実行 | CI / pre-commit hook / QA ゲート | エージェントループの特定タイミング |
| 5. Delegation | 専門タスクを子エージェントに委譲 | 並列ジョブ / 専門ビルドワーカー / レビューボット | 明示的に起動 |

各層を実現する具体的なファイル・ツールの実装方法は [Section 12](#12-5層の実装方法) を参照。

---

### 6. 追跡ドキュメントのライフサイクル

追跡ドキュメントには有限のスコープがあり、スコープの完了と共にライフサイクルが終わる。

**キャンペーン**: 追跡ドキュメントのスコープ単位。ひとまとまりの作業群を指す。プロジェクト ≠ キャンペーン（1プロジェクトで複数のキャンペーンが発生しうる。例: 機能A実装キャンペーン → バグ修正キャンペーン → リファクタキャンペーン）。

**状態遷移:**

```
Active（活動中）→ Complete（完了）→ Archive（保管）

[Active]
  - プロジェクトルート直下に配置
  - AI がセッション開始時に読み込む対象
  - 常に最大1つのみ存在する

[Complete]
  - 全タスクが完了した状態（短期間の中間状態）
  - ハンドオーバースキルが検知し、アーカイブを提案

[Archive]
  - archive/ に移動し、AI の通常の読み込み対象外に
  - 開発者の振り返り・参照用として保存
  - 判断の経緯は DECISIONS.md（ADR）に外部化済み
```

| パターン | 追跡ドキュメント | キャンペーン完了の判定 | アーカイブ命名例 |
| --- | --- | --- | --- |
| 開発型 | `plan.md` | 全タスクの品質ゲート通過 | `archive/plan_feat-auth.md` |
| パイプライン型 | `playbook.md` | 全 Phase 完了 + 出力検証 PASS | `archive/playbook_scrape-v2.md` |
| ドキュメント型 | `session_plan.md` | 全タスクの完了基準チェック | `archive/session_plan_spec-v1.md` |

アーカイブ後、新しい作業群が発生すると `session_planning` スキルが追跡ドキュメントの不在を検知し、パターン選択フロー（[Section 8](#8-パターン選択フロー)）を実行して新たな追跡ドキュメントを作成する。

---

### 7. コンパクション回避の考え方

コンパクション（コンテキストの強制圧縮）が発生すると AI の判断精度が低下する。実装の途中で精度が落ちると、直前の設計判断と整合しないコードが生成される典型的な事故につながる。

**予防策:**

| 戦略 | 説明 |
| --- | --- |
| 30-45分ルール | 1セッションを30-45分以内に収める（= 1 PR 単位の作業時間と揃えると運用しやすい） |
| サブエージェント活用 | 調査・分析はサブエージェントに委譲し、メインコンテキストを保護 |
| 即時外部化 | 意思決定・発見は即座に追跡ドキュメント / ADR に書き込む |
| 検証ゲート = ブレイクポイント | 検証ゲートのタイミングがセッション分割の自然な判断点（= コミット/プッシュ粒度と一致させる） |
| コンテキスト保護 | リンク衛生 + アーカイブ境界（原則5） |

**兆候と対応:**

| 兆候 | 対応 |
| --- | --- |
| 応答が遅くなる | 追跡ドキュメントを更新し、セッション終了を検討 |
| 以前の指示を忘れる | 暗黙の文脈が失われている。即座に外部化 |
| コンパクション警告 | 追跡ドキュメントの最新化を確認してから許可 |

具体的な操作コマンドは [Section 17](#17-コンパクション回避の実践) を参照。

---

## Part 2: 実践編（どう使う）

### 8. パターン選択フロー

以下の4つの質問でパターンが決まる。

```
1. このプロジェクト/キャンペーンの主なアウトプットは何か？
   → コード / データ / ドキュメント / 複合

2. そのアウトプットを壊す最大のリスクは何か？
   → リグレッション / AI幻覚 / 不完全・不整合

3. そのリスクを検知する方法は何か？
   → 自動テスト / スクリプト検証 / チェックリスト

4. → パターンが決まる（開発型 / パイプライン型 / ドキュメント型）
```

**複合型の場合 — まずワークスペースの分離を検討する:**

| 条件 | 判断 |
| --- | --- |
| 品質ゲートの種類が異なる（`pytest` vs schema check 等） | **分ける** |
| 検知したい失敗モードが異なる | **分ける** |
| 同じ品質ゲートで検証できる | 混在可 |
| 副次アウトプットが主要アウトプットに従属する（例: コードに付随する README） | 混在可 |

混在させる場合は、主要アウトプットのパターンをベースに、副次アウトプットの検証ゲートを追加する。

---

### 9. 開発型のセットアップ

**適用条件:** アウトプットが動くアプリケーション。リグレッションリスクを自動テストで防ぐ。

**品質ゲート3層構造:**

```
1. 実装中ゲート（コーディング中に随時適用）
   - テストリスト必須化: 実装開始前に正常系/異常系/境界値のテストリストを作成
   - 方式選択ゲート: test-first / tdd / hybrid を3問の判定で決定
   - 段階的テスト検証: 単一テスト → ファイル単位 → 全件の順で拡大
   - GREEN品質チェック: アサーション強度、モック参照安定性

2. セッション境界ゲート（セッション完了時に必須実行）
   - 自動テスト全件 PASS
   - E2E テスト全件 PASS（存在する場合）
   - ビルド成功
   - 型チェック通過
   - lint 通過
   → scripts/quality_gate.sh で自動判定

3. フェーズ境界ゲート（V字モデルの各フェーズ完了時）
   - フェーズ固有の完了条件チェックリスト
   - レビューエージェント（subagent, readonly/tools制限）による独立レビュー
```

**必要なドキュメント:**

```
docs/
├── DECISIONS.md                     -- ADR（設計判断記録）
├── SPEC.md                          -- 仕様書（SDD: Spec-Driven Development）
├── ARCHITECTURE.md                  -- アーキテクチャ設計書
└── process/
    ├── SESSION_BASED_DEVELOPMENT.md -- セッション分割の方法論・ブランチ戦略
    ├── SESSION_MANAGEMENT.md        -- セッション開始・終了プロトコル
    ├── PHASE_CHECKLIST.md           -- フェーズ別完了条件
    └── TDD.md                       -- テスト駆動開発ガイド
```

**必要なスキル:**

```
.agents/skills/
├── session_planning/      -- 大規模タスク検知 → plan.md 作成
├── session_handover/      -- セッション終了 → 検証ゲート → plan.md 更新
│   └── scripts/quality_gate.sh
├── decisions_record/      -- 設計判断検知 → DECISIONS.md（ADR）記録提案
├── test_verification/     -- 4段階テスト検証 + ターミナル監視
└── tdd_testlist/          -- テストリスト必須化 + 方式選択 + GREEN品質チェック
```

**検証スクリプト（quality_gate.sh）:**

```shell
#!/bin/bash
# exit 0 = 全ゲート通過 / exit 1 = 失敗
set -e
echo "=== Quality Gate ==="

echo "[1/4] Running tests..."
npm test --if-present

echo "[2/4] Running E2E tests..."
if [ -d "e2e" ]; then npx playwright test --reporter=list; fi

echo "[3/4] Type checking..."
npx tsc --noEmit

echo "[4/4] Building..."
npm run build

echo "=== All gates passed ==="
```

技術スタックに応じてカスタマイズ（例: Rust → `cargo test` + `cargo build`、Python → `pytest` + `mypy`、Go → `go test ./...` + `go build ./...`）。

---

### 10. パイプライン型のセットアップ

**適用条件:** アウトプットがスクリプト生成データ。AI幻覚リスクをスクリプト検証で防ぐ。

**品質ゲート構造:**

```
1. Phase 境界ゲート（各 Phase 完了時）
   - スクリプト出力ファイルの存在確認
   - 出力データの行数・件数・スキーマ整合性チェック
   - AI が直接生成したデータでないことの確認（= パイプラインを通したか）
   → scripts/verify_output.py で自動判定

2. セッション境界ゲート（セッション完了時）
   - playbook.md 進捗チェックボックス更新
   - git コミット
```

**必要なドキュメント:**

```
docs/
├── PIPELINE_SPEC.md                 -- パイプライン仕様（入出力スキーマ）
└── process/
    └── SESSION_BASED_DEVELOPMENT.md -- playbook 中心セッション方法論・並列実行・ブランチ戦略
```

**必要なスキル:**

```
.agents/skills/
├── session_planning/      -- 大規模タスク検知 → playbook.md 作成
└── session_handover/      -- playbook 進捗更新 + Phase 境界検証
    └── scripts/verify_output.py
```

**検証スクリプト（verify_output.py）:**

```python
#!/usr/bin/env python3
"""exit 0 = 検証通過 / exit 1 = 失敗"""
import sys, json
from pathlib import Path

def verify_file(path: str, min_lines: int = 1) -> bool:
    p = Path(path)
    if not p.exists():
        print(f"FAIL: {path} does not exist"); return False
    lines = p.read_text().strip().split('\n')
    if len(lines) < min_lines:
        print(f"FAIL: {path} has {len(lines)} lines (min: {min_lines})"); return False
    print(f"PASS: {path} ({len(lines)} lines)"); return True

def verify_json(path: str, required_keys: list[str] = None) -> bool:
    p = Path(path)
    if not p.exists():
        print(f"FAIL: {path} does not exist"); return False
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: {path} is not valid JSON: {e}"); return False
    if required_keys:
        sample = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else {}
        missing = [k for k in required_keys if k not in sample]
        if missing:
            print(f"FAIL: {path} missing keys: {missing}"); return False
    count = len(data) if isinstance(data, list) else 1
    print(f"PASS: {path} ({count} records)"); return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: verify_output.py <file>"); sys.exit(1)
    target = sys.argv[1]
    ok = verify_json(target) if target.endswith('.json') else verify_file(target)
    sys.exit(0 if ok else 1)
```

---

### 11. ドキュメント型のセットアップ

**適用条件:** アウトプットがドキュメント群（SDD 成果物: 要件定義・仕様書・設計書・ADR・ランブック・API ドキュメント等）。不完全・不整合リスクをチェックリストで防ぐ。

**品質ゲート構造:**

```
1. セッション境界ゲート（セッション完了時）
   - 完了基準チェックリストの全項目確認
   - session_plan.md の実施記録更新
   - ドキュメント間の整合性確認（相互参照リンク切れ検知）
   → scripts/check_completion.sh で補助

2. 工程境界ゲート（要件定義 → 基本設計 → 詳細設計 → 実装 → テスト → ...）
   - SDD ライフサイクルルールの完了条件確認
   - README.md のドキュメント一覧ステータス更新
```

**必要なドキュメント:**

ドキュメント型ではプロセスドキュメントよりも `CLAUDE.md` / `AGENTS.md` の充実が重要。プロジェクトの判断基準・ディレクトリ構成・セッションプロトコルを Layer 1 に集約する。SDD 成果物のテンプレートは `docs/templates/` に配置し、スキルから参照する。

**必要なスキル:**

```
.agents/skills/
├── session_planning/      -- session_plan.md の作成・更新
├── session_handover/      -- 実施記録の追記 + 次セッション計画
│   └── scripts/check_completion.sh
└── decisions_record/      -- 設計判断検知 → DECISIONS.md（ADR）記録提案（任意）
```

**検証スクリプト（check_completion.sh）:**

```shell
#!/bin/bash
# exit 0 = 全チェック通過 / exit 1 = 失敗
PROJECT_DIR="${1:-.}"
PASS=0; FAIL=0

check_file() {
  if [ -f "$1" ]; then
    echo "PASS: $1 exists"; PASS=$((PASS + 1))
  else
    echo "FAIL: $1 does not exist"; FAIL=$((FAIL + 1))
  fi
}

check_file "$PROJECT_DIR/README.md"
check_file "$PROJECT_DIR/session_plan.md"

echo ""; echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

---

### 12. 5層の実装方法

#### Layer 1: Context — CLAUDE.md / AGENTS.md

プロジェクトの「要件定義書」相当を定義する。Claude Code は `CLAUDE.md`、Cursor は `AGENTS.md`（または `.cursor/rules`）を一次的な文脈源として読み込む。

**ドキュメント命名規約 — semantic 2層モデル（v3 正式採用）:**

本設計書では、`docs/` 配下のファイル名の**大文字/小文字で役割を明確に区別する** semantic 2層モデルを規約として採用する。

| 層 | 命名 | 意味 | 判定基準 | 例 |
| --- | --- | --- | --- | --- |
| **Meta 層** | `UPPER_SNAKE_CASE.md` | 上位概念・判断フレームワーク・運用ルール・記録フォーマット。AI/人間への「読む指示」「どう動くか・どう判断するか」を定義 | **「他リポジトリでも同じ役割名で通用するか？」= Yes** | `DECISIONS.md`, `GOTCHAS.md`, `QUALITY_GATE.md`, `AGENT_RUNBOOK.md`, `RUNBOOK.md`, `README.md`, `CHANGELOG.md`, `SECURITY.md` |
| **Domain 層** | `kebab-case.md` | 本リポジトリ固有のドメイン知識・独自ワークフロー・業務仕様・実装詳細 | **「このリポジトリ特有の what を記述しているか？」= Yes** | `spec.md`, `spec/master-sync.md`, `architecture.md`, `api.md`, `data-models.md`, `coding-standards.md`, `workflows.md`, `datadog-investigation-guide.md` |

**公式固定（ツール識別のため大文字必須、上記 Meta 層の特殊例）:**

| ファイル | 根拠 |
| --- | --- |
| `CLAUDE.md` | [Anthropic Docs - claude-md](https://docs.anthropic.com/en/docs/claude-code/claude-md)（ケースセンシティブ、`claude.md` 等は認識されない） |
| `CLAUDE.local.md` | Anthropic Docs（個人用ローカル設定） |
| `MEMORY.md` | Anthropic Docs（Auto Memory のエントリポイント） |
| `AGENTS.md` | [Cursor Docs - Rules](https://cursor.com/docs/rules) |

**公式が小文字 kebab-case を推奨している領域（Domain 層と整合）:**

* `.cursor/rules/*.mdc` は **kebab-case** が公式推奨（例: `react-patterns.mdc`, `api-validation.mdc`）
* `.claude/rules/*.md` も `testing.md`, `api-design.md` のような小文字 kebab-case を推奨
* Auto Memory のトピックファイル（`debugging.md`, `api-conventions.md` 等）も同様

**例外: 識別子プレフィックス付きファイル**

`runbooks/RB-001-xxx.md` のように**カタログ ID が大文字プレフィックス**のケースは、ID 部分は大文字固定・本文タイトル部分は kebab-case の混在。Meta 層（カテゴリ名）と Domain 層（個別インシデント内容）のハイブリッドと解釈する。

**判定に迷うケースの指針**

1. そのファイルを別プロジェクトに移したとき、**役割名だけ継承して中身を書き直せるか** → Yes なら Meta 層（大文字）
2. そのファイルの中身が**このプロジェクト固有の業務/技術仕様**か → Yes なら Domain 層（小文字）
3. 両方当てはまる場合（例: `TROUBLESHOOTING.md` 的なもの）は、**中身が何を占めているかの比率**で判定。汎用フレームワーク > 50% なら Meta、プロジェクト固有事例 > 50% なら Domain

この規約を採用することで、「大文字ファイル = メタ指示/判断基準を読み手に渡すもの」「小文字ファイル = プロジェクト固有のコンテンツ」という semantic な使い分けが成立し、**AI エージェントがファイル名だけから読むべき順序・理由を判別できる**ようになる。

**CLAUDE.md（Claude Code の主要 Context ファイル）:**

* プロジェクトの目的・スコープ・技術スタック
* 判断基準（何を優先し、何を避けるか。= 非機能要件 / 設計トレードオフ）
* ディレクトリ構成と各ファイルの役割
* セッション管理プロトコル（再開・終了の手順）
* Gotchas セクション（失敗から学んだことを蓄積。= ポストモーテムの運用ログ）

**AGENTS.md（Cursor の主要 Context ファイル / v2 修正 W7）:**

* `.cursor/rules` の**完全な簡易代替**として機能する独立したルール定義ファイル
* **ネスト対応**: `frontend/AGENTS.md`, `backend/AGENTS.md` 等、サブディレクトリ配置が可能。親の AGENTS.md と組み合わされ、具体的な指示が優先される
* 公式: [Cursor Docs - Rules > AGENTS.md](https://cursor.com/docs/rules)

**CLAUDE.md / AGENTS.md の統合運用パターン:**

Source of Truth を CLAUDE.md に置き、Cursor 実行時は AGENTS.md から CLAUDE.md を参照（または AGENTS.md 末尾に `@CLAUDE.md` 参照を追加）させる運用にすると、両ツールで同じ文脈を共有しやすい。ただしこれは**本設計の推奨運用**であり、AGENTS.md 単独でも Cursor では完結する。

セッション再開時、AI はまずこの層を読んでプロジェクト文脈を復元する。新メンバーが最初に読む README + オンボーディングドキュメントと同じ役割。

#### Layer 2: Constraints — Rules

`.cursor/rules/` のルールが全セッションで自動適用される。コーディング規約・lint ルール・設計原則に相当。

**ルール設計の原則:**

* **宣言的に書く**: 「〜すること」「〜してはならない」の制約のみ記載する。手続き（手順・ワークフロー）はスキルに委譲し、ルールからはスキル名を参照するだけにする
* **スキルと重複させない**: 同じ内容がルールとスキルの両方にあると、片方を更新した際に不整合が生じる（Single Source of Truth 違反）
* **行数ガイド（v2 修正 W8）**: Cursor 公式は 500 行以下を推奨するが、本設計では手続きの混入を検知するため独自に **50 行以内** を目安とする。超える場合は手続き的な内容が混入しているサインなのでスキルへの分離を検討する
* **description はラベルとして書く**: alwaysApply ルールは常に読み込まれるため、スキルのようなトリガー設計は不要。ルールの適用範囲が一目でわかる説明を書く

**模範例** — `no-remote-git.mdc`（20行）:

```
禁止事項を「〜してはならない」で4つ列挙 + 理由を1文で説明。
手順なし、条件分岐なし、参照先なし。純粋な制約のみ。
```

**共有ルール**（`~/.cursor/rules/` で全WS適用）:

* `plan-quality.mdc` — 影響調査（入口）+ 品質ゲート（出口）を一体適用
* `user-skills-repo.mdc` — 共有スキルリポジトリの管理ルール

**WS固有ルール**（`.cursor/rules/` で当該WSのみ）:

* `session-workflow.mdc` — セッションの制約（コミット戦略・コンテキスト保護等）
* その他プロジェクト固有の制約（使用禁止ライブラリ、命名規約など）


#### Layer 3: Capabilities — Skills

Agent Skills が必要時に呼び出される。Anthropic Agent Skills オープン標準に準拠。開発ドメインでは**再利用可能な実装手順書 / ランブック**に相当。

**スキル設計のポイント（v2 修正 C4, C5, W1, I1, I4）:**

* **frontmatter の** `description`: 「いつ発火させるか」のトリガー条件として設計する。スキルの要約ではなく、AI がリクエストとマッチするか判断するための条件文。ドメインキーワードと開発者の発話パターン（日本語・英語）を十分に含めることで発火精度が上がる
* **description の一覧表示上限**（公式）: Anthropic 公式仕様では `description` と `when_to_use` の合算が一覧表示時に **1,536 文字で切り詰められる**。本設計ではこれより厳しい **1,024 文字以内**（チーム標準）を推奨し、What（何をするか）+ When（発動トリガー）+ Negative（発動しない場面）の3構造で書く。フロントマターに XMLタグ（`< >`）を含めない
* **本文サイズ**（v2 修正 C4）: Anthropic 公式は SKILL.md 本文（Level 2）を **5,000 トークン未満** に収めることを推奨。目安: 英語 ≒ 3,000〜3,500 語、日本語 ≒ 2,500〜4,000 文字。Progressive Disclosure（手順 → 判断基準 → テンプレート）で L3 に逃す
* **コスト見積り**（v2 追記 I1）: Level 1（メタデータ）= 約 100 トークン / スキル（常時ロード）、Level 2（SKILL.md 本文）= 5,000 トークン未満（トリガー時にロード）、Level 3（参照・スクリプト）= 実質無制限（参照時のみ）
* `references/`: テンプレート・詳細仕様は別ファイルに分離。本文から相対パスで参照
* `scripts/`: 検証スクリプトをスキルと同居
* **Gotchas セクション**（本設計の推奨）: 全スキルに設け、運用中の失敗を蓄積。5件以上でリファクタリングを検討
* **Setup/Config パターン**: ユーザー固有の設定が必要なスキルでは `config.json` をスキルディレクトリに配置。未設定時は対話的に初期設定する
* **`disable-model-invocation`**（v2 追記 W1）: `true` にすると自動発火を抑止し、`/skill-name` スラッシュコマンド専用になる。手動のみで起動したい「コマンド化スキル」向け

**description テンプレート例:**

```yaml
---
name: session_planning
description: >
  大規模タスク（変更ファイル5件以上、サブタスク3つ以上）を検知したときに、
  セッション分割計画と追跡ドキュメントを作成する。
  追跡ドキュメントが存在しない場合は新キャンペーンと判断し、選択フローを
  実行してパターンを決定してから追跡ドキュメントを新規作成する。
  Do NOT use for: 単一ファイル修正、バグ修正など1セッションで完了する小規模タスク。
---
```

**session_handover の description テンプレート例:**

```yaml
---
name: session_handover
description: >
  セッション終了時（「セッションを終了する」「引き継ぎを作成して」「今日はここまで」等の
  発話を検知）に、検証ゲートを実行し、追跡ドキュメントを更新する。
  全タスク/全Phase完了を検知した場合はアーカイブを提案する。
  追跡ドキュメントにセッションIDや大規模ファイルへのリンクを含めない（リンク衛生）。
  Do NOT use for: セッション途中の進捗確認。セッション開始時の操作。
---
```

**スキルの分類例:**

| 分類 | スキル例 | 配置先 | 概要 |
| --- | --- | --- | --- |
| セッション管理 | session-planning | `~/.cursor/skills/` | 大規模タスク検知 → 追跡ドキュメント作成 |
| セッション管理 | session-handover | `~/.cursor/skills/` | セッション終了 → 検証ゲート → 記録更新 |
| 知識外部化 | decisions-record | `~/.cursor/skills/` | 設計判断検知 → DECISIONS.md（ADR）記録提案 |
| 品質管理 | plan-review | `~/.cursor/skills/` | プラン文書の5軸セルフレビュー |
| 品質管理 | quality-gate | `~/.cursor/skills/` | 品質ゲートの実行時検証(Pass/Fail) |
| ツール連携 | confluence-sync | `~/.cursor/skills/` | Confluence 双方向同期 |
| スキル管理 | create-skill-rule | `~/.cursor/skills/` | スキル/ルール新規作成・設計 |

上記はコアスキルの例。これに加えて、ワークスペースごとに実装ドメイン固有のスキル（API 仕様参照、コード生成、ドキュメント変換等）を追加する。

**Setup/Config パターン:** ユーザー固有の設定が必要なスキルでは `config.json` をスキルディレクトリに配置。未設定時は対話的に初期設定する。

#### Layer 4: Automation — Hooks

Hooks がエージェントループの特定タイミングで自動実行される。CI / pre-commit hook / QA ゲートに相当。Hook のイベント名・スキーマは **Cursor 公式仕様（キャメルケース）** に準拠する（v2 修正 C2）。

| Hook | タイミング | 用途 |
| --- | --- | --- |
| `afterFileEdit` | ファイル編集後 | フォーマッタ、lint、型チェック |
| `stop` | エージェント停止時 | 追跡ドキュメント更新の促進。Task Contract の検証 |
| `preCompact` | コンパクション発生前 | 追跡ドキュメントへの書き込み促進 |
| `preToolUse` | ツール実行前 | 特定ツールの使用制限（汎用） |
| `beforeShellExecution` | シェルコマンド実行前 | 危険コマンドの検知とブロック（シェル特化） |
| `sessionStart` | セッション開始時 | 環境チェック、コンテキスト注入 |

> Claude Code 側の Hook イベントはパスカルケース（`PreToolUse`, `SessionStart` 等）で別体系。本設計では Cursor 公式表記をデフォルトとし、Claude Code 併用時は [Cursor Docs - Third Party Hooks](https://cursor.com/docs/reference/third-party-hooks) を参照。

**Advisory → Deterministic への昇格判断:**

| 判断基準 | Advisory（Rules）のまま | Deterministic（Hooks）に昇格 |
| --- | --- | --- |
| 違反時の影響 | 品質低下だが回復可能 | データ損失・セキュリティ侵害・不可逆な破壊 |
| 例外の有無 | 状況により例外がありうる | 例外を認めない |
| 現状の遵守率 | 十分に守られている | 繰り返し違反が観測される（3回以上） |

**On-demand hooks:** スキルから一時的にフックを登録するパターン。

* `/careful` — `rm -rf`、`DROP TABLE`、`force-push` をブロック
* `/freeze` — 特定ディレクトリ以外への書き込みをブロック

**Permission Mode と3層防御（v2 修正 C7）:**

Claude Code の `Shift+Tab` は **Permission Mode を4モードで循環切替** するキーである。

| モード | 挙動 |
| --- | --- |
| `default` | 都度確認（標準） |
| `acceptEdits` | ファイル編集は自動承認 |
| `plan` | 読み取り専用のプランモード |
| `bypassPermissions` | 全権限を自動承認（通称 YOLO モード） |

資料 v1 で「Auto Mode」と呼んでいた状態は **`bypassPermissions` モード**に相当する。`bypassPermissions` を安全に使うための3層防御:

1. **sandbox** — OS レベルの隔離。書き込みをプロジェクトディレクトリに制限
2. **allowedTools** — `.claude/settings.json` でツール単位の許可・拒否
3. **preToolUse hook**（Cursor）/ `PreToolUse` hook（Claude Code） — 危険コマンドの検知とブロック

**Task Contract + Stop-hook パターン:**

`stop` Hook で完了条件（Task Contract）の全条件を検証し、未達なら `followup_message` でエージェントに継続を促す。AI がセッション長を終了理由にする問題を構造的に防止する。

#### Layer 5: Delegation — Subagents

サブエージェントがメインコンテキストを保護しながら専門タスクを処理する。並列ビルドジョブ / 専門ワーカープールに相当。

**Cursor 組み込み Subagent（v2 追記 W2）:**

Cursor には自動でメインコンテキストを保護するために、以下の組み込み Subagent が3つ用意されている。自作 Subagent を作る前に、組み込みで要件を満たせないかを先に検討する。

| Subagent | 用途 |
| --- | --- |
| `explore` | コードベース探索（高速モデルで並列検索） |
| `bash` | シェルコマンド実行（ノイズの多い出力を隔離） |
| `browser` | ブラウザ MCP 制御 |

**自作 Subagent の活用パターン:**

| パターン | 説明 |
| --- | --- |
| 調査・分析の委譲 | 組み込み `explore` で不足する場合、専門調査 Subagent を追加 |
| 検証の委譲 | verifier パターン — 読み取り系に制限した Subagent が独立レビュー |
| 並列 Phase 実行 | 独立した Phase を `is_background: true` のサブエージェントで同時実行 |
| サブエージェントレビュー | 実装完了後にレビューを委譲（Researcher → Implementer → Reviewer 構成の簡易版） |
| インタビュー駆動 | 要件不明確時に AskUserQuestion で詳細ヒアリングしてから着手 |
| ネスト起動（Cursor 2.5+ / v2 追記 I5） | 親 Subagent が子 Subagent を起動して木構造の並列処理を組むことも可能 |

→ Subagent の設計仕様・作成ワークフロー・品質ゲートは [Section 13.4](#134-subagent) を参照。

---

### 13. Skill・Rule・Subagent・Hook の設計仕様

AI エージェントの振る舞いを制御する4種類のアーティファクト（Skill・Rule・Subagent・Hook）を新規作成・設計する際の考え方・構造仕様・作成手順・品質ゲートを解説する。各アーティファクトの「いつ・何を使うか」は [Section 12](#12-5層の実装方法) を、「どこに置くか」は [Section 14](#14-スキルルールの配置戦略) を参照。

#### 13.1 全体像と判断フロー

4つのアーティファクトは、それぞれ異なる性質・強制力・発動タイミングを持つ。

| 基準 | Skill（Layer 3） | Rule（Layer 2） | Subagent（Layer 5） | Hook（Layer 4） |
| --- | --- | --- | --- | --- |
| 性質 | 手続き的なワークフロー（手順・判断フロー） | 宣言的な制約（「〜すること」「〜してはならない」） | 別コンテキストで実行する委譲ロール | スクリプトで強制する検査プロセス |
| 発動タイミング | description のトリガー条件にマッチした時 | alwaysApply で常時、または globs/description/manual で条件的 | Task tool で明示的に呼び出し、または description ベースで自動委譲 | イベント発生時に自動実行 |
| 遵守率 | N/A | ~80%（Advisory） | N/A | ~100%（Deterministic、ただし fail-open 設定時は例外） |
| 開発プロセスのアナロジー | ランブック / 実装手順書 | コーディング規約 / lint ルール | 並列ビルドジョブ / 専門ワーカー | CI / pre-commit hook |
| 代表例 | session-handover（引き継ぎ手順） | no-remote-git（リモート操作禁止） | plan-reviewer（プランの独立レビュー） | stop hook（品質ゲート強制） |

**判断フロー:**

1. 調査・レビュー等の独立タスクを**別コンテキスト**で処理したい → **Subagent**
2. 手順が3ステップ以上 → **Skill**
3. 宣言的制約（「〜すること」「〜してはならない」）→ **Rule** 候補
4. Rule 候補のうち「繰り返し違反が観測される（3回以上）」or「違反時にデータ損失・不可逆な問題」→ **Hook** に昇格

**Skill の2層アーキテクチャ:**

Skill は汎用性と WS 固有ロジックの分離のため、2層に設計する。

| 層 | 名称 | 特徴 | 配置先 |
| --- | --- | --- | --- |
| Layer A | 疎結合スキル（Atomic） | 単一責務、他スキルに非依存、WS 固有ロジックを含めない | `~/.cursor/skills/` or `.agents/skills/` |
| Layer B | オーケストレーター（Orchestrator） | 複数スキルを組み合わせ/チェーン、WS 固有コンテキストを持つ | `.agents/skills/`（WS 固有のみ） |

判断基準:

* 他のスキルを参照/チェーンする必要があるか？ → Yes: Layer B
* WS 固有のロジック（特定のディレクトリ構造、ルール、ワークフロー）を含むか？ → Yes: Layer B
* 上記いずれも No → Layer A

設計原則:

* 疎結合スキルに WS 固有ロジックを入れない（汎用性の破壊を防ぐ）
* WS 固有のロジックはオーケストレーターに集約する
* オーケストレーターは疎結合スキルを「呼び出す/参照する」形で連携する


#### 13.2 Skill

##### 13.2.1 考え方

Skill は手続き的なワークフロー知識を SKILL.md ファイルに記述したもの。AI エージェントはセッション開始時に全スキルの description をスキャンし、ユーザーのリクエストとマッチするスキルがあれば読み込んでワークフローを実行する。

Anthropic 公式ガイドの5つの設計パターンから、作成するスキルに最適なものを選ぶ。

| パターン | 特徴 | 該当スキル例 |
| --- | --- | --- |
| Sequential Workflow | ステップを順に実行するパイプライン | session-handover（検証→記録→アーカイブ判定） |
| Multi-Service Orchestration | 複数ツール/API を組み合わせる | confluence-sync（REST API + ブラウザ MCP） |
| Context-Aware Response | コンテキストに応じて振る舞いを変える | git-ops（GitHub/その他リモート/ローカルで操作切替） |
| Domain-Specific Intelligence | 専門知識を埋め込んで適用する | lib-advisor（ライブラリ選定の知見でルーティング） |
| Iterative Refinement | 出力を反復的に改善する | plan-review（Critical→Warning→Info の段階修正） |

##### 13.2.2 構造仕様

スキルは3段階の Progressive Disclosure で設計する。

**L1: フロントマター（トリガー条件 / v2 修正 C5, W1, I4）**

```yaml
---
name: {slug}  # ケバブケース（ディレクトリ名と一致）
description: >
  [What: 何をするスキルか（1-2文）]
  [When: 発動トリガーフレーズ（Use when: ...）]
  [Negative: 発動しない場面（Do NOT use for: ...）]
disable-model-invocation: false  # true にするとスラッシュコマンド専用
license: MIT                     # 任意
compatibility: ["cursor>=2.3"]   # 任意
metadata:                        # 任意のキーバリュー
  owner: ai-infra-team
---
```

**L1 フィールド一覧（公式準拠）:**

| フィールド | 必須 | 用途 |
| --- | --- | --- |
| `name` | Yes | スキル識別子。**小文字英数字とハイフンのみ / 最大 64 文字 / XML タグ禁止 / `anthropic` `claude` を含んではならない** |
| `description` | Yes | 発火トリガー。`description` + `when_to_use` の合算が公式一覧で **1,536 文字** にトランケートされる |
| `license` | No | ライセンス名または同梱ライセンスファイル参照 |
| `compatibility` | No | 環境要件（対応 Cursor / Claude Code バージョン、ネットワーク要件等） |
| `metadata` | No | 任意のキーバリューメタデータ |
| `disable-model-invocation` | No | `true` で自動発火を無効化し、`/skill-name` 専用にする |

**本設計の L1 追加推奨（チーム標準）:**

* description は **1,024 文字以内** に収める（公式 1,536 文字より厳しく管理する）
* What + When + Negative trigger の3構造で書く
* フロントマターに XML タグ（`< >`）を含めない
* description は「スキルの要約」ではなく「いつ発火させるか」のトリガー条件。ドメインキーワードと開発者の発話パターン（日本語・英語）を含める

**L2: SKILL.md 本文（v2 修正 C4）**

* Anthropic 公式目安: **5,000 トークン未満**（英語 ≒ 3,000〜3,500 語、日本語 ≒ 2,500〜4,000 文字）
* スキルの役割、ワークフロー、出力フォーマットを記載
* L3（外部ファイル）への相対パス参照を含める
* **Gotchas セクション**（本設計の推奨）を含める（初期は空でよい。5件以上蓄積でリファクタリングを検討）

**L3: 補助ファイル**

```
{skill-slug}/
├── SKILL.md          # スキル本体（エントリーポイント）
├── config.json       # ユーザー設定（必要な場合のみ）
├── templates/        # 出力テンプレート（あれば）
├── references/       # 参照データ（あれば）
└── scripts/          # 検証スクリプト（あれば）
```

* ディレクトリ名はケバブケースで統一（`name:` フィールドと一致）
* 入口は `SKILL.md` に統一する（`README.md` を置くこと自体は公式禁止ではないが、エントリーポイントの重複を避けるため本設計では非推奨）
* Setup/Config パターン: ユーザー固有の設定が必要なスキルでは `config.json` を配置


##### 13.2.3 作成ワークフロー

**Step 1: 設計パターンの選択**

上記5パターンから最適なものを選ぶ。

**Step 2: フロントマター（L1）の設計**

description をトリガー条件として設計する。ドメインキーワードと開発者の発話パターン（日本語・英語）を十分に含める。`name` は 64 文字以内 / 小文字英数ハイフン / 予約語（`anthropic`, `claude`）禁止。

**Step 3: SKILL.md 本文（L2）の設計**

スキルの役割、ワークフロー、出力フォーマットを記載する。Progressive Disclosure で L3 への参照パスを含める。Gotchas セクションを必ず設ける。公式目安の5,000トークン未満に収める。

**Step 4: 補助ファイル（L3）の設計**

大量のデータや参照情報がある場合、INDEX → TOC/概要 → 詳細ファイルの階層で段階的に読み込む。

**Step 5: フォルダ構成**

ケバブケースのディレクトリ名で統一し、`name:` フィールドと一致させる。

**Step 6: 自己改善設計**

Gotchas セクションを入口にした Observe → Amend → Evolve サイクルを設計する（詳細は [13.6](#136-自己改善サイクル)）。

##### 13.2.4 品質ゲート

| ゲート | 検証内容 | 検証方法 |
| --- | --- | --- |
| QG1: 構造チェック | `name` が公式制約（64文字 / 予約語禁止 / XMLタグ禁止）を満たす / `description` が本設計標準 1,024 文字以内かつ公式上限 1,536 文字以内 / What+When+Negative の3構造 / SKILL.md が 5,000 トークン未満 / Gotchas セクションが存在 | 文字数・トークン数カウントと目視確認 |
| QG2: 発火テスト | 発動すべきフレーズ3つ以上で発火する / 無関係なフレーズでは発火しない | 実際にトリガーフレーズを発話して確認 |
| QG3: 機能テスト | ワークフローが期待通りに動作 / 参照チェーン（L1→L2→L3）にリンク切れがない | 実行してログを確認 |
| QG4: チェーン品質（Layer B のみ） | 参照する疎結合スキルが全て存在 / quality-gate による成果物検証が設計されている | スキル依存グラフのレビュー |
| QG5: 依存パッケージ評価（スクリプト含む場合） | メンテナンス（最終リリース1年以内）/ コミュニティ / アーキテクチャ / 代替比較 / バス係数 | 公式リポ・npm registry の確認 |

QG5 のレッドフラグ（該当すれば即却下）: 1年以上リリースなし + 後継が存在、依存バージョンが固定放置、メンテされていないフォークの採用。

#### 13.3 Rule

##### 13.3.1 考え方

Rule は宣言的な制約を `.cursor/rules/{name}.mdc` ファイルに記述したもの。「〜すること」「〜してはならない」のような行動規範であり、手順やワークフローは含めない。コーディング規約・設計原則・lint ルールと同じ位置付け。ルールの遵守率は約80%（Advisory）であり、例外なく守らせたいものは Hook に昇格させる。

**Precedence（適用順序 / v2 追記 W6）:**

Cursor の Rule は以下の順序で適用される。上位が競合時に優先。

```
Team Rules（Enterprise / Team プラン）
  ↓
Project Rules（.cursor/rules/, AGENTS.md）
  ↓
User Rules（~/.cursor/rules/, Cursor Settings）
```

##### 13.3.2 構造仕様

**Cursor Rule の4タイプ（v2 修正 C1）:**

| ルールタイプ | 条件 | description の役割 |
| --- | --- | --- |
| `Always Apply` | `alwaysApply: true`。毎セッション適用 | UI 上のラベル（トリガー設計は不要） |
| `Apply Intelligently` | `alwaysApply: false` かつ `globs` なし、`description` 必須。Agent が description ベースで関連性判断 | AI が発火判定する**トリガー条件** |
| `Apply to Specific Files` | `globs` にマッチするファイルを扱うときに適用 | UI 上のラベル |
| `Apply Manually` | `@ルール名` で明示参照時のみ | AI がルール一覧から選ぶヒント |

> `Apply Intelligently` と Skill は機能が重複する領域があり、Cursor 2.4 以降は `/migrate-to-skills` コマンドで Skill への移行が推奨される。
> 出典: [Cursor Docs - Rules](https://cursor.com/docs/rules)

**ファイル構造:**

```
---
description: [ルールの適用範囲を示すラベル、Apply Intelligently ではトリガー条件]
globs: [ファイルパターン（Apply to Specific Files の場合）]
alwaysApply: true/false
---

[ルールの本文（マークダウン）]
```

**設計原則:**

* **宣言的に書く**: 制約のみ記載し、手続きはスキルに委譲する
* **スキルと重複させない**: 同じ内容がルールとスキル両方にあると不整合が生じる（Single Source of Truth 違反）
* **行数ガイド（v2 修正 W8）**: Cursor 公式は 500 行を推奨するが、本設計では手続き混入検知のため独自に **50 行以内** を目安とする
* **description はラベルとして書く**（`Apply Intelligently` 以外の場合）: ルールの適用範囲が一目でわかる説明

**良いルールの例** — `no-remote-git.mdc`（20行）: 禁止事項を「〜してはならない」で4つ列挙 + 理由を1文で説明。手順なし、条件分岐なし、純粋な制約のみ。

**悪いルールのサイン:**

* 「Step 1, Step 2, Step 3...」のような手順がある → スキルに分離
* 同じ内容が対応するスキルにもある → ルールから削除しスキルに委譲
* 50行を超えている → 制約以外の内容が混入している（本設計基準）


##### 13.3.3 作成ワークフロー

**Step 1: ルール/スキル/Hook の判断**

作成したい内容が Rule・Skill・Hook のどれに該当するかを [13.1](#131-全体像と判断フロー) の判断フローで確認する。

**Step 2: タイプの選択**

4タイプ（Always Apply / Apply Intelligently / Apply to Specific Files / Apply Manually）からワークスペースでの用途に合ったものを選択する。Apply Intelligently は Skill への置き換えも検討する。

**Step 3: 本文の設計**

制約を宣言的に書く。手順が含まれていたらスキルへの分離を検討する。50行（本設計標準）を超えないように抑える。

**Step 4: 配置先の選択**

| 条件 | 配置先 |
| --- | --- |
| 全ワークスペース共通 | `~/.cursor/rules/` または `~/.cursor/skills/_rules/` + シンボリックリンク |
| ワークスペース固有 | `.cursor/rules/` または `AGENTS.md`（簡易用途） |

##### 13.3.4 品質ゲート

| ゲート | 検証内容 | 検証方法 |
| --- | --- | --- |
| QG-R1: 構造チェック | 50行以内（本設計） / 宣言的制約のみ / スキルとの重複なし / description が適用範囲を明示 / 公式500行以内 | 行数カウントと対応スキルの目視比較 |
| QG-R2: 制約の明確性 | 各制約が「〜すること」「〜してはならない」で表現 / 曖昧な表現（「できれば」「なるべく」）がない | 本文の表現レビュー |

#### 13.4 Subagent

##### 13.4.1 考え方

Subagent（サブエージェント）は、メインエージェントとは**別のコンテキスト**で実行される委譲ロール。メインコンテキストを保護しながら、調査・レビュー・並列処理などの専門タスクを処理する。5層モデルの Layer 5（Delegation）を実装するアーティファクトであり、パターンの詳細は [Section 12 の Layer 5](#layer-5-delegation--subagents) を参照。並列ビルドジョブや専門ワーカーに相当。

**Skill との違い:**

* **Skill** は「メインエージェントが自分で読むワークフロー」— 同じコンテキスト内で実行
* **Subagent** は「別プロセスに委譲するロール」— 独立したコンテキストで実行し、結果だけを返す

Subagent でも手順が長い場合はスキルを併用する（Subagent がスキルを読み込んで実行するパターン）。

**ネスト起動（Cursor 2.5+ / v2 追記 I5）:**

Cursor 2.5 以降、Subagent が子 Subagent を起動して木構造の並列処理を組むことが可能。ツールポリシーや Hook によってブロックもできるため、権限を階層で設計できる。

**Cursor 組み込み Subagent（再掲 / v2 追記 W2）:**

自作前にまず組み込みで要件を満たせないかを検討する。

| Subagent | 用途 | 典型ユース |
| --- | --- | --- |
| `explore` | コードベース探索 | 仕様調査、影響調査 |
| `bash` | シェルコマンド実行 | ビルド・テスト実行、ログ収集 |
| `browser` | ブラウザ MCP 制御 | E2E 動作確認、ドキュメント参照 |

##### 13.4.2 構造仕様

**配置の系統:**

| スコープ | 配置先 | 特徴 |
| --- | --- | --- |
| Cursor プロジェクトスコープ | `.cursor/agents/{name}.md` | そのプロジェクトのみ |
| Claude Code プロジェクトスコープ | `.claude/agents/{name}.md` | worktree 隔離等が可能 |
| Cursor ユーザーレベル共有 | `~/.cursor/agents/{name}.md` | 全ワークスペースで利用可能 |
| Claude Code ユーザーレベル共有 | `~/.claude/agents/{name}.md` | 全ワークスペースで利用可能 |

**ファイル構造（Cursor 準拠）:**

```yaml
---
name: {name}
description: >
  [役割の説明 + トリガー条件]
model: inherit            # inherit / fast / 具体的なモデルID
readonly: true            # 任意: true でファイル変更・シェル副作用を制限
is_background: false      # 任意: true で親をブロックせず並列実行
---

[本文: 役割・制約・出力フォーマット・手順]
```

**フロントマター主要フィールド（v2 修正 W3, W4）:**

| フィールド | 値 | 用途 |
| --- | --- | --- |
| `name` | string | 識別子 |
| `description` | string | 発火トリガー |
| `model` | `inherit` / `fast` / 具体的なモデルID（例: `claude-4-sonnet`, `gpt-5-mini`, `claude-opus-4-6`） | 使用モデル |
| `readonly` | boolean | `true` で書き込み系を制限（レビュー系に推奨） |
| `is_background` | boolean | `true` で親をブロックせずバックグラウンド実行。「Parallel Phase Runner」で有用 |

> Claude Code の Agent は frontmatter が別体系（`tools`, `disallowedTools`, `permissionMode`, `skills`, `mcpServers` 等）。詳細は [Anthropic Docs - Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)。

**使い分けパターン:**

| 役割 | readonly | is_background | 用途例 |
| --- | --- | --- | --- |
| Researcher | true | false | コードベース調査、ドキュメント探索 |
| Reviewer | true | false | プランレビュー、コードレビュー |
| Parallel Phase Runner | false | **true** | 独立した Phase の並列実行 |
| Domain Specialist | false | false | 特定ドメインの専門タスク |
| Reasoning 特化 | 任意 | 任意 | `model` に `claude-opus-4-6` 等の推論特化モデルを明示 |

##### 13.4.3 作成ワークフロー

**Step S1: 組み込みでカバーできるか確認**

`explore` / `bash` / `browser` で要件を満たせる場合は、自作せずそのまま使う。

**Step S2: 役割の選定**

上記5パターン（Researcher / Reviewer / Parallel Phase Runner / Domain Specialist / Reasoning 特化）から該当する役割を選ぶ。

**Step S3: スコープと配置先の決定**

プロジェクト固有の役割なら `.cursor/agents/` に、全ワークスペースで再利用するなら `~/.cursor/agents/` に配置する。

**Step S4: フロントマターの設計**

description をトリガー条件として設計する。tools は最小権限で設定し、レビュー系は `readonly: true` を明示する。並列用途は `is_background: true` を設定する。

**Step S5: 本文の記述**

役割・入力仕様・出力仕様・制約を記述する。出力フォーマットを具体的に指定すると、メインエージェントが結果を利用しやすくなる。

**Step S6: 呼び出しテスト**

Task tool 経由で実際に呼び出し、期待通りに動作することを確認する。

##### 13.4.4 品質ゲート

| ゲート | 検証内容 | 検証方法 |
| --- | --- | --- |
| QG-S1: 構造チェック | description がトリガー条件として機能 / tools の最小権限 / readonly / is_background が役割と整合 | フロントマターのレビューと発火想定の対話 |
| QG-S2: 動作テスト | 意図したタスクで発動 / メインコンテキストを汚染しない / 出力が期待形式 | Task tool 経由で実呼び出しして確認 |

#### 13.5 Hook

##### 13.5.1 考え方

Hook はエージェントの特定タイミングで**自動実行**されるスクリプト。ルール（Advisory、遵守率 ~80%）では不十分な場合に、**原則として Deterministic** な強制力で制約を適用する。CI / pre-commit hook / QA ゲートに相当。

> ただし公式仕様上、Hook スクリプトの失敗時は **デフォルトでフェイルオープン**（アクションを継続）であり、厳格にブロックしたい場合は明示設定が必要（Cursor では JSON で `permission: "deny"` / exit 2 / `failClosed` 相当の制御を行う）。

**Advisory → Deterministic の昇格判断:**

| 条件 | 判定 |
| --- | --- |
| ルールで繰り返し違反が観測される（3回以上） | Hook に昇格 |
| 違反時にデータ損失・不可逆な問題が発生する | Hook に昇格 |
| 違反が稀で影響が軽微 | ルールのまま |

##### 13.5.2 構造仕様

**hooks.json のスキーマ（Cursor 準拠 / v2 修正 C2, C3, W9, I2）:**

```json
{
  "version": 1,
  "hooks": {
    "<event>": [
      {
        "command": "<script-path>",
        "timeout": 15,
        "matcher": "<pattern>"
      }
    ]
  }
}
```

| パラメータ | 必須 | 説明 |
| --- | --- | --- |
| `command` | Yes | 実行するスクリプトのパス |
| `timeout` | No | タイムアウト秒数（公式デフォルトは環境依存） |
| `matcher` | No | 対応イベントでのフィルタ（例: `afterFileEdit`, `beforeShellExecution`, `preToolUse`） |
| `loop_limit` | No | **注意**: Cursor 公式 hooks.json スキーマでは確認不可。Claude Code 系では `stop_hook_active` 等の別機構あり。本設計で採用する場合は実装検証を必須とする（v2 修正 W9） |

**利用可能なイベント（Cursor 公式、キャメルケース / v2 修正 C2）:**

| イベント | タイミング | 主な用途 |
| --- | --- | --- |
| `sessionStart` / `sessionEnd` | セッション開始・終了 | 環境チェック、コンテキスト注入、監査 |
| `preToolUse` / `postToolUse` / `postToolUseFailure` | ツール実行前後 | 汎用ツール制限・監査 |
| `subagentStart` / `subagentStop` | サブエージェント開始・終了 | 委譲の監視・制御 |
| `beforeShellExecution` / `afterShellExecution` | シェル実行前後 | 危険コマンドブロック、実行ログ |
| `beforeMCPExecution` / `afterMCPExecution` | MCP ツール実行前後 | MCP 経由操作の制御 |
| `beforeReadFile` / `afterFileEdit` | ファイル操作前後 | 機密検知、フォーマット |
| `beforeSubmitPrompt` | プロンプト送信前 | プロンプト検査 |
| `preCompact` | コンパクション発生前 | 追跡ドキュメントへの書き込み促進 |
| `stop` | エージェント停止時 | 品質ゲート強制、未完了検知 |
| `afterAgentResponse` / `afterAgentThought` | レスポンス・思考後 | ログ・分析 |
| `beforeTabFileRead` / `afterTabFileEdit` | Tab（インライン補完）専用 | Tab 向けの軽量制御 |

> Claude Code 側は `PreToolUse` `SessionStart` `Stop` 等の**パスカルケース**で別体系。[Cursor Docs - Third Party Hooks](https://cursor.com/docs/reference/third-party-hooks) が互換読み込みを提供。

**stdin/stdout の JSON プロトコル:**

* **入力**: `{"transcript_path": "...", "file_path": "...", "command": "...", "tool_name": "..."}` 等（イベントにより異なる）
* **出力**: 以下のいずれか

**出力フィールド一覧（v2 追記 I2）:**

| フィールド | 用途 |
| --- | --- |
| `permission` | `"allow"` / `"ask"` / `"deny"`（`beforeShellExecution` 等） |
| `user_message` | ユーザー向け表示メッセージ |
| `agent_message` | Agent 向けメッセージ（次の行動誘導） |
| `continue` | 処理継続フラグ |
| `decision` | `"block"` 等 |
| `reason` | 判断理由 |
| `followup_message` | stop hook 等で継続を促すメッセージ |

**exit code（v2 修正 C3）:**

| exit code | 意味 |
| --- | --- |
| `0` | 成功、JSON 出力を使用 |
| `2` | アクションをブロック（`permission: "deny"` と等価、簡易ブロック用） |
| その他 | フック失敗、アクションは継続（フェイルオープン） |

ブロック方法は「exit 2（簡易）」と「exit 0 + JSON で `permission: "deny"` を返す（詳細メッセージ付き）」の2通りから選択する。

**設計原則:**

* **フェイルオープン**: スクリプト障害時は何もしない（ワークフローを阻害しない）。ただしセキュリティ/データ損失系は `failClosed` 相当の設定で明示的にブロックする
* **コマンドベース優先**: まずコマンドベース（外部スクリプト実行）で実装し、必要に応じてプロンプトベース（LLM へのプロンプト注入）を検討する
* **Deterministic + Advisory ハイブリッド**: 検知は確実に行い、判断基準を `followup_message` / `agent_message` に含めて AI に委ねるパターンが有効

**配置先:**

| スコープ | hooks.json の配置 | スクリプトの配置 |
| --- | --- | --- |
| ユーザーレベル | `~/.cursor/hooks.json`（`_hooks/` への symlink） | `~/.cursor/skills/_hooks/` |
| プロジェクトレベル | `.cursor/hooks.json` | `.cursor/hooks/` or スキル内の `scripts/` |

##### 13.5.3 作成ワークフロー

**Step H1: Advisory → Deterministic の昇格判断**

上記の昇格判断表で Hook 化が必要か確認する。

**Step H2: Hook イベントの選択**

利用可能なイベントから、目的に合ったタイミングを選ぶ。「シェル特化」なら `beforeShellExecution`、「汎用ツール」なら `preToolUse`、「停止時強制」なら `stop`。

**Step H3: コマンドベース vs プロンプトベースの選択（v2 修正 I3）**

* **コマンドベース（推奨）**: 外部スクリプト実行。Deterministic な検証に適する
* **プロンプトベース**: `type: "prompt"` で **全イベントにサポート**。`{ ok: boolean, reason?: string }` 形式で返す簡易ポリシー判定。`model` フィールドで評価用モデルを指定可能。`$ARGUMENTS` プレースホルダで hook 入力 JSON を挿入できる

**Step H4: hooks.json の設計**

上記スキーマに従い hooks.json を作成する。配置先（ユーザーレベル vs プロジェクトレベル）を決定する。

**Step H5: スクリプトの実装**

フェイルオープン原則に従い、入力不正時は `{}` を返して exit 0 で終了するように実装する。データ損失系などフェイルクローズにしたい場合は exit 2 / `permission: "deny"` を明示的に使う。

**Step H6: テスト・デバッグ**

1. `chmod +x` でスクリプトに実行権限を付与
2. ダミー JSON を echo で stdin に渡して出力を確認
3. Cursor Settings > Hooks タブで認識を確認
4. 期待されるイベントで発火すること、不要なイベントでは発火しないことを検証


##### 13.5.4 品質ゲート

| ゲート | 検証内容 | 検証方法 |
| --- | --- | --- |
| QG-H1: 構造チェック | hooks.json が有効な JSON / version: 1 指定 / イベント名が公式表記（キャメルケース）/ スクリプトに実行権限 / フェイル戦略（open/closed）が明示 | JSON パース + stat + ソースコードレビュー |
| QG-H2: 動作テスト | 期待イベントで発火 / 不要イベントでは非発火 / JSON 出力構造が正しい / timeout 内に完了 / exit 2 / `permission: "deny"` が意図通り機能 | ダミー JSON の echo stdin 投入と実環境での発火確認 |

#### 13.6 自己改善サイクル

各アーティファクトに共通する改善サイクル。作って終わりではなく、運用から継続的に改善する。開発現場の **ポストモーテム / レトロスペクティブ / 継続的改善** と同じ営みを、AI アーティファクトに対して回す。

* **Observe**: 発火漏れ・誤った出力・非効率な手順を検知する仕組み（Gotchas セクション + session-handover での確認）
* **Amend**: 検知した問題を Gotchas に追記し、再発を防止する（= バグチケット起票相当）
* **Evolve**: Gotchas が5件以上蓄積したら、アーティファクトの構造自体をリファクタリングする（= リファクタリング PR 相当）

Gotchas 検知のトリガー例:

1. 開発者が「期待と違う」等の不一致を表明した
2. 同じ問題で2回以上修正が必要になった
3. スキルの手順に従ったのに想定外の結果が出た

---

### 14. スキル・ルールの配置戦略

スキル・ルールは3層に配置され、各層が異なるスコープを持つ。Cursor は `.agents/skills/` と `.cursor/skills/` を一次的にロードし、互換性サポートとして `.claude/skills/` `.codex/skills/` も読み込める（v2 修正 W5）。

```
~/.cursor/skills/              # ユーザーレベル共有（Git管理）
├── _rules/                    # 共有ルール実体
├── session-planning/          # セッション管理（全WS共有）
├── session-handover/
├── decisions-record/
├── plan-review/               # 品質管理（全WS共有）
├── quality-gate/
├── create-skill-rule/
└── ...                        # その他の汎用スキル

repo-root/
├── CLAUDE.md                  # Claude Code の Context ファイル（SoT）
├── AGENTS.md                  # Cursor の Context ファイル（.cursor/rules 代替、ネスト可）
├── .agents/skills/            # WS固有スキル（オープン標準、Cursor プライマリ）
├── .cursor/skills/            # WS固有スキル（Cursor プライマリ）
├── .cursor/rules/             # WS固有ルール
├── .cursor/agents/            # Cursor サブエージェント
├── .claude/skills/            # Claude Code スキル（Cursor は互換読み込み）
├── .claude/settings.json      # Claude Code 設定
├── .claude/agents/            # Claude Code サブエージェント
└── .codex/skills/             # OpenAI Codex CLI スキル（Cursor は互換読み込み）
```

**配置の判断基準（v2 修正 W5）:**

| 対象 | 配置先 | 理由 |
| --- | --- | --- |
| 全WS共通スキル | `~/.cursor/skills/` または `~/.agents/skills/` | Git 一元管理 |
| 全WS共通ルール | `~/.cursor/rules/` または `~/.cursor/skills/_rules/` | シンボリックリンクで自動読み込み |
| WS固有スキル（Cursor プライマリ） | `.agents/skills/` または `.cursor/skills/` | Cursor の一次ロード先 |
| WS固有ルール | `.cursor/rules/` または `AGENTS.md` | Cursor の Always Apply / Apply Intelligently / AGENTS.md |
| Cursor サブエージェント | `.cursor/agents/` | Cursor 機能 |
| Claude Code サブエージェント | `.claude/agents/` | Claude Code 機能 |
| Claude Code スキル | `.claude/skills/` | Claude Code 一次配置。Cursor は互換読み込み |
| Codex 互換スキル | `.codex/skills/`, `~/.codex/skills/` | OpenAI Codex CLI 連携。Cursor は互換読み込み |
| Claude Code 設定 | `.claude/settings.json` | allowedTools、permissionMode 設定 |

---

### 15. クロスツール連携

同じスキル・追跡ドキュメントを Cursor と Claude Code で共有できる。

| 操作 | ツール | セッション管理との関係 |
| --- | --- | --- |
| 壁打ち・相談 | Cursor Ask モード | セッション管理スキルは非活性 |
| 実装・分析 | Cursor Agent モード | 大規模タスク検知 → session_planning が自動発動 |
| 自律実行 | Claude Code | 同じスキルが動作（`.agents/skills/` はポータブル、`.claude/skills/` は Claude Code 一次） |
| モバイル確認 | Claude モバイル | 追跡ドキュメントを読んで状況把握 |

**Claude Code の拡張チャネル:**

| チャネル | 用途 |
| --- | --- |
| `/loop` | 定期プロンプト実行（例: `/loop 5m check deploy`） |
| Agent Teams | マルチセッション協調（3-5人のチームメイト） |
| `remote-control` | スマホからのリモート操作 |
| SDK 連携 | 外部メッセージングアプリとの統合 |

**Claude Code の公式メモリ機構 + サードパーティ連携（v2 修正 C6）:**

公式のメモリ機能は以下で構成される。

* `CLAUDE.md`（プロジェクトルート、ユーザーグローバルは `~/.claude/CLAUDE.md`）
* `/memory` スラッシュコマンドによる編集
* Anthropic API レベルの新設メモリツール（利用可能な場合）

これに加えて、サードパーティ OSS の `claude-mem`（npm パッケージ、Claude Code 本体機能**ではない**）を導入する運用もある。公式と役割を分ける場合の整理:

* 公式 `CLAUDE.md` + `/memory` = プロジェクト文脈の一次ソース（明示管理）
* サードパーティ `claude-mem` = 暗黙的なコンテキスト補完ツール（導入時はセキュリティ・保守性評価が必須）
* 本設計の追跡ドキュメント = 明示的な引き継ぎファイル（Source of Truth）

二重保護でセッション間の文脈断絶をさらに最小化できるが、サードパーティ採用時はチームとしてのレビューを実施する。

---

### 16. 新規ワークスペースの立ち上げ

#### パスA: 新規ワークスペースの場合

**前提:** ブートストラップスクリプト `bootstrap-workspace` が `~/.local/bin/` に配置されている（PATH に含まれるため、どこからでも呼び出し可能）。スクリプトは最小限の CLAUDE.md / AGENTS.md（パターン選択フローへの誘導を含む）と基本ディレクトリ構造を生成する。

```
1. ブートストラップスクリプトを実行
   $ bootstrap-workspace ~/work/new-project
   → ディレクトリ作成 + 最小限の CLAUDE.md / AGENTS.md 生成

2. Cursor / Claude Code でワークスペースを開く
   $ cd ~/work/new-project && cursor .

3. 開発責任者（PO）が以下のいずれかで初期パターンを確定:
   - AI が CLAUDE.md / AGENTS.md を読み、パターン選択フロー（Section 8 の4問）を提示 → PO 回答
   - もしくはフロントマターで直接宣言（儀式を省略）

4. AI がブループリント（Section 9-11）に従い5層をセットアップ:
   Layer 1: CLAUDE.md / AGENTS.md をプロジェクト固有の内容に更新
   Layer 2: .cursor/rules/ にWS固有ルール配置
   Layer 3: .agents/skills/ または .cursor/skills/ にセッション管理スキル群を配置
   Layer 4: hooks.json（必要に応じて）
   Layer 5: .cursor/agents/（必要に応じて。まず組み込み explore/bash/browser で十分か確認）
```

**例: 新しい Web アプリワークスペースを作る場合:**

1. `bootstrap-workspace ~/work/new-web-app && cd ~/work/new-web-app && cursor .`
2. PO が即決: アウトプット = 動くアプリ → **開発型**（AI に4問ヒアリングさせる必要はない）
3. AI が開発型ブループリント（Section 9）の「必要なドキュメント・スキル」をセットアップ
4. AI が技術スタックに合わせて品質ゲートのコマンドをカスタマイズ

**技術スタック別の品質ゲートカスタマイズ:**

| スタック | テスト | ビルド / 型チェック |
| --- | --- | --- |
| Node.js / TypeScript | `npm test` | `npm run build` + `npx tsc --noEmit` |
| Rust | `cargo test` | `cargo build` |
| Python | `pytest` | `mypy` |
| Go | `go test ./...` | `go build ./...` |

#### パスB: 既存ワークスペースの新キャンペーン

```
session_planning スキル発動
  → 追跡ドキュメントが存在するか？
    → Yes: 既存キャンペーンの続き → 追跡ドキュメントを更新
    → No:  新キャンペーン → パターン選択フロー → 追跡ドキュメントを新規作成
```

5層インフラは整備済みのため、追跡ドキュメントの作成のみで開始できる。

---

### 17. コンパクション回避の実践

**手動操作（v2 修正 C8）:**

| コマンド | 用途 | ツール |
| --- | --- | --- |
| `/compact` | コンテキストを手動圧縮 | Claude Code / Cursor 公式 |
| `/clear` | 無関係なタスク間のリセット | Claude Code / Cursor 公式 |
| `/rewind` | 履歴を戻す（代替アプローチを試す） | Claude Code 公式 |
| `/resume` | 過去セッション再開 | Claude Code 公式 |
| `Cmd+Shift+L` | 新規チャット（分岐）を開く | Cursor キーボードショートカット |

> v1 に記載の `/branch` は公式仕様上存在しないため削除。異なるアプローチを試す分岐は `/rewind`（Claude Code）または新規チャット `Cmd+Shift+L`（Cursor）で代替する。

**セッション長による早期終了の防止:**

AI はセッション長を正当な終了理由と認識しがちだが、Task Contract で完了条件を明示的に定義し、stop Hook で条件を満たすまで終了を抑制する。

**将来の自動化:**

* `preCompact` Hook で追跡ドキュメント更新を自動促進
* `stop` Hook で品質ゲート実行を促す `followup_message`
* Notification Hooks でコンパクション発生を外部通知（Slack 等）
* Task Contract + Stop-hook で契約条件未達の終了を自動抑制

---

## Appendix

### Appendix A: 設計原則の根拠と一次情報ソース

本設計の原則6-8および Layer 3-5 の強化は、AI エージェント設計の4人の海外実践者の一次情報に基づく。

**4つの一次情報ソース:**

| ソース | 専門領域 | 主な知見 |
| --- | --- | --- |
| Thariq | Skills / Caching / CLAUDE.md 設計 | Progressive Disclosure、オンデマンドフック、コンテキストコスト管理 |
| SysLS | エージェント工学 7原則 | Task Contract、Sycophancy 対策、3エージェント構成 |
| Vasilije | 自己改善サイクル | DGM-Hyperagents、Observe → Amend → Evolve |
| Vishwas | 実践 Tips | CLAUDE.md 品質管理、Advisory vs Deterministic |

#### 原則1-5 の根拠

複数の実開発ワークスペース（Web/ネイティブアプリ開発、データパイプライン、SDD ドキュメント基盤）での実運用から帰納的に導出した。詳細は [Appendix B](#appendix-b-実運用から得た知見) を参照。

* **原則1（単一ファイル）**: 開発ワークスペースで plan.md・handover・開始メッセージの三重管理が問題化 → 追跡ドキュメントの一元化で解決
* **原則2（スクリプトで実装）**: 検証ゲートが自然言語指示のみだったため AI が検証なしに走り続けた → スクリプト化で確実な実行を保証
* **原則3（最小 Human-in-the-Loop）**: handover の「儀式」コストが毎セッション発生 → 開発者の介入を3点に限定し、残りは AI 自律
* **原則4（即時外部化）**: decisions_record スキルが設計判断の永続化に成功（= ADR の運用自動化）→ 全パターンに横展開
* **原則5（コンテキスト保護）**: 追跡ドキュメントに agent-transcript のリンクを含めると、再開時にコンテキストが爆発する問題を経験 → リンク衛生 + アーカイブ境界


#### 原則6: コンテキストコストの管理（v2 追記 I1）

AI へのルール・スキル・CLAUDE.md の総量は、**2つのコスト**として開発者が意識すべきリソース:

1. **コンテキストウィンドウのトークン量制約**: 常時ロードされる指示（CLAUDE.md + alwaysApply ルール）はトークンを消費し、有効な作業領域を圧迫する
2. **ルール探索コスト O(N)**: AI はセッション開始時に全スキルの description を走査する。スキル数が増えるほど発火判定コストと誤発火リスクが増える

**Anthropic 公式のトークン見積り:**

| Level | 常時ロード? | 目安コスト |
| --- | --- | --- |
| L1 メタデータ（description） | Yes（起動時） | 約 100 トークン / スキル |
| L2 SKILL.md 本文 | トリガー時 | 5,000 トークン未満 |
| L3 参照・スクリプト | 参照時のみ | 実質無制限 |

対策:

* **Thariq**: スキルの description はトリガー条件として設計し、常時ロードされる指示量を最小化する
* **Vishwas Tip 29**: CLAUDE.md の各指示に「この指示がなければ AI は間違えるか？」のリトマステストを適用
* **実効的な上限の目安**: システムプロンプトがツール定義で一定量を占める中で、常時ロードされる指示（alwaysApply + CLAUDE.md + スキル L1 × N）は合計で**数千トークン以内**に収めるのが無難。Progressive Disclosure で必要な層だけ読み込ませる


#### 原則7: Advisory vs Deterministic

* **Vishwas Tip 38**: Rules に書いた指示の遵守率は ~80%。例外なく守らせたいものは Hooks で実装
* **Thariq**: オンデマンドフック設計 — スキルから一時的にフックを登録し、特定作業中だけ制約を有効化
* **SysLS**: 「エージェントに対してはコードでポリシーを制定する」— 人間の善意ではなくコードで制約を強制
* **注意**: Hook も公式仕様上はデフォルトでフェイルオープン。厳格なブロックが必要な場合は `exit 2` / `permission: "deny"` / `failClosed` 相当の明示設定を行う


#### 原則8: 自己改善サイクル

* **Vasilije**: DGM-Hyperagents — 改善プロセスそのものを編集・進化の対象にするメタ層。現時点では手動の Evolve ステップで対応するが、将来的に合成評価やフィードバック自動集約と組み合わせて改善プロセス自体の自動改善を検討
* **Vishwas Tip 30**: Gotchas セクションを全スキル・CLAUDE.md に設け、失敗から継続的に学習する仕組みを構築（= ポストモーテムを運用ログとして残す）

---

### Appendix B: 実運用から得た知見

開発ドメインのセッション管理を実運用した結果の教訓を、パターンごとに整理する。

#### 開発型で得た知見

* **性質**: Web / ネイティブアプリ / ライブラリ / CLI の実装
* **守りたいこと**: 自動テストを必ず行い、リグレッションなくリリースまで運べるフロー

| 効いたこと | 詳細 |
| --- | --- |
| 品質ゲートの強制 | テスト + ビルド + 型チェック + lint がセッション完了の必須条件 |
| 4段階テスト検証 | 単一テスト → ファイル → 全件の段階的拡大で無駄な待ち時間を排除 |
| テストリスト必須化 | 実装前に正常系/異常系/境界値を設計（= Given-When-Then の事前記述） |
| decisions_record（ADR 自動化） | 設計判断の即時外部化でセッション間の判断根拠を保持 |

| ダメだったこと | 原因 → 解決策 |
| --- | --- |
| handover の「儀式」が重い | 三重管理 → plan.md への一元化（原則1） |
| 毎セッション再プランニング | plan が変わっていないのに再計画 → 「未完了を続行」で解消 |

#### パイプライン型で得た知見

* **性質**: スクリプト / ETL / スクレイピング / バッチ生成
* **守りたいこと**: AI の幻覚を防ぎ、出力データの厳格さ（スキーマ・件数・整合性）を保つ

| 効いたこと | 詳細 |
| --- | --- |
| playbook 一元化 | 計画 = 進捗 = 引き継ぎ。「未完了を続行」の1行で再開可能 |
| 並列 Phase 実行 | サブエージェント（`is_background: true`）で独立 Phase を同時実行しスループット向上 |

| ダメだったこと | 原因 → 解決策 |
| --- | --- |
| AI が検証なしに走り続ける | Phase 間の品質チェック不在 → `verify_output.py` の追加 |
| AI 幻覚に気づけない | スクリプト経由でないデータ生成の検証がない → スクリプト出力の存在確認を必須化 |

#### ドキュメント型で得た知見

* **性質**: SDD 成果物（仕様書・設計書・ADR・ランブック・API ドキュメント・議事録）
* **守りたいこと**: ドキュメントの完全性と整合性（相互参照・用語統一・版管理）

| 効いたこと | 詳細 |
| --- | --- |
| session_plan.md 一元化 | playbook 方式の利点を継承 |
| decisions-record 横展開 | 開発型の成果（ADR 自動化）をドキュメント型にも適用 |
| plan-quality.mdc 共有化 | 影響調査 + 品質ゲートを全WSに横展開 |

**Gotchas 検知トリガーの実践例（原則8の実践）:**

CLAUDE.md に以下の3条件を明文化し、スキル利用時の失敗を自動的に記録提案:

1. 開発者が「期待と違う」等の不一致を表明した
2. 同じ問題で2回以上修正が必要になった
3. スキルの手順に従ったのに想定外の結果が出た

---

### Appendix C: 用語集

本ドキュメントで使用する主要な用語を3つのカテゴリに分けて整理する。

#### ドキュメント固有の概念

| 用語 | 説明 |
| --- | --- |
| キャンペーン | ひとまとまりの作業群。プロジェクトとは異なるスコープ単位で、1プロジェクト内で複数発生しうる（例: 機能A実装 → バグ修正 → リファクタ）。[Section 6](#6-追跡ドキュメントのライフサイクル) |
| 追跡ドキュメント（Tracking Artifact） | 計画・進捗・引き継ぎを1つのファイルに集約したもの。plan.md / playbook.md / session_plan.md の総称。[Section 2](#2-3つの構成要素) |
| 検証ゲート（Verification Gate） | セッション終了時にアウトプットの品質を検証する仕組み。[Section 2](#2-3つの構成要素) |
| 再開プロトコル（Resume Protocol） | 次セッション開始時にコンテキストを復元する手順。[Section 2](#2-3つの構成要素) |
| 5層モデル（Layer 1-5） | セッション管理の実装を5つの層に整理したアーキテクチャ。[Section 5](#5-5層モデル開発プロセス対応) |
| 開発型 / パイプライン型 / ドキュメント型 | ワークスペースのアウトプットの性質に基づく3つのパターン。[Section 3](#3-パターンを決める2つの軸) |
| セッション境界ゲート | セッション完了時に実行する品質チェック |
| Phase境界ゲート / フェーズ境界ゲート | 開発フェーズやパイプラインの Phase 完了時に実行する品質チェック |
| リンク衛生（Link Hygiene） | 追跡ドキュメントにセッション ID や大規模ファイルへのリンクを含めないルール |
| アーカイブ境界（Archive Boundary） | 完了した追跡ドキュメントを `archive/` に移動し、AI の読み込み対象から外す仕組み |
| コンテキストコスト | トークン量制約（常時ロード指示のサイズ）+ ルール探索コスト O(N)（スキル数に対する発火判定コスト）の総称。[原則6](#4-設計原則) |
| Advisory vs Deterministic | AI への指示の強制力の2分類。Advisory（Rules、~80%）と Deterministic（Hooks、~100% / 公式デフォルトはフェイルオープン）。[原則7](#4-設計原則) |
| Task Contract | エージェントの完了条件を明示的に定義し、途中終了を防止する仕組み。[Section 12](#12-5層の実装方法) |
| SDD（Spec-Driven Development） | 仕様駆動開発。要件定義 → 仕様書 → 実装 → 検証の流れで、仕様ドキュメントを Source of Truth として扱う開発スタイル |
| ADR（Architecture Decision Record） | 設計判断を構造化して記録する形式。DECISIONS.md に蓄積する |
| AI上流工程リファレンス | 4人の一次情報ソースを調査・統合した社内ナレッジ文書群 |
| Thariq / SysLS / Vasilije / Vishwas | AI エージェント設計の一次情報ソース4人。[Appendix A](#appendix-a-設計原則の根拠と一次情報ソース) |
| Meta 層（大文字ドキュメント） | v3 で正式採用された命名規約の片方。判断フレームワーク・運用ルール・記録フォーマット等、**他プロジェクトに移植しても役割名として通用する**ドキュメント。例: `DECISIONS.md`, `QUALITY_GATE.md`, `AGENT_RUNBOOK.md`, `GOTCHAS.md`。[§12 Layer 1](#layer-1-context--claudemd--agentsmd) |
| Domain 層（小文字ドキュメント） | v3 で正式採用された命名規約の片方。**このリポジトリ固有の業務仕様・実装詳細・独自ワークフロー**を記述するドキュメント。kebab-case で命名。例: `spec.md`, `architecture.md`, `api.md`, `workflows.md`。[§12 Layer 1](#layer-1-context--claudemd--agentsmd) |

#### AIエージェント管理の用語

| 用語 | 説明 |
| --- | --- |
| コンテキストアーキテクチャ | 知識の分割・同期・圧縮・再構築を設計する考え方。セッション管理の設計課題の本質。[Section 1](#1-セッション管理とは何か) |
| コンテキストウィンドウ | AI が1回のセッションで処理できるテキスト量の上限。プロセスの RAM に相当 |
| コンパクション | コンテキストウィンドウ上限時の強制圧縮処理。情報の欠落が生じうる。[Section 7](#7-コンパクション回避の考え方) |
| Lost in the Middle | 長いコンテキストの中央付近の情報が AI に無視されやすい現象 |
| コンテキストドリフト | セッションを重ねるうちに AI の理解が実態からずれていく現象 |
| AI 幻覚（ハルシネーション） | AI が事実に基づかない情報を生成する現象 |
| Progressive Disclosure | 必要なタイミングで必要な情報だけを段階的に提示する設計パターン |
| Hooks | エージェントの特定タイミングで自動実行されるスクリプト。Cursor はキャメルケース（`preToolUse` 等）、Claude Code はパスカルケース（`PreToolUse` 等）。[Section 12](#12-5層の実装方法) |
| フェイルオープン（Fail-Open） | Hook スクリプト障害時にワークフローを阻害しない設計方針（公式デフォルト）。[Section 13](#13-skillrulesubagenthook-の設計仕様) |
| フェイルクローズ（Fail-Closed） | Hook 失敗時にアクションをブロックする設計方針。セキュリティ/データ損失系で `failClosed` 等の明示設定で使う |
| 疎結合スキル / オーケストレーター（Atomic / Orchestrator） | スキルの2層アーキテクチャ。Layer A（汎用・単一責務）と Layer B（WS 固有・スキルチェーン）。[Section 13](#13-skillrulesubagenthook-の設計仕様) |
| alwaysApply | Cursor のルール属性。true で全セッションに常時自動適用 |
| Apply Intelligently | Cursor の Rule タイプ。description ベースで Agent が関連性判断して発火。Skill との役割重複あり |
| Agent Skills オープン標準 | Anthropic が定めたスキルの配置・記述の標準仕様 |
| frontmatter | SKILL.md 先頭の YAML メタデータ。トリガー条件を含む。[Section 13](#13-skillrulesubagenthook-の設計仕様) |
| disable-model-invocation | Skill の frontmatter フィールド。`true` で自動発火を抑止し `/skill-name` 専用にする |
| 組み込み Subagent | Cursor が標準で提供する `explore` / `bash` / `browser`。[Section 13.4](#134-subagent) |
| DGM-Hyperagents | 改善プロセスそのものを進化対象にする概念。[Appendix A](#appendix-a-設計原則の根拠と一次情報ソース) |
| Gotchas | スキルや CLAUDE.md の「失敗から学んだこと」記録セクション。開発現場のポストモーテム運用ログに相当。[原則8](#4-設計原則) |
| agent-transcript | エージェントの対話ログ JSONL ファイル。追跡ドキュメントからリンク禁止 |
| claude-mem | **サードパーティ OSS（npm パッケージ）**。Claude Code 本体の公式機能ではなく、公式の `CLAUDE.md` + `/memory` メモリを補完する外部ツール。[Section 15](#15-クロスツール連携) |
| Permission Mode | Claude Code の権限モード。`default` / `acceptEdits` / `plan` / `bypassPermissions` の4種。`Shift+Tab` で循環切替。[Section 12](#12-5層の実装方法) |
| bypassPermissions | Permission Mode の一種。全権限を自動承認（通称 YOLO モード）。v1 で「Auto Mode」と呼んでいた状態 |
| Sycophancy（迎合性） | AI が人間に迎合し誤りを指摘しない傾向。3エージェント構成で対策 |

#### 略語・一般用語

| 用語 | 説明 |
| --- | --- |
| ADR（Architecture Decision Record） | 設計判断を構造化して記録する形式 |
| PO（Product Owner） | 本ドキュメントでは**開発責任者**（PO / PdM / PjM / PL / TL）を指す。リポジトリに対して技術判断の最終権限を持つ役割 |
| V字モデル | 開発工程とテスト工程を対応付けたソフトウェア開発モデル |
| Human-in-the-Loop | プロセスに人間の判断・承認を組み込む設計パターン |
| SDD | Spec-Driven Development（仕様駆動開発） |
| TDD | Test-Driven Development（テスト駆動開発） |
| CLAUDE.md | Claude Code がプロジェクトの文脈を理解するための設定ファイル |
| AGENTS.md | Cursor がプロジェクトの文脈を理解するための設定ファイル。`.cursor/rules` の簡易代替、ネスト対応 |

---

### Appendix D: 参照

#### 外部リソース

* [Anthropic Agent Skills Overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) — Anthropic 公式
* [Anthropic Agent Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — Anthropic 公式
* [Anthropic Docs - Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents) — Claude Code サブエージェント
* [The Complete Guide to Building Skills for Claude](https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf) — Anthropic 公式スキル設計ガイド
* [将軍スキルクリエイター v2](https://zenn.dev/shio_shoppaize/articles/shogun-skill-creator-v2) — スキル設計の実践知見
* [コンテキスト設計こそが核心](https://zenn.dev/shio_shoppaize/articles/shogun-context-architecture) — コンテキストアーキテクチャの理論
* [Cursor Rules](https://cursor.com/docs/rules), [Skills](https://cursor.com/docs/skills), [Subagents](https://cursor.com/docs/subagents), [Hooks](https://cursor.com/docs/hooks) — Cursor 公式ドキュメント
* [Cursor Third Party Hooks](https://cursor.com/docs/reference/third-party-hooks) — Claude Code 互換読み込み

---

### Appendix E: 開発責任者視点で作るべきドキュメントリスト

元資料（経営視点版）には**開発プロジェクトで本来必要なドキュメントの多くが抽象レベルでしか触れられていない**。開発責任者（PO）が AI エージェント開発基盤を実運用する上で、別途整備すべきドキュメントを以下に列挙する。

> **命名規約について（v3 正式採用）**: 本 Appendix のドキュメントは **Meta 層（大文字）** と **Domain 層（小文字 kebab-case）** の2層に分類している。分類基準は [§12 Layer 1 の「ドキュメント命名規約 — semantic 2層モデル」](#layer-1-context--claudemd--agentsmd) を参照。原則として、**判断フレームワーク/運用ルール/記録フォーマットは Meta 層（大文字）**、**プロジェクト固有の業務仕様/実装詳細は Domain 層（小文字）** として作成する。

#### E.1 仕様・設計ドキュメント（SDD 成果物）

> **命名**: このカテゴリは**主に Domain 層（小文字 kebab-case）**。中身が各プロジェクト固有の業務仕様になるため。ただし `DECISIONS.md`（ADR）は判断フレームワーク＝ Meta 層として大文字を維持する。

| ドキュメント | 層 | 目的 | 推奨パス |
| --- | --- | --- | --- |
| `docs/spec.md` / `docs/spec/*.md` | Domain | 機能仕様書（What）。ユーザーストーリー・入出力・受入条件を定義 | 各リポジトリ直下 |
| `docs/requirements.md` | Domain | 要件定義（機能要件 + 非機能要件: 性能/可用性/セキュリティ/運用） | 各リポジトリ直下 |
| `docs/architecture.md` | Domain | アーキテクチャ設計（コンポーネント図・データフロー・技術選定理由） | 各リポジトリ直下 |
| `docs/DECISIONS.md`（ADR） | **Meta** | 設計判断の時系列記録。記録フォーマット（Title/Status/Context/Decision/Consequences）が汎用フレームワーク | 各リポジトリ直下 |
| `docs/data-models.md` | Domain | データモデル / スキーマ定義（パイプライン型で特に重要） | 各リポジトリ直下 |
| `docs/api.md` | Domain | 外部 API 仕様（提供する API・利用する API の両方） | 各リポジトリ直下 |

#### E.2 実装・運用ドキュメント

> **命名**: `README.md` / `CHANGELOG.md` は Meta 層（GitHub 等の識別対象・汎用役割）。`RUNBOOK.md` はカテゴリ名として Meta 層、個別の runbook（`RB-XXX-*.md`）は ID プレフィックス + 小文字タイトルの混在表記。`onboarding.md` / `dev-env.md` / `troubleshooting.md` は中身が各プロジェクト固有のため Domain 層。

| ドキュメント | 層 | 目的 | 推奨パス |
| --- | --- | --- | --- |
| `README.md` | **Meta** | セットアップ手順・開発開始までの最短経路（`make setup` で動くレベルの具体性） | リポジトリ直下 |
| `docs/onboarding.md` | Domain | 新メンバー（人間 / AI 両方）向けオンボーディング手順 | 各リポジトリ |
| `docs/dev-env.md` | Domain | 開発環境構築（OS・ツールバージョン・環境変数・必須サービス） | 各リポジトリ |
| `docs/runbooks/RB-XXX-*.md`（または `docs/RUNBOOK.md`） | Meta/Domain 混在 | 運用手順書。カタログ ID は大文字、個別本文は kebab-case | 各リポジトリ |
| `docs/troubleshooting.md` | Domain | 既知の詰まりポイントと復旧手順 | 各リポジトリ |
| `CHANGELOG.md` | **Meta** | 変更履歴（SemVer 準拠。Keep a Changelog 形式の汎用フォーマット） | リポジトリ直下 |

#### E.3 テスト・品質ドキュメント

> **命名**: 品質ゲート/テスト戦略/パフォーマンス予算/SLO は「判断基準フレームワーク」＝ Meta 層。テストケース一覧は中身がプロジェクト固有のため Domain 層。

| ドキュメント | 層 | 目的 | 推奨パス |
| --- | --- | --- | --- |
| `docs/TEST_STRATEGY.md` | **Meta** | テスト戦略（単体/結合/E2E の範囲・カバレッジ目標・責務分担） | 各リポジトリ |
| `docs/test-cases.md` | Domain | 代表的なテストケース一覧（TDD テストリストの蓄積） | 各リポジトリ |
| `docs/QUALITY_GATE.md` | **Meta** | 品質ゲートの定義（通過基準・例外承認フロー） | 各リポジトリ |
| `docs/PERFORMANCE_BUDGET.md` | **Meta** | パフォーマンス予算（レイテンシ・スループット・メモリ上限） | 各リポジトリ |
| `docs/SLO.md` | **Meta** | Service Level Objectives（可用性・エラーレート目標） | 各リポジトリ |

#### E.4 AI エージェント運用ドキュメント（本基盤に固有）

> **命名**: このカテゴリは**全て Meta 層**。AI エージェントの運用フレームワーク・観測定義・カタログ・集約知見はいずれも「判断基準」「記録フォーマット」「横断ルール」に該当するため。

| ドキュメント | 層 | 目的 | 推奨パス |
| --- | --- | --- | --- |
| `docs/AGENT_RUNBOOK.md` | **Meta** | AI エージェントの起動・停止・ログ確認・復旧手順 | 各リポジトリ |
| `docs/AGENT_OBSERVABILITY.md` | **Meta** | 発火状況・スキルヒット率・Hook 実行時間の観測方法 | 各リポジトリ |
| `docs/TOKEN_COST_LOG.md` | **Meta** | トークン消費量の観測記録（スキル別・セッション別） | 各リポジトリ |
| `docs/SKILL_CATALOG.md` | **Meta** | 利用可能スキル一覧と発火条件の要約（O(N) 探索コスト可視化のため） | 各リポジトリ |
| `docs/HOOK_CATALOG.md` | **Meta** | 有効な Hook 一覧とブロック条件 | 各リポジトリ |
| `docs/GOTCHAS.md`（集約版） | **Meta** | 各スキルの Gotchas を横串で集約した運用知見 | 各リポジトリ |
| `docs/AGENT_VERSION_MATRIX.md` | **Meta** | Cursor / Claude Code / Anthropic API のバージョン互換性記録 | 各リポジトリ |

#### E.5 プロセス・チームドキュメント

> **命名**: プロセスの汎用的フレームワーク（ブランチ戦略/レビュー観点/リリース手順/インシデント対応フロー）は Meta 層。個別のポストモーテム本文は Domain 層（`postmortems/YYYY-MM-DD-*.md`）。

| ドキュメント | 層 | 目的 | 推奨パス |
| --- | --- | --- | --- |
| `docs/BRANCH_STRATEGY.md` | **Meta** | ブランチ戦略（Git Flow / GitHub Flow / trunk-based のどれか） | 各リポジトリ |
| `docs/PR_REVIEW_CHECKLIST.md` | **Meta** | プルリクエストレビュー観点（人間 / AI 両方が参照） | 各リポジトリ |
| `docs/RELEASE_PROCESS.md` | **Meta** | リリース手順（タグ付け・デプロイ・ロールバック） | 各リポジトリ |
| `docs/INCIDENT_RESPONSE.md` | **Meta** | インシデント対応フロー（検知 → 復旧 → ポストモーテム） | 各リポジトリ |
| `docs/postmortems/YYYY-MM-DD-*.md` | Domain | ポストモーテムの蓄積ディレクトリ（= 自己改善サイクルの Observe 層） | 各リポジトリ |

#### E.6 セキュリティ・コンプライアンス

> **命名**: このカテゴリは**全て Meta 層**。セキュリティポリシー・シークレット管理ルール・データ取扱規則・AI 利用ポリシーはいずれも「規則・フレームワーク」に該当。

| ドキュメント | 層 | 目的 | 推奨パス |
| --- | --- | --- | --- |
| `docs/SECURITY.md` | **Meta** | セキュリティポリシー・脆弱性報告手順 | リポジトリ直下 |
| `docs/SECRETS_MANAGEMENT.md` | **Meta** | シークレット管理ルール（`.env` の扱い・ローテーション） | 各リポジトリ |
| `docs/DATA_HANDLING.md` | **Meta** | データ取扱規則(個人情報・ライセンス・外部送信の可否) | 各リポジトリ |
| `docs/AI_USAGE_POLICY.md` | **Meta** | AI エージェントに委ねてよい操作・委ねてはいけない操作 | 各リポジトリ |

#### E.7 優先度の目安

全てを一度に整備する必要はない。以下の優先度で段階的に作成する:

| 優先度 | ドキュメント | 理由 |
| --- | --- | --- |
| P0（必須） | `README.md` / `CLAUDE.md` / `AGENTS.md` / `DECISIONS.md` / `QUALITY_GATE.md` | セッション管理と品質保証の最小セット（全て Meta 層） |
| P1（早期） | `spec.md` / `architecture.md` / `TEST_STRATEGY.md` / `runbooks/` / `troubleshooting.md` | 開発・運用の基礎（Domain と Meta の混在） |
| P2（中期） | `AGENT_RUNBOOK.md` / `SKILL_CATALOG.md` / `GOTCHAS.md` / `BRANCH_STRATEGY.md` / `PR_REVIEW_CHECKLIST.md` | AI エージェント運用の成熟化（Meta 層中心） |
| P3（長期） | `PERFORMANCE_BUDGET.md` / `SLO.md` / `postmortems/` / `AGENT_VERSION_MATRIX.md` / `TOKEN_COST_LOG.md` | 運用規模拡大時に必要 |

#### E.8 このリスト自体の扱い

* このリストは **テンプレート** であり、全プロジェクトで同じ構成が必要なわけではない
* パターン（開発型 / パイプライン型 / ドキュメント型）によって必要な組み合わせは異なる
* 小規模プロジェクトでは `README.md` + `CLAUDE.md` + `DECISIONS.md` の3点で十分なケースも多い
* リストの**運用状況自体**も Gotchas の対象にし、「作ったが使われていないドキュメント」を定期的に棚卸しする
* **命名規約が迷う場合**: §12 Layer 1 の「判定に迷うケースの指針」を参照。原則は「役割名だけで別プロジェクトに移植できるか＝ Meta（大文字）」「プロジェクト固有の中身が 50% 超なら Domain（小文字）」

---

### Appendix F: v2 変更履歴（公式仕様レビュー反映）

Opus 4.7 High レビュー（`ai-agent-unified-design-for-developer-review-opus4.7-high.md`）の22件の指摘を以下の通り反映した。

#### 🔴 Critical（公式仕様との齟齬を修正）

| ID | 対象 | 修正内容 |
| --- | --- | --- |
| C1 | §13.3.2 | Rule モードを3種類から**4種類**（Always Apply / **Apply Intelligently** / Apply to Specific Files / Apply Manually）に修正 |
| C2 | §12 Layer 4, §13.5.2 | Hook イベント名を Cursor 公式のキャメルケースに統一（`PreToolUse` → `preToolUse` 等）。Tab 系イベントも併記 |
| C3 | §13.5.2 | Hook の exit code を3段階（0 / 2 / その他）に修正。exit 2 によるブロック方法を追記 |
| C4 | §12 Layer 3, §13.2.2 | SKILL.md 本文の上限を「5,000語」から「**5,000 トークン未満**（日本語 ≒ 2,500〜4,000 文字）」に修正 |
| C5 | §13.2.2 | Skill `name` の制約を追加: 64文字以内 / 小文字英数ハイフン / XML タグ禁止 / `anthropic` `claude` 禁止 |
| C6 | §15, 用語集 | `claude-mem` を「**サードパーティ OSS（npm）**」として再定義。公式メモリ機能（CLAUDE.md / `/memory`）と区別 |
| C7 | §12 Layer 4, 用語集 | 「Auto Mode（`Shift+Tab`）」を「**Permission Mode の4モード循環切替**（default / acceptEdits / plan / bypassPermissions）」に修正。資料中の Auto Mode は `bypassPermissions` に相当 |
| C8 | §17 | 存在しない `/branch` コマンドを削除。`/rewind`（Claude Code）/ `Cmd+Shift+L`（Cursor 新規チャット）に置換 |

#### 🟡 Warning（公式機能の抜けを補完）

| ID | 対象 | 修正内容 |
| --- | --- | --- |
| W1 | §13.2.2 | Skill frontmatter に `disable-model-invocation` を追加（スラッシュコマンド専用化） |
| W2 | §12 Layer 5, §13.4 | Cursor 組み込み Subagent（`explore` / `bash` / `browser`）を追加。自作前の検討を推奨 |
| W3 | §13.4.2 | Subagent に `is_background` フィールドを追加。Parallel Phase Runner で推奨 |
| W4 | §13.4.2 | Subagent `model` に具体的なモデルID（`claude-4-sonnet` 等）を追記。Reasoning 特化パターンを追加 |
| W5 | §14 | スキル配置先に `.codex/skills/`, `~/.codex/skills/` と互換性サポートを追記 |
| W6 | §13.3 | Cursor Rules の Precedence（Team → Project → User）を追記 |
| W7 | §12 Layer 1 | AGENTS.md を「`.cursor/rules` の完全な簡易代替、ネスト対応の独立 SoT」として再定義。CLAUDE.md との統合運用パターンを整理 |
| W8 | §13.3.2 | Rule の行数「50行」を「**Cursor 公式は500行推奨、本設計では手続き混入検知のため独自に50行**」と明示 |
| W9 | §13.5.2 | `loop_limit` の出典を注記（Cursor 公式スキーマで確認不可、実装検証が必要） |

#### 🟢 Informational（設計根拠の強化）

| ID | 対象 | 修正内容 |
| --- | --- | --- |
| I1 | 原則6, §12 Layer 3 | Anthropic 公式のトークン見積り（L1: 100 tokens / L2: 5k 未満 / L3: 実質無制限）を追記 |
| I2 | §13.5.2 | Hook の JSON 出力フィールド一覧（`permission` / `user_message` / `agent_message` / `continue` / `decision` / `reason` / `followup_message`）を表で整理 |
| I3 | §13.5.3 | プロンプトベース Hook を「全イベント対応、`model` 指定可能、`$ARGUMENTS` プレースホルダ対応」と修正。未検証の記述を削除 |
| I4 | §13.2.2 | Skill frontmatter に `license` / `compatibility` / `metadata` を追記 |
| I5 | §13.4.1 | Subagent のネスト起動（Cursor 2.5+）を追記 |

#### v2 で明示的に残したもの（独自規約）

以下は公式仕様ではなく本設計独自のチーム標準として明示した。読者が公式仕様と混同しないように注記。

* description 1,024 文字以内（公式 1,536 文字より厳しく運用）
* What / When / Negative trigger の3構造
* Gotchas セクション必須化
* Rule 50 行以内（公式 500 行より厳しく運用）
* `README.md` を置かない方針（公式非推奨ではないが入口統一のため）

#### v2.1 追記（ファイル命名規約の明確化）

v2.0 公開後の読者からの質問を受け、Appendix E と §12 Layer 1 に以下の注記を追加（v3 で semantic 2層モデルに発展）:

* 公式で大文字必須と定められているのは **`CLAUDE.md` / `CLAUDE.local.md` / `MEMORY.md` / `AGENTS.md` の4ファイルのみ**。出典は [Anthropic Docs - claude-md](https://docs.anthropic.com/en/docs/claude-code/claude-md) および [Cursor Docs - Rules](https://cursor.com/docs/rules)
* 公式は **`.cursor/rules/*.mdc` / `.claude/rules/*.md` / Auto Memory トピックファイルには kebab-case を推奨**
* Appendix E で列挙する `DECISIONS.md` / `QUALITY_GATE.md` / `RUNBOOK.md` / `GOTCHAS.md` 等の大文字表記は GitHub Community Standards / ADR コミュニティ由来の **OSS 慣習**であり、プロジェクトごとに小文字・kebab-case に読み替えてよい
* 本リポジトリ (pos-tec-service) の `docs/spec/master-sync.md`, `docs/runbooks/RB-*.md`, `docs/investigations/` のように **小文字・kebab-case 運用は完全に公式準拠**

#### v3.0 変更（命名規約 semantic 2層モデルの正式採用）

v2.1 の「OSS 慣習 vs 公式要件」の整理を一歩進め、命名規約を **semantic 2層モデル** として本設計書の正式規約に格上げ。

| 変更箇所 | 内容 |
| --- | --- |
| §12 Layer 1 | 「ファイル名の大文字指定について（v2.1 追記）」ブロックを「**ドキュメント命名規約 — semantic 2層モデル**」として再構成。Meta 層（大文字）= 判断フレームワーク/運用ルール/記録フォーマット、Domain 層（小文字 kebab-case）= プロジェクト固有のドメイン知識/独自ワークフロー、という明確な semantic 区分を定義。判定基準「他リポジトリで同じ役割名が通用するか」を追加 |
| Appendix E 冒頭 | 命名規約の注記を刷新し、各カテゴリを Meta/Domain で明示分類 |
| Appendix E の各カテゴリ | ドキュメント一覧に **層** 列を追加。`SPEC.md` → `spec.md`、`ARCHITECTURE.md` → `architecture.md`、`DATA_MODEL.md` → `data-models.md`、`API.md` → `api.md`、`ONBOARDING.md` → `onboarding.md`、`DEV_ENV.md` → `dev-env.md`、`TROUBLESHOOTING.md` → `troubleshooting.md`、`TEST_CASES.md` → `test-cases.md`、`POSTMORTEMS/` → `postmortems/` に変更（Domain 層として）。一方、`DECISIONS.md` / `QUALITY_GATE.md` / `AGENT_RUNBOOK.md` / `GOTCHAS.md` / `SECURITY.md` 等の判断フレームワーク系は Meta 層として大文字を維持 |
| Appendix E.7 | 優先度表の表記を Meta/Domain 整合版に更新 |
| Appendix E.8 | 命名規約が迷う場合の指針（§12 Layer 1 参照）を追記 |

**設計思想の発展**:

v2.1 では「公式要件 vs OSS 慣習」という二分法で命名規約を捉えていたが、v3 では **命名の大文字/小文字が AI エージェントへのシグナル（メタ指示 vs ドメインコンテンツ）として機能する** という semantic な意味づけを正式採用。これにより:

* AI エージェントがファイル名だけで「このファイルは判断基準を与えるメタ指示か、プロジェクト固有のコンテンツか」を識別できる
* 新規ドキュメント作成時の命名判断が「役割名として他プロジェクトに移植できるか」という明確な基準で決まる
* `docs/` 配下の大文字/小文字混在が、単なる慣習の寄せ集めではなく **意図的な設計** になる

**後方互換性**: v2 で大文字のまま作成されたドキュメント（例: `SPEC.md`, `ARCHITECTURE.md`）を v3 規約に合わせてリネーム（`spec.md`, `architecture.md`）するかどうかは各プロジェクトの判断。本リポジトリ（pos-tec-service）は既に Domain 層 = 小文字運用が浸透しているため追加作業はほぼ不要。逆にまだ大文字で作成されている `AGENT_RUNBOOK.md` / `DECISIONS.md` / `QUALITY_GATE.md` / `GOTCHAS.md` は Meta 層として大文字維持で整合が取れる。