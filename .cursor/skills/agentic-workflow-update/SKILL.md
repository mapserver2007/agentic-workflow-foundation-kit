---
name: agentic-workflow-update
description: >
  foundation/engineをvendorしないconsumerアプリへ、publicな
  agentic-workflow-foundation-kit の生成成果物を安全に適用する。
  固定URLからkitを取得し、アプリ固有のmanifest overlayで一時生成・監査した後、
  計画全体の承認とpreimage再検証を経て生成成果物とlockだけを適用する。
  Use when - 「kit をインストール」「kit を更新」「kit-update」等の指示。
  Do NOT use for - 通常の基盤生成、Domain docs の更新、アプリコードの変更、PR/commit。
disable-model-invocation: true
---

# agentic-workflow-update — consumer

foundation/engineを対象アプリへ保持しないconsumerアプリへ、kitの生成成果物を反映する更新専用スキル。

このスキルは対象アプリへvendorされない。kitのcloneに含まれる最新版を、
適用成功後にホスト個人スキルへ原子的に配置する。

## 不変条件

- kitの取得元は `https://github.com/mapserver2007/agentic-workflow-foundation-kit.git` に固定する。
- Git network operationは `bin/kit-source-fetch-safe` 経由の無認証HTTPSのみ。対象アプリの `init.yaml`、Keychain、GitHub App、並置kit、認証helperを参照しない。
- `/tmp/agentic-workflow-foundation-kit` は取得したkitの実行時clone、`/tmp/work` は一時アプリ作業ツリーとして扱う。
- root `manifest.yaml` はfetch前に検証する。欠落・不正形式は `KU-OVERLAY-001` / exit 2で停止する。
- 承認前に対象アプリへ書き込まない。
- root `manifest.yaml`、Domain docs、ADR/GOTCHAS、reports、seed、アプリコード、foundation/engine、upstream design docsは適用対象外。
- `agentic-workflow-kit.lock.yaml` はupdaterの生成状態であり、計画全体の承認後に生成成果物と同時に適用する。
- lockなし初回adoptではorphan、rename、削除を自動解決しない。
- preimage不一致、orphan、rename、未承認の計画はapplyしない。
- updater自身を対象アプリの `.cursor/skills/` や Git履歴へ配置しない。
- 自動 commit / push はしない。

## 実行手順

### 1. dry-run

対象アプリのルートで、root `manifest.yaml` を配置済みであることを確認して候補を生成する。

```bash
python3 ~/.cursor/skills/agentic-workflow-update/scripts/kit_update.py plan \
  --app-root /path/to/target
```

外部overlayを使う場合は `--root-manifest` を明示する。

```bash
python3 ~/.cursor/skills/agentic-workflow-update/scripts/kit_update.py plan \
  --app-root /path/to/target \
  --root-manifest /path/to/overlay/manifest.yaml \
  --plan-file /tmp/kit-update-plan.json
```

`plan` は次を行う。

1. fetch前にoverlayの存在・形式を検証する。
2. 固定public URLから `/tmp/agentic-workflow-foundation-kit` へcloneする。
3. 対象アプリを `/tmp/work` へコピーし、外部overlayがあれば `/tmp/work/manifest.yaml` へ安全に取り込む。
4. clone版のseed/engineと対象overlayから resolved manifestを作り、一時作業ツリーで生成・check・auditを実行する。
5. 対象アプリの `bin/quality-gate verify` を一時作業ツリーで実行する。
6. resolved output catalogと既存lockを比較し、生成成果物の差分とlock候補だけをplanへ出す。
7. foundation/engine、upstream design docs、root manifest、Domain docs、アプリコードは変更候補に含めない。

表示された計画全体の `plan_digest` と差分を確認し、POの計画全体承認を得る。
ファイル単位の部分承認・部分適用は行わない。

### 2. apply

dry-run で得た計画を保存し、承認後に適用する。

```bash
python3 ~/.cursor/skills/agentic-workflow-update/scripts/kit_update.py apply \
  --plan-file /tmp/kit-update-plan.json \
  --approve-plan <plan_digest>
```

`apply` は計画digest、kit revision、overlay preimage、候補ファイル、対象アプリの
preimage、保護対象digestを再検証する。不一致時は `KU-PREIMAGE-001` で停止し、
対象アプリへ書かない。
適用対象は生成されたrender/marker成果物と `agentic-workflow-kit.lock.yaml` だけである。
適用後に対象アプリのapplication quality gateを実行し、成功時だけcloneの最新版updaterを
ホスト個人スキルへ原子的に配置する。

## 生成経路

clone上でfoundationの6フェーズを再実行しない。生成は必ずkit cloneのseed/engineと
対象アプリoverlayを使い、次の引数を明示する。

```bash
python3 /tmp/agentic-workflow-foundation-kit/.cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py generate \
  --seed-manifest /tmp/agentic-workflow-foundation-kit/.cursor/skills/agentic-workflow-foundation/manifest.yaml \
  --root-manifest /tmp/work/manifest.yaml \
  --work-root /tmp/work
```

`--work-root /tmp/work` を指定することでdry-run中の個人updater自己更新を防ぐ。
foundation/engineとupstream design docsは生成依存としてclone側から読み、
テンプレートから展開された候補は `/tmp/work` にのみ書かれる。

## 検査 ID

- `KU-OVERLAY-001`: fetch前にoverlayを検証し、対象overlayで生成された
- `KU-SCOPE-001`: 生成成果物とlockだけが適用対象になった
- `KU-PREIMAGE-001`: 承認後の対象変更を検出して無変更で停止した
- `KU-ORPHAN-001`: orphan / rename 候補を検出し、自動削除しなかった
- `KU-DENY-001`: denylist のバイト列が不変だった
- `KU-HOST-001`: 個人スキルがホストに配置され、対象アプリには存在しなかった

## 失敗時

exit `1` は修正可能な候補差分・停止要因、exit `2` は入力不備・契約違反・実行不能を
表す。失敗時は対象アプリを変更せず、報告された停止要因を解消して `plan` から再実行する。

