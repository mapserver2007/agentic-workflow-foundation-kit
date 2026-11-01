# Evidence signals

既存実装から「観測できる事実」を抽出するための、技術・言語非依存の読み取り指針。特定技術名のallowlistや技術カテゴリへの自動mappingは持たない。

## 読み取り優先順（SHOULD）

1. dependency manifest / lockfile / workspace定義
2. container・dev environment定義
3. CI workflow・quality gate設定
4. API / schema / interface定義
5. runtime・deploy・infrastructure設定
6. compiler・formatter・linter・test runner等の言語toolchain設定
7. 上記を補足するREADME・architecture文書

## 読み取りの範囲（全量読解）

読み取り量に「代表ファイルだけ」「数百ファイル程度」という上限は設けない。次の二層で**全可読ファイル**に到達する。

1. **全量走査（決定論）**: `scripts/survey_repository.py survey` が全 tracked 可読ファイルを走査し、構造 card（package・型・関数・internal import・proto の service/rpc・SQL table 等）と facts（依存・container・CI・Makefile・proto・SQL・routes・環境変数名・生成物グループ・層間 import 集計）を作る。1ファイル 512 KiB を超えるものは先頭のみ走査し `oversize` とする（full 必須の対象外）。
2. **shard 読解（AI）**: 可読ファイルを shard に分け、`references/shard-review-protocol.md` に従って読む。tier-1（manifest / build / ci / container / iac / contract / schema / readme）は全文を読み台帳 level を `full` にする。それ以外は全文を読むか、card を精査して `card` とする。到達範囲は `調査範囲:` 行に集計され、validator が照合する。

生成物（`Code generated` 等の header、`*.pb.go` 等の filename、`gen/` 配下）は shard 読解の対象外とし、**入力（IDL・schema）と生成器**を読んで設計に反映する。生成物の件数・生成器は `facts/generated.md` に出る。

分析できなかった範囲（未初期化 submodule・LFS pointer・oversize・symlink）は、設計書の §22 または Appendix E に分析制限として記録する（SHOULD）。

## 値の分類（SHOULD）

- **明示方針 / 宣言値**: dependency constraint、runtime constraint、CI matrix、設定channel、exact pinなど、将来の解決を制約する記述。§9の方針列へ `宣言: <値>` と書ける。
- **解決値**: lockfileや生成metadataが示す、あるsnapshotで実際に解決された値。方針へ一般化せず、備考へ `観測: <値>; evidence: <path>` と書く。
- **単なる観測値**: 実行例、badge、comment、生成物内のversion等。宣言とは扱わず、必要なら備考に限定する。
- **不明**: 明示方針を確認できないもの。`[要確認]` とし、exact versionから「同一majorを採用」等を推測しない。
- **version概念なし**: `—` とする。

コード・manifest・CIから事実として言える範囲だけを記述する。採用理由、非採用理由、長期方針、設計原則など実装から確定できない判断は `[要確認]: <理由>` とする。

## evidence の安全境界（MUST）

evidence は `validate_design_doc.py` が次を検査する。

- source rootからの相対POSIX path
- root内のtracked通常ファイル
- path全要素が非symlink
- 全量 `git ls-files -z` setとの文字列完全一致
- 次の除外リストに非該当

`EXCLUDED_DIR_NAMES`:

```text
.git
.hg
.svn
node_modules
vendor
dist
build
out
target
coverage
.cache
.next
.nuxt
.venv
venv
__pycache__
```

`EXCLUDED_FILE_NAMES`:

```text
.netrc
.git-credentials
credentials
credentials.json
id_rsa
id_dsa
id_ecdsa
id_ed25519
```

`EXCLUDED_FILE_PREFIXES`:

```text
.env
id_rsa
id_dsa
id_ecdsa
id_ed25519
```

`EXCLUDED_SUFFIXES`:

```text
.pem
.key
.p12
.pfx
.der
.crt
.cer
```

`BINARY_EXTENSIONS`:

```text
.7z
.a
.avi
.bin
.bmp
.class
.dll
.dylib
.eot
.exe
.gif
.gz
.ico
.jar
.jpeg
.jpg
.mov
.mp3
.mp4
.o
.otf
.pdf
.png
.pyc
.so
.tar
.tiff
.ttf
.wav
.webp
.woff
.woff2
.xz
.zip
```

除外対象は、trackedであっても読まず、evidenceにも使わない（MUST）。`.git/**`、secret / credential候補、binary、dependency、build生成物、cacheを二重防御で排除する。

## Submodule / LFS / symlink

- inspect が返す `uninitialized_submodules` が1以上なら取得せず、対象範囲を分析制限として記録する。
- evidence候補の先頭行が `version https://git-lfs.github.com/spec/v1` ならLFS pointerであり、実体を取得せず分析制限として記録する。validatorは内容を読まないため検出しない。
- worktree内のsymlinkは追跡しない。必要な証跡がsymlink先だけにある場合は `[要確認]` とする。
- 対象worktreeでbuild / test / installを行わず、生成物を作って証跡にしない。
