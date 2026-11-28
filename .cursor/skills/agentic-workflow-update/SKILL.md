---
name: agentic-workflow-update
description: >
  consumerアプリへ、publicな agentic-workflow-foundation-kit の
  kit本体（updaterを除く）と生成成果物を安全に適用する。
  固定URLからkitを取得し、アプリ固有のmanifest overlayで一時生成・監査した後、
  計画全体の承認とpreimage再検証を経て、kit本体のミラー同期、生成成果物、lockを適用する。
  Use when - 「kit をインストール」「kit を更新」「kit-update」等の指示。
  Do NOT use for - 通常の基盤生成、Domain docs の更新、アプリコードの変更、PR/commit。
disable-model-invocation: true
---

# agentic-workflow-update — consumer

consumerアプリへ、kit本体（foundation / engine / technology-stack-unified-design / upstream design docs）を
cloneとの直接比較でミラー同期し、生成成果物を反映する更新専用スキル。
適用後は、対象アプリ内のfoundationで再生成差分がゼロ（`check`）であることを確認する。

このスキル自身（`agentic-workflow-update`）は対象アプリへ同期しない。kitのcloneに含まれる最新版を、
適用成功後にホスト個人スキルへ原子的に配置する。

## 不変条件

- kitの取得元は `https://github.com/mapserver2007/agentic-workflow-foundation-kit.git` に固定する。
- Git network operationは `bin/kit-source-fetch-safe` 経由の無認証HTTPSのみ。対象アプリの `init.yaml`、Keychain、GitHub App、並置kit、認証helperを参照しない。
- plan ごとに権限限定の一意な一時rootを作り、その配下の `kit/` を実行時clone、
  `work/` を一時アプリ作業ツリーとして扱う。plan/apply失敗またはapply完了時に、
  updater所有markerを確認して一時rootを削除する。
- root `manifest.yaml` はfetch前に検証する。欠落・不正形式は `KU-OVERLAY-001` / exit 2で停止する。
- 承認前に対象アプリへ書き込まない。
- kit本体（`KIT_BODY_ROOTS`: foundation / engine / technology-stack-unified-design / upstream design docs 2本）は、
  kit cloneとの直接比較でミラー同期する。cloneに無いファイルは削除対象になる。
  `__pycache__` と `*.pyc` は比較に含めない。symlinkと通常ファイルでないものは `KU-KITBODY-001` で拒否する。
- root `manifest.yaml`、`init.yaml`、技術ブループリント、Domain docs、ADR/GOTCHAS、reports、seed、アプリコードは適用対象外。
- `.cursor/agentic-workflow-update.lock.yaml` はupdaterの生成状態であり、計画全体の承認後に生成成果物と同時に適用する。lockはv1のまま、kit本体は記録しない。
- lockなし初回adoptでは、生成成果物のorphan、rename、削除を推測しない。kit本体と `mode: split` の出力は、lockに依らずミラーで削除候補を決める。
- orphan、rename、kit本体またはsplitの削除候補がある plan は、`retirement` が指定されたときだけ apply できる。未指定では apply しない。
  kit本体とsplitの削除は `retirement=delete` のときだけ実行する。`keep` ではミラーが収束しないため `KU-ORPHAN-001` で停止する。
- preimage不一致、未承認の計画はapplyしない。
- updater自身（`.cursor/skills/agentic-workflow-update`）は対象アプリへ同期も削除もしない。対象アプリに既にあるときは plan の `warnings` に出す。
- 適用後の検証は、対象アプリ内のfoundationの `run_resolved_engine.py check` だけを実行する。`generate` は実行しない
  （manifest移行、legacy cleanup、host配置は承認計画の対象外）。
- 自動 commit / push はしない。

更新責務の詳細は [README.md](README.md) を参照する。

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
3. 対象アプリを同一rootの `work/` へコピーし、`work/` のkit本体ルートをcloneと同じ内容に置き換える（updaterは除く）。同一内容の別パスを渡したときは、そのバイト列を一時 `work/manifest.yaml` へコピーする。アプリ直下の `manifest.yaml` は変更しない。
4. clone版のseed/engineと対象overlayから resolved manifestを作り、一時作業ツリーで生成・check・auditを実行する。
   consumer の audit は `--skip-seed-required-sections` を指定する。denylist または
   `mode: seed` の既存ファイル（ADR / GOTCHAS / Domain docs / skill config）は
   適用・再生成せず、ファイルの存在だけを確認する。render / marker の drift と
   required_sections、seed の不在、未知の mode、テンプレート不在、描画失敗は検査対象に残る。
5. 対象アプリの `bin/quality-gate verify` を一時作業ツリーで実行する。
6. 次の3つを、それぞれの所有者を基準に比較して plan へ出す。
   - kit本体: **cloneと対象アプリを直接比較**する（add / update / delete、モードビット含む）。`work/` は比較に使わない。
   - `mode: split` の出力（`docs/tech-stack.md` と `docs/tech-stack/`）: **`work/` で生成した結果と対象アプリを比較**する。
     splitの正本は対象アプリ自身の技術ブループリントであり、cloneとは比較しない。
     出力ディレクトリに下位ディレクトリやsymlinkがあるとengineが止まり、plan の失敗として表面化する。
   - render / marker: resolved output catalogと既存lockを比較する。lock候補もここで出す。
7. root manifest、Domain docs、アプリコードは変更候補に含めない。plan の schema は v2（change の `kind` に `kit_body` と `split` を追加）で、lockは v1 のまま。

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

orphan、rename、またはkit本体・splitの削除候補がある場合は、計画全体の承認の前に delete か keep を選ぶ。
kit本体とsplitの削除候補がある plan では、`keep` を選べない（`delete` のときだけ plan が通る）。
エージェント実行時は AskQuestion で選ばせ、選んだ値で plan を作り直す。
CLI を直接実行するときは、次のどちらかを付けて plan する。

```bash
python3 ~/.cursor/skills/agentic-workflow-update/scripts/kit_update.py plan \
  --app-root /path/to/target \
  --retire delete \
  --plan-file /tmp/kit-update-plan.json
```

`delete` は lock に記録されていた旧生成ファイルを削除する。rename では旧パスだけを削除し、新しいパスは通常の追加または更新として残す。さらに、kit本体のルート配下でcloneに無いファイルと、splitの出力ディレクトリで生成結果に無いファイルを削除する（lockに入ったことがなくても削除する。ルートはkit専有・engine専有のため）。
`keep` はファイルを残し、新しい lock の管理から外す。ただしkit本体とsplitの削除候補には使えない。
`seed` のドメイン文書、lock に入ったことのないアプリ独自ファイル（kit本体とsplitのルート外）、保護対象は削除しない。`apply` は plan 内の `retirement` だけを使い、別フラグでは上書きできない。

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
適用対象は、kit本体、生成されたrender/marker成果物、splitの出力、`.cursor/agentic-workflow-update.lock.yaml` だけである。
kit本体の候補はcloneから直接読む（cloneのrevisionは plan と一致することを検証済み）。

ファイル適用、適用後 `check`、application quality gate、host 個人スキルへの updater 配置は一つのトランザクションである。
適用後 `check` は、対象アプリ内のfoundationの `run_resolved_engine.py check`（`PYTHONDONTWRITEBYTECODE=1`）を実行し、
再生成差分がゼロであることを確認する。`check` はhost配置より前に走るため、失敗時はアプリだけを適用前へ戻し、hostは未変更のままである。
host配置などが例外で失敗した場合は、アプリと host を適用前へ戻す。

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
`work/` のkit本体はcloneと同一バイトなので、生成物は適用後の対象アプリ内で生成した結果と一致する。
ただし副作用（manifest移行、legacy cleanup、host配置）は `work_root == ROOT` の `generate` だけが実行し、この経路では実行されない。
これらは承認計画の対象外で、updaterは実行しない。

## 検査 ID

- `KU-OVERLAY-001`: fetch前にoverlayを検証し、アプリの manifest と違う外部ファイルを拒否した
- `KU-SCOPE-001`: 適用対象が、kit本体・生成成果物・split・lockの範囲に収まった
- `KU-KITBODY-001`: kit本体の同期範囲違反を拒否した（updater混入、ルート外パス、symlink、cloneのルート欠落、生成物とkit本体の重なり）
- `KU-PREIMAGE-001`: 承認後の対象変更を検出して無変更で停止した
- `KU-ORPHAN-001`: orphan / rename / kit本体・splitの削除候補を検出し、delete（kit本体とsplitは delete のみ）が計画に含まれるときだけ解消した
- `KU-DENY-001`: denylist のバイト列が不変だった
- `KU-HOST-001`: 個人スキルがホストに配置された。対象アプリにupdaterが既にあるときは、触らず plan の `warnings` に警告する

## 失敗時

exit `1` は修正可能な候補差分・停止要因、exit `2` は入力不備・契約違反・実行不能を
表す。例外で失敗した場合は対象アプリと host 個人スキルを適用前へ戻し、報告された停止要因を解消して `plan` から再実行する。
プロセスの強制終了で例外処理が走らなかった混在は、次の apply が preimage 不一致で停止する。

