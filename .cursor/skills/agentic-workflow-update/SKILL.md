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
- plan ごとに権限限定の一意な一時rootを作り、その配下の `kit/` を実行時clone、
  `work/` を一時アプリ作業ツリーとして扱う。plan/apply失敗またはapply完了時に、
  updater所有markerを確認して一時rootを削除する。
- root `manifest.yaml` はfetch前に検証する。欠落・不正形式は `KU-OVERLAY-001` / exit 2で停止する。
- 承認前に対象アプリへ書き込まない。
- root `manifest.yaml`、Domain docs、ADR/GOTCHAS、reports、seed、アプリコード、foundation/engine、upstream design docsは適用対象外。
- `.cursor/agentic-workflow-update.lock.yaml` はupdaterの生成状態であり、計画全体の承認後に生成成果物と同時に適用する。
- lockなし初回adoptではorphan、rename、削除を推測しない。
- orphan または rename がある plan は、`retirement` が `delete` または `keep` のときだけ apply できる。未指定では apply しない。
- preimage不一致、未承認の計画はapplyしない。
- updater自身を対象アプリの `.cursor/skills/` や Git履歴へ配置しない。
- 自動 commit / push はしない。

## 実行手順

### 1. dry-run

対象アプリのルートで、root `manifest.yaml` を配置済みであることを確認して候補を生成する。

```bash
python3 ~/.cursor/skills/agentic-workflow-update/scripts/kit_update.py plan \
  --app-root /path/to/target \
  --plan-file /tmp/kit-update-plan.json
```

`--root-manifest` は、対象アプリ直下の `manifest.yaml` 自身か、sha256 が一致するコピーだけを受け付ける。内容が違う外部ファイルは fetch 前に拒否する。アプリの `manifest.yaml` は上書きしない。

`plan` は次を行う。

1. fetch前にoverlayの存在・形式を検証し、アプリ直下の `manifest.yaml` と同一パスまたは同一 sha256 であることを確認する。
2. 固定public URLから plan 固有一時rootの `kit/` へcloneする。
3. 対象アプリを同一rootの `work/` へコピーする。同一内容の別パスを渡したときは、そのバイト列を一時 `work/manifest.yaml` へコピーする。アプリ直下の `manifest.yaml` は変更しない。
4. clone版のseed/engineと対象overlayから resolved manifestを作り、一時作業ツリーで生成・check・auditを実行する。
   consumer の audit は `--skip-seed-required-sections` を指定する。denylist または
   `mode: seed` の既存ファイル（ADR / GOTCHAS / Domain docs / skill config）は
   適用・再生成せず、ファイルの存在だけを確認する。render / marker の drift と
   required_sections、seed の不在、未知の mode、テンプレート不在、描画失敗は検査対象に残る。
5. 対象アプリの `bin/quality-gate verify` を一時作業ツリーで実行する。
6. resolved output catalogと既存lockを比較し、生成成果物の差分とlock候補だけをplanへ出す。
7. foundation/engine、upstream design docs、root manifest、Domain docs、アプリコードは変更候補に含めない。

### 初回利用時の host updater bootstrap

旧 host updater は新しい consumer audit flag を渡せないため、consumer の `plan` より先に
改訂済み kit checkout から host updater を更新する。clone に root manifest がある場合は
throwaway work root へ生成し、host updater だけを原子的に更新する。公開 clone のように
root manifest がない場合は updater-only の fallback が選ばれ、生成や対象アプリへの書込みは行わない。

```bash
python3 /tmp/agentic-workflow-foundation-kit/.cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py generate \
  --seed-manifest /tmp/agentic-workflow-foundation-kit/.cursor/skills/agentic-workflow-foundation/manifest.yaml \
  --root-manifest /tmp/agentic-workflow-foundation-kit/manifest.yaml \
  --work-root /tmp/kit-updater-bootstrap \
  --update-skill-home ~/.cursor/skills
```

`generate` 成功後、kit の updater が `~/.cursor/skills/agentic-workflow-update` へ
原子的に配置される。対象アプリの作業ツリーや root manifest は変更されない。
host updater が更新されたことを確認してから、対象アプリで `plan` を実行する。
`apply` は plan が成功した後の更新経路なので、host updater の bootstrap 手段には使わない。

orphan または rename がある場合は、計画全体の承認の前に delete か keep を選ぶ。
エージェント実行時は AskQuestion で選ばせ、選んだ値で plan を作り直す。
CLI を直接実行するときは、次のどちらかを付けて plan する。

```bash
python3 ~/.cursor/skills/agentic-workflow-update/scripts/kit_update.py plan \
  --app-root /path/to/target \
  --retire delete \
  --plan-file /tmp/kit-update-plan.json
```

`delete` は lock に記録されていた旧生成ファイルを削除する。rename では旧パスだけを削除し、新しいパスは通常の追加または更新として残す。`keep` はファイルを残し、新しい lock の管理から外す。`seed` のドメイン文書、lock に入ったことのないアプリ独自ファイル、保護対象は削除しない。`apply` は plan 内の `retirement` だけを使い、別フラグでは上書きできない。

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
適用対象は生成されたrender/marker成果物と `.cursor/agentic-workflow-update.lock.yaml` だけである。
ファイル適用、application quality gate、host 個人スキルへの updater 配置は一つのトランザクションである。
いずれかが例外で失敗した場合は、アプリと host を適用前へ戻す。

## 生成経路

clone上でfoundationの6フェーズを再実行しない。生成は必ずkit cloneのseed/engineと
対象アプリoverlayを使い、次の引数を明示する。

```bash
python3 <plan-temp-root>/kit/.cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py generate \
  --seed-manifest <plan-temp-root>/kit/.cursor/skills/agentic-workflow-foundation/manifest.yaml \
  --root-manifest <plan-temp-root>/work/manifest.yaml \
  --work-root <plan-temp-root>/work
```

kit updater は plan ごとにこの work root を割り当て、dry-run中の個人updater自己更新を防ぐ。
foundation/engineとupstream design docsは生成依存としてclone側から読み、
テンプレートから展開された候補は plan 固有の `work/` にのみ書かれる。

## 検査 ID

- `KU-OVERLAY-001`: fetch前にoverlayを検証し、アプリの manifest と違う外部ファイルを拒否した
- `KU-SCOPE-001`: 生成成果物とlockだけが適用対象になった
- `KU-PREIMAGE-001`: 承認後の対象変更を検出して無変更で停止した
- `KU-ORPHAN-001`: orphan / rename を検出し、delete または keep が計画に含まれるときだけ解消した
- `KU-DENY-001`: denylist のバイト列が不変だった
- `KU-HOST-001`: 個人スキルがホストに配置され、対象アプリには存在しなかった

## 失敗時

exit `1` は修正可能な候補差分・停止要因、exit `2` は入力不備・契約違反・実行不能を
表す。例外で失敗した場合は対象アプリと host 個人スキルを適用前へ戻し、報告された停止要因を解消して `plan` から再実行する。
プロセスの強制終了で例外処理が走らなかった混在は、次の apply が preimage 不一致で停止する。

