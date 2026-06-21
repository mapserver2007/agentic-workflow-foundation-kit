# セットアップガイド

本キットの生成物が正しく動作するために必要な外部サービス・ツールのセットアップ手順。

生成される基盤ファイル群の概要は [README.md](README.md) を参照。

---

## 1. CLI ツール（必須）

基盤の生成・Hook の実行に必要なコマンドラインツール。

| ツール | 用途 | 必須/推奨 |
| --- | --- | --- |
| `python3` | 生成エンジン・resolver スクリプトの実行 | 必須 |
| `git` | バージョン管理 | 必須 |
| `jq` | Hook スクリプトの JSON 処理 | 推奨（未インストール時はフェイルオープン） |
| `gh` | GitHub CLI（PR 操作等） | 推奨（agent-code-review 使用時は wrapper が代替） |

```bash
make install   # Homebrew 経由で一括インストール（macOS）
make check     # インストール状況を確認
```

> `python3` は標準ライブラリのみ使用（PyYAML 不要）。

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

## 4. GitHub Apps — wrapper 用（オプション）

`code_review.enabled: true` / `github_pr.enabled: true` の場合に生成される `agent-code-review` / `agent-github-pr` スキルは、AI に GitHub token を露出しない安全な wrapper コマンドを使用する。wrapper は GitHub Apps の **installation token** を内部で発行する（OAuth / user token は不要）。

| スキル | wrapper コマンド |
| --- | --- |
| agent-code-review | `bin/github-pr-reviews-safe` / `bin/github-pr-comment-safe` / `bin/github-pr-reply-safe` |
| agent-github-pr | `bin/github-pr-create-safe` |

### 4.1 GitHub Apps の作成

1. GitHub → **Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**
2. 作成画面の各セクションを以下のとおり設定する。

#### Basic information

| 項目 | 設定 | 備考 |
| --- | --- | --- |
| GitHub App name | 任意（例: `agent-github-operation`） | **必須**。同一アカウント内で一意の名前 |
| Description | 任意 | 空欄可。Markdown 可 |
| Homepage URL | 対象リポジトリの URL | **必須**。例: `https://github.com/{owner}/{repo}` |

#### Identifying and authorizing users

wrapper は installation token のみ使用するため、OAuth 関連は設定不要。

| 項目 | 設定 | 備考 |
| --- | --- | --- |
| Callback URL | 空欄 | **Add Callback URL は不要** |
| Expire user authorization tokens | **チェックを外す** | OAuth を使わないため不要 |
| Request user authorization (OAuth) during installation | **チェックを外す** | インストール時のユーザー認可は不要 |
| Enable Device Flow | **チェックを外す** | CLI 向け OAuth フローは不要 |

#### Post installation

| 項目 | 設定 | 備考 |
| --- | --- | --- |
| Setup URL | 空欄 | インストール後の追加セットアップ URL は不要 |
| Redirect on update | **チェックを外す** | リポジトリ追加/削除時のリダイレクトは不要 |

#### Webhook

REST API を直接呼び出すため Webhook は不要。**Active はデフォルトで ON になっている**ので、必ず OFF にする。

| 項目 | 設定 | 備考 |
| --- | --- | --- |
| Active | **チェックを外す** | **デフォルト ON のため要注意** |
| Webhook URL | 空欄 | Active OFF なら入力不要 |
| Secret | 空欄 | Active OFF なら入力不要 |

#### Permissions

**Repository permissions** を展開して設定する。**Organization permissions** / **Account permissions** はすべて **No access** のまま。

| Permission | Access | 用途 |
| --- | --- | --- |
| Pull requests | **Read and write** | レビュー取得・コメント投稿・PR 作成（必須） |
| Metadata | **Read** | リポジトリ情報の参照（他の Repository permission を設定すると自動付与されることが多い） |
| Contents | **Read and write** | PR 作成時の head ブランチ参照（`github_pr.enabled: true` の場合のみ必要） |

> `agent-code-review` のみ使う場合は **Pull requests** + **Metadata** で足りる。`agent-github-pr` も使う場合は **Contents: Read and write** を追加する。

#### Where can this GitHub App be installed?

| 選択肢 | 推奨 | 備考 |
| --- | --- | --- |
| **Only on this account** | 推奨 | 自分のアカウント / 組織内のみに限定 |
| Any account | — | 複数 org で共有する場合のみ |

3. **Create GitHub App** をクリック

### 4.2 Private Key の生成・配置

1. 作成した Apps のページで **Generate a private key** をクリック
2. ダウンロードされた `.pem` ファイルを `~/.config/github-apps/` に配置する

```bash
mkdir -p ~/.config/github-apps
mv ~/Downloads/*.private-key.pem ~/.config/github-apps/private-key.pem
chmod 600 ~/.config/github-apps/private-key.pem
```

| ファイル | パス | 備考 |
| --- | --- | --- |
| `private-key.pem` | `~/.config/github-apps/private-key.pem` | GitHub Apps からダウンロードした秘密鍵（**必須**） |

> **配置の原則**: リポジトリ外（`~/.config/github-apps/`）に置き、AI（Cursor Agent）からは読み取れないようにする。`.cursor/rules/03-github-security.mdc` により、AI は `.pem` / `.key` ファイルの読み取りを禁止されている。wrapper はこのパスから private key を読み取る。

### 4.3 GitHub Apps のインストール

1. Apps のページ → **Install App** → 対象リポジトリを選択
2. 次の ID を確認する:
   - **App ID** — Apps 設定ページの **About**（4.1 で Apps 作成直後から確認可）
   - **Installation ID** — インストール後の URL `https://github.com/settings/installations/{Installation ID}` の数値部分
3. wrapper 用に `~/.config/github-apps/config.env` を作成する（フォーマットは下記サンプル）

> **スキルとの関係**: `agent-github-pr` / `agent-code-review` は `config.env` を直接読まない。wrapper 実装が installation token 発行に使う。**wrapper が `config.env` を参照する実装の場合のみ**作成する。

#### `config.env` サンプル

```bash
# ~/.config/github-apps/config.env
# wrapper 実装が source する環境変数ファイル（shell の KEY=VALUE 形式）

# GitHub Apps の App ID（Apps 設定 → About）
GITHUB_APP_ID=123456

# Installation ID（Install App 後の URL 末尾）
GITHUB_APP_INSTALLATION_ID=78901234

# private key のパス（4.2 で配置した pem）
GITHUB_APP_PRIVATE_KEY_PATH="${HOME}/.config/github-apps/private-key.pem"
```

作成例:

```bash
cat > ~/.config/github-apps/config.env <<'EOF'
GITHUB_APP_ID=123456
GITHUB_APP_INSTALLATION_ID=78901234
GITHUB_APP_PRIVATE_KEY_PATH="${HOME}/.config/github-apps/private-key.pem"
EOF
chmod 600 ~/.config/github-apps/config.env
```

| 変数 | 必須 | 説明 |
| --- | --- | --- |
| `GITHUB_APP_ID` | Yes | JWT の `iss`。どの GitHub Apps として認証するか |
| `GITHUB_APP_INSTALLATION_ID` | Yes | どの installation 向けに installation token を取得するか |
| `GITHUB_APP_PRIVATE_KEY_PATH` | Yes* | pem ファイルのパス。*wrapper が固定パス（`~/.config/github-apps/private-key.pem`）を読む実装なら省略可 |

> 変数名は wrapper 実装の convention。上記以外のキー名を使う wrapper もある。その場合は各 wrapper の README に従う。

### 4.4 wrapper コマンドの生成

wrapper コマンドは `agentic-workflow-foundation` スキルの Phase 1.5 で「推奨スキル・ツール設定をインストールしますか？」に **Yes** を選択すると、Phase 2 でプロジェクトルートの `bin/` に自動生成される。手動インストールは不要。

```bash
# 生成確認（agent-code-review 用 3 コマンド + agent-github-pr 用 1 コマンド）
test -x bin/github-pr-reviews-safe && test -x bin/github-pr-comment-safe && test -x bin/github-pr-reply-safe && test -x bin/github-pr-create-safe
```

| wrapper | 用途 | 引数 | 使用スキル |
| --- | --- | --- | --- |
| `bin/github-pr-reviews-safe` | レビュースレッド取得（READ） | `<owner> <repo> <pr-number>` | agent-code-review |
| `bin/github-pr-comment-safe` | PR コメント投稿（WRITE） | `<pr-number> <body-file>` | agent-code-review |
| `bin/github-pr-reply-safe` | レビューコメント reply（WRITE） | `<pr-number> <comment-id> <body-file>` | agent-code-review |
| `bin/github-pr-create-safe` | PR 作成（WRITE） | `<base-branch> <title-file> <body-file>` | agent-github-pr |

> wrapper が見つからない場合は `agentic-workflow-foundation` スキルを `code_review.enabled: true` / `github_pr.enabled: true` で再実行する。

### 4.5 セキュリティモデル

```
AI Agent ──→ wrapper（bin/github-pr-*-safe）──→ GitHub API
               │
               ├── ~/.config/github-apps/private-key.pem を読み取り
               ├── installation token を発行
               └── API レスポンスのうち安全な部分のみ AI に返却

AI Agent は token / private key に直接アクセスできない
  └── .cursorignore が bin/ を AI コンテキストから除外（サンドボックス遮断）
  └── guard-git-write.sh が gh auth token / .pem 読み取りをブロック
  └── 03-github-security.mdc が認証ファイル読み取りを禁止
```

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

- [ ] `python3` / `git` がインストール済み（`make check`）
- [ ] Cursor Settings → Features → Hooks が有効
- [ ] 基盤ファイルの初回生成が完了（`agentic-workflow-foundation` スキルを実行）

### 推奨

- [ ] `jq` がインストール済み（Hook の JSON 処理）
- [ ] GitHub の Branch Protection Rules を設定

### オプション（agent-code-review / agent-github-pr を使う場合）

- [ ] GitHub Apps を作成（Webhook Active を **OFF**、OAuth 関連は未設定）
- [ ] Repository permissions を設定（Pull requests + Metadata、必要なら Contents も）
- [ ] GitHub Apps を対象リポジトリにインストール
- [ ] Private key を `~/.config/github-apps/` に配置（`chmod 600`）
- [ ] §4.3 のサンプルに従い `config.env` を作成（`chmod 600`）
- [ ] スキル実行後に `bin/github-pr-*-safe` が生成されていることを確認（`test -x bin/github-pr-reviews-safe`）

### オプション（CodeRabbit を使う場合）

- [ ] CodeRabbit アカウントを作成
- [ ] 対象リポジトリを CodeRabbit に接続
- [ ] PR を作成して CodeRabbit のレビューが動作することを確認
