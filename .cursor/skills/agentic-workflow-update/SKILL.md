---
name: agentic-workflow-update
description: >
  対象アプリへ agentic-workflow-foundation-kit の最新版を安全に適用する。
  kit 本体を対象アプリへ同期し、アプリ固有の manifest overlay で一時生成・監査した後、
  dry-run 承認と preimage 再検証を経て kit 本体と render/marker 成果物だけを適用する。
  Use when - 「kit をインストール」「kit を更新」「kit-update」等の指示。
  Do NOT use for - 通常の基盤生成、Domain docs の更新、アプリコードの変更、PR/commit。
disable-model-invocation: true
---

# agentic-workflow-update

適用済みアプリへ kit の最新版を反映する更新専用スキル。

このスキルは対象アプリへ vendor されない。kit リポジトリの
`.cursor/skills/agentic-workflow-update/` が正本であり、foundation の `generate` 成功時に
`~/.cursor/skills/agentic-workflow-update/` へ原子的に配置される。

## 不変条件

- kit の取得元は、対象アプリの親に並置された `agentic-workflow-foundation-kit` の `origin`。
- Git network operation は `bin/kit-source-fetch-safe` 経由の HTTPS のみ。raw `git clone` / `fetch` / `pull` は実行しない。
- workspace の kit 作業ツリーは読まず、fetch 時点の `origin/HEAD` から取得した clone だけを使う。
- `/tmp/agentic-workflow-foundation-kit` は取得した kit の実行時コピー、`/tmp/work` は一時アプリ作業ツリーとして扱う。
- 承認前に対象アプリへ書き込まない。
- `init.yaml`、root `manifest.yaml`、Domain docs、ADR/GOTCHAS、reports、seed、アプリコードは適用対象外。
- orphan、rename、削除、preimage 不一致は自動解決しない。
- updater 自身を対象アプリの `.cursor/skills/` や Git 履歴へ配置しない。
- 自動 commit / push はしない。

## 実行手順

### 1. dry-run

対象アプリのルートで、まず候補を生成する。

```bash
python3 ~/.cursor/skills/agentic-workflow-update/scripts/kit_update.py plan
```

`plan` は次を行う。

1. 並置 kit の `origin` を安全 wrapper 経由で fetch する。
2. その時点の `origin/HEAD` を `/tmp/agentic-workflow-foundation-kit` へ clone する。
3. 対象アプリを `/tmp/work` へコピーし、kit 本体だけを clone 版へ置き換える。
4. clone 版の seed/engine と対象アプリの root manifest を明示して一時生成する。
5. `check`、`audit`、profile に応じた quality gate を実行する。
6. kit 本体と render/marker 成果物の追加・変更を分類する。
7. seed、denylist、orphan、rename、入力不足を停止要因として報告する。

表示された `plan_digest` と差分を確認し、PO の同期承認を得る。承認はこのスキルの
呼び出し元が行い、スクリプトは承認判断を代行しない。

### 2. apply

dry-run で得た計画を保存し、承認後に適用する。

```bash
python3 ~/.cursor/skills/agentic-workflow-update/scripts/kit_update.py apply \
  --plan-file /tmp/kit-update-plan.json \
  --approve-plan <plan_digest>
```

`apply` は計画 digest、kit revision、候補ファイル、対象アプリの preimage、保護対象の
digest を再検証する。不一致時は `KU-PREIMAGE-001` で停止し、対象アプリへ書かない。
適用後に `check`、`audit`、application quality gate を実行する。
検証に成功した場合だけ、clone に含まれる次版 updater をホスト個人スキルへ原子的に
配置する。対象アプリへ updater を vendor することはない。

## 生成経路

clone 上で foundation の6フェーズを再実行しない。生成は必ず対象アプリの overlay を
使い、次の3引数を明示する。

```bash
python3 /tmp/agentic-workflow-foundation-kit/.cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py generate \
  --seed-manifest /tmp/agentic-workflow-foundation-kit/.cursor/skills/agentic-workflow-foundation/manifest.yaml \
  --root-manifest /tmp/work/manifest.yaml \
  --work-root /tmp/work \
  --skip-host-update
```

`--skip-host-update` は dry-run 中に個人 updater が自己更新されることを防ぐ。テンプレート
から展開された候補は `/tmp/work` にのみ書かれ、承認後に対象アプリへ同期される。

## 検査 ID

- `KU-OVERLAY-001`: 対象アプリの root manifest を使って生成された
- `KU-SCOPE-001`: kit 本体と許可された生成成果物だけが適用対象になった
- `KU-PREIMAGE-001`: 承認後の対象変更を検出して無変更で停止した
- `KU-ORPHAN-001`: orphan / rename 候補を検出し、自動削除しなかった
- `KU-SEED-001`: 既存 seed のバイト列が不変だった
- `KU-DENY-001`: denylist のバイト列が不変だった
- `KU-HOST-001`: 個人スキルがホストに配置され、対象アプリには存在しなかった

## 失敗時

exit `1` は修正可能な候補差分・停止要因、exit `2` は入力不備・契約違反・実行不能を
表す。失敗時は対象アプリを変更せず、報告された停止要因を解消して `plan` から再実行する。

