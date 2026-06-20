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
3. GitHub App のインストールを承認（`Pull requests: Read and write` 権限が必要）

### 3.3 動作確認

1. PR を作成する
2. CodeRabbit bot がレビューコメントを投稿することを確認
3. `.coderabbit.yaml` の設定（言語・ツール・path_instructions）が反映されていることを確認

> CodeRabbit の GitHub App と次節の agent-code-review 用 GitHub App は別物。CodeRabbit は CodeRabbit 社が提供する App、agent-code-review 用は自分で作成する App。

---

## 4. GitHub App — agent-code-review wrapper 用（オプション）

`code_review.enabled: true` の場合に生成される `agent-code-review` スキルは、AI に GitHub token を露出しない安全な wrapper コマンド（`github-pr-reviews-safe` / `github-pr-comment-safe` / `github-pr-reply-safe`）を使用する。この wrapper は GitHub App の installation token を内部で発行する。

### 4.1 GitHub App の作成

1. GitHub → **Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**
2. 以下を設定:

| 項目 | 値 |
| --- | --- |
| App name | 任意（例: `my-org-pr-review-bot`） |
| Homepage URL | リポジトリ URL 等 |
| Webhook | **Active のチェックを外す**（不要） |

3. **Repository permissions** を設定:

| Permission | Access |
| --- | --- |
| Pull requests | **Read and write** |
| Metadata | **Read** |

4. **Where can this GitHub App be installed?** → **Only on this account**（組織内のみ）
5. **Create GitHub App** をクリック

### 4.2 Private Key の生成・配置

1. 作成した App のページで **Generate a private key** をクリック
2. ダウンロードされた `.pem` ファイルを安全な場所に配置
3. AI（Cursor Agent）からはアクセスできない権限に設定する

```bash
chmod 600 /path/to/private-key.pem
```

> private key のパスは wrapper の実装に合わせて配置する。`.cursor/rules/03-github-security.mdc` により、AI は `.pem` / `.key` ファイルの読み取りを禁止されている。

### 4.3 GitHub App のインストール

1. App のページ → **Install App** → 対象リポジトリを選択
2. **App ID** と **Installation ID** をメモしておく（wrapper の設定に使用）

### 4.4 wrapper コマンドのインストール

wrapper コマンド 3 つを `/usr/local/bin/` に配置する。

```bash
# インストール後の確認
which github-pr-reviews-safe && which github-pr-comment-safe && which github-pr-reply-safe
```

| wrapper | 用途 | 引数 |
| --- | --- | --- |
| `github-pr-reviews-safe` | レビュースレッド取得（READ） | `<owner> <repo> <pr-number>` |
| `github-pr-comment-safe` | PR コメント投稿（WRITE） | `<pr-number> <body-file>` |
| `github-pr-reply-safe` | レビューコメント reply（WRITE） | `<comment-id> <body-file>` |

> wrapper の実装は本キットには含まれない。GitHub App の private key を読み取り、installation token を発行して GitHub API を呼び出すスクリプトを各環境に合わせて作成する。

### 4.5 セキュリティモデル

```
AI Agent ──→ wrapper（/usr/local/bin/github-pr-*-safe）──→ GitHub API
               │
               ├── private key を読み取り
               ├── installation token を発行
               └── API レスポンスのうち安全な部分のみ AI に返却

AI Agent は token / private key に直接アクセスできない
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

### オプション（agent-code-review を使う場合）

- [ ] GitHub App を作成・インストール
- [ ] Private key を生成・安全に配置
- [ ] wrapper コマンド 3 つを `/usr/local/bin/` にインストール
- [ ] `which github-pr-reviews-safe && which github-pr-comment-safe && which github-pr-reply-safe` で確認

### オプション（CodeRabbit を使う場合）

- [ ] CodeRabbit アカウントを作成
- [ ] 対象リポジトリを CodeRabbit に接続
- [ ] PR を作成して CodeRabbit のレビューが動作することを確認
