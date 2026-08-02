# セットアップガイド

本キットの生成物が正しく動作するために必要な外部サービス・ツールのセットアップ手順。

生成される基盤ファイル群の概要は [README.md](README.md) を参照。

---

## 1. CLI ツール（必須）

基盤の生成・Hook の実行に必要なコマンドラインツール。

| ツール | 用途 | 必須/推奨 |
| --- | --- | --- |
| `python3` | 生成エンジン・resolver スクリプトの実行 | 必須 |
| `node` | application profile の JavaScript toolchain 実行（Node.js 18 以上） | 必須 |
| `corepack` | Node.js とは別に、承認済み契約に従って `pnpm` を有効化 | 必須 |
| `git` | バージョン管理 | 必須 |
| `jq` | Hook スクリプトの JSON 処理 | 推奨（未インストール時はフェイルオープン） |
| `gh` | GitHub CLI（PR 操作等） | 推奨（agent-code-review 使用時は wrapper が代替） |

```bash
make install   # Homebrew 経由で一括インストール（macOS）
make check     # インストール状況を確認
```

> `python3` は標準ライブラリのみ使用（PyYAML 不要）。
>
> `make install` は `corepack` が未導入の場合、`npm install --global corepack` で導入します。
>
> `pnpm` は `bin/project-setup --apply` が契約内の `corepack prepare` で固定バージョンを有効化する。契約外の `npm install -g pnpm` は行わない。

---

## 2. Cursor Hooks の有効化（必須）

生成される `.cursor/hooks.json` と `.cursor/hooks/*.sh` を動作させるには、Cursor の設定で Hooks を有効にする必要がある。

### 手順

1. Cursor を開く
2. **Settings** → **Features** → **Hooks** を探す
3. **Enable Hooks** をオンにする

### 確認方法

Hook が正しく動作しているかは、新規チャットを開いて1通メッセージを送り、`.cursor/.session/` ディレクトリにセッションファイル（`{session_id}.json`）が作成されることで確認できる。

### 生成される Hook 一覧

| Hook | イベント | 役割 |
| --- | --- | --- |
| `guard-git-write.sh` | `beforeShellExecution` | Git/gh の不可逆操作のブロック・token 漏洩防止 |
| `session-bootstrap.sh` | `sessionStart` | セッション state 初期化・handoff manifest 注入 |
| `session-budget-tracker.sh` | `beforeSubmitPrompt` | プロンプト数カウント |
| `session-shell-tracker.sh` | `afterShellExecution` | シェル出力バイト数カウント |
| `session-budget-evaluator.sh` | `stop` | Context Budget の Yellow/Red 判定・ハンドオフ促進 |

---

## 3. CodeRabbit（オプション）

`coderabbit.enabled: true` の場合に `.coderabbit.yaml` が生成される。CodeRabbit を利用するには以下のセットアップが必要。

### 3.1 アカウント作成

1. [coderabbit.ai](https://coderabbit.ai) にアクセス
2. GitHub アカウントで Sign Up
3. Free プランまたは Pro プランを選択

### 3.2 リポジトリの接続

1. CodeRabbit ダッシュボードで **Add Repository** を選択
2. 対象リポジトリを選択して接続
3. GitHub Apps のインストールを承認（`Pull requests: Read and write` 権限が必要）

### 3.3 動作確認

1. PR を作成する
2. CodeRabbit bot がレビューコメントを投稿することを確認
3. `.coderabbit.yaml` の設定（言語・ツール・path_instructions）が反映されていることを確認

> CodeRabbit の GitHub Apps と次節の agent-code-review 用 GitHub Apps は別物。CodeRabbit は CodeRabbit 社が提供する Apps、agent-code-review 用は自分で作成する Apps。

---

## 4. GitHub provider — wrapper 用

`init.yaml > github_access.api_credential_provider` で `github_app`（既定）または `keychain` を一つだけ選びます。同じ provider が GitHub API と AI の HTTPS Git に使われ、token / PAT / JWT 本体は init / manifest に保存されません。

```yaml
github_access:
  api_credential_provider: github_app
  keychain:
    service: agentic-workflow-github-api
    account: ""
```

### 4.1 provider=`github_app`

1. GitHub → Settings → Developer settings → GitHub Apps で App を作成します。OAuth、Device Flow、Webhook は不要です。
2. 使用機能に応じ、Repository permissions を最小権限で設定します。
   - PR review / create: Pull requests read-write
   - Issue: Issues read-write
   - fetch / clone: Contents read
   - push: Contents read-write
   - Metadata: read
3. App を対象 repository にインストールします。wrapper は操作対象 `owner/repo` から installation ID を動的解決するため、固定 Installation ID は設定しません。
4. private key をリポジトリ外の `~/.config/github-apps/private-key.pem` に配置し、`~/.config/github-apps/config.env` には App ID と任意の鍵パスだけを設定します。

```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH="${HOME}/.config/github-apps/private-key.pem"
```

App が対象 repo に未 installation、または Contents 権限が不足する場合、wrapper は credential を出力せず exit 2 で終了します。

### 4.2 provider=`keychain`

Keychain Access.app を開き、専用の generic password item をユーザー操作で登録します。PAT をコマンドライン引数や shell history に残す登録例は使用しません。

- Service: `init.yaml > github_access.keychain.service`（既定 `agentic-workflow-github-api`）
- Account: `init.yaml > github_access.keychain.account` と完全一致する非空値
- Password: 対象 current repo と active cross-repo すべてに必要な権限を持つ PAT

fine-grained PAT は単一 resource owner に限定されます。複数 owner を扱う場合は、一つの PAT で全対象を満たせる構成だけをサポートします。Organization SSO の承認状態と PAT の有効期限も確認してください。`keychain` provider は macOS 専用で、非 macOS では exit 2 です。

### 4.3 生成 wrapper

| wrapper | 用途 |
| --- | --- |
| `bin/_github-auth.sh` | provider dispatcher、API / HTTPS Git 共通 helper |
| `bin/_github-app-auth.sh` / `bin/_github-keychain-auth.sh` | provider backend |
| `bin/github-git-fetch-safe` | current repo fetch |
| `bin/github-pr-create-safe` | HTTPS push + PR 作成 |
| `bin/github-pr-{reviews,comment,reply}-safe` | PR review 操作 |
| `bin/github-issue-{create,read}-safe` | Issue 操作 |
| `bin/cross-repo-sync-safe` | cross-repo clone/fetch/pull |

### 4.4 セキュリティモデル

wrapper は `GIT_ASKPASS` を操作単位で作成し、既存 credential helper を無効化します。SSH origin は永続変更せず、各 invocation だけ `https://github.com/{owner}/{repo}.git` を使います。Authorization secret は process argv、remote URL、stdout/stderr、永続/一時ファイルへ出しません。

AI シェルからの `security find-*`、`git credential fill`、`gh auth token`、`gh` CLI 直実行は Hook で deny します。wrapper 内 subprocess は `beforeShellExecution` Hook の直接入力ではありません。ユーザーが端末から直接行う SSH 運用は kit の対象外です。

---

## 5. GitHub リポジトリ設定（推奨）

基盤の運用効果を最大化するための GitHub リポジトリ設定。

### 5.1 Branch Protection Rules

対象ブランチ: `main` / `develop` / `release/*`

| 設定 | 推奨値 | 理由 |
| --- | --- | --- |
| Require pull request reviews | ON | `guard-git-write.sh` が保護ブランチへの直接 push をブロックするため、PR ワークフローを前提とする |
| Require status checks to pass | ON | Quality Gate（build / lint / test）を CI で実行する場合 |
| Require branches to be up to date | ON | マージ前に最新の base branch との整合を保証 |
| Restrict who can push | ON | 保護ブランチへの意図しない push を防止 |

### 5.2 GitHub Actions（任意）

Quality Gate の自動実行を CI で行う場合は、GitHub Actions ワークフローを設定する。生成される `docs/QUALITY_GATE.md` の `session.verification.gate_command` が CI でも同じコマンドで実行できるようにする。

---

## セットアップチェックリスト

### 必須

- [ ] `python3` / `node` / `corepack` / `git` がインストール済み（`make check`）
- [ ] Node.js 18 以上と `corepack` が利用可能
- [ ] Cursor Settings → Features → Hooks が有効
- [ ] 基盤ファイルの初回生成が完了（`agentic-workflow-foundation` スキルを実行）

### 推奨

- [ ] `jq` がインストール済み（Hook の JSON 処理）
- [ ] GitHub の Branch Protection Rules を設定

### GitHub wrapper を使う場合

- [ ] `init.yaml > github_access.api_credential_provider` を一つ選択
- [ ] `github_app`: App を対象 repo に installation し、必要な Contents / Pull requests / Issues 権限と private key を設定
- [ ] `keychain`: Keychain Access.app で service/account 完全一致の専用 PAT item を登録し、期限・SSO・全対象 repo の権限を確認
- [ ] `bin/_github-auth.sh` と利用 feature の `bin/*-safe` wrapper が生成済み

### オプション（CodeRabbit を使う場合）

- [ ] CodeRabbit アカウントを作成
- [ ] 対象リポジトリを CodeRabbit に接続
- [ ] PR を作成して CodeRabbit のレビューが動作することを確認
