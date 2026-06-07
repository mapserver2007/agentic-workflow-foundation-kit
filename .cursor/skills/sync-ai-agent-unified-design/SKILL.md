---
name: sync-ai-agent-unified-design
description: >-
  private リポジトリにある「3つの統一設計書」Markdown（AI_AGENT_UNIFIED_DESIGN /
  AI_BUSINESS_AGENT_SUITE / TECHNOLOGY_STACK_UNIFIED_DESIGN）を GitHub MCP
  （失敗時は gh CLI フォールバック）で取得し、`.cursor/docs/` に冪等同期する。
  設計書が存在しない場合は取得し、存在しても改版/更新があれば上書きする（内容差分時のみ）。
  主目的は create-agentic-workflow-foundation の Phase 0 から呼ばれて統一設計書(SoT)を
  揃えることだが、PO が単独で実行してもよい。「統一設計書を取得/同期して」「設計書を最新化して」
  「sync-ai-agent-unified-design スキル」「統一設計書が無いので取得して」等を検知したときに使う。
  Fetch the 3 unified design docs from a private GitHub repo into `.cursor/docs/`.
disable-model-invocation: true
---

# sync-ai-agent-unified-design

private リポジトリ上の「3つの統一設計書」Markdown を `.cursor/docs/` に**冪等同期**するスキル。`create-agentic-workflow-foundation` が SoT として参照する設計書を取得・最新化する入口。

## 役割と境界

- **取得元**: private リポジトリ（`references/source.yaml` の `repository`）。
- **配置先（固定3ファイル）**: `create-agentic-workflow-foundation` が SoT として参照する正規パス。
  - `.cursor/docs/AI_AGENT_UNIFIED_DESIGN.md`
  - `.cursor/docs/AI_BUSINESS_AGENT_SUITE.md`
  - `.cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md`
- **やること**: 取得して配置/上書きするだけ（同期）。設計書の内容生成・編集はしない。
- **冪等性**: 内容差分があるときのみ上書きする。差分がなければスキップ（再実行でファイル不変）。

## 前提条件

- **取得設定**: `references/source.yaml` に `repository` / `ref` / `files`（src→dest 対応）を記入済みであること。`[要確認]` が残っている `src` は取得対象外（未確定として報告）。
- **GitHub 認証（Fine-grained PAT）**: 対象 repo / Contents: Read-only / Metadata: Read-only に絞った PAT を、環境変数 `GITHUB_TOKEN` で供給する（`~/.zshenv` に `export GITHUB_TOKEN="..."` を推奨）。
- **MCP 経路（主）**: `.cursor/mcp.json` の `github` サーバ（docker `ghcr.io/github/github-mcp-server`、`GITHUB_PERSONAL_ACCESS_TOKEN: ${env:GITHUB_TOKEN}`）が稼働。docker 必須。`mcp.json` は秘密を含まない（環境変数参照のみ）ためリポジトリにコミット共有してよい。**PAT を mcp.json に直書きしない**。
- **gh CLI 経路（フォールバック）**: MCP が未稼働/失敗のとき `gh` を使う。MCP と同じ Fine-grained PAT を使う（`gh auth login --with-token` 等）。

## ワークフロー

```
- [ ] Step 0: 設定読込・前提チェック（source.yaml / repository / files）
- [ ] Step 1: .cursor/docs/ を用意
- [ ] Step 2: 各ファイルを取得（MCP 優先 → gh CLI フォールバック）
- [ ] Step 3: ローカルと内容比較し、差分時/不在時のみ上書き（CREATED / UPDATED / UNCHANGED）
- [ ] Step 4: 報告（取得結果・skip した項目・未確定の設定）
```

### Step 0: 設定読込・前提チェック

1. `references/source.yaml` を読む。`repository` が `[要確認]` のままなら停止して PO に記入を依頼する。
2. `files` の各エントリの `src` が `[要確認]` のものは取得対象から除外し、Step 4 で「未確定」として列挙する。
3. 取得対象が 0 件なら、その旨を報告して停止する。

### Step 1: 配置先ディレクトリ

`.cursor/docs/` が無ければ作成する。

```bash
mkdir -p .cursor/docs
```

### Step 2: 取得（MCP 優先 → gh CLI フォールバック）

各 `files[*]` について、`repository`（`owner/repo`）・`src`・`ref` を使って内容を取得する。

**MCP 経路（主）**: `.cursor/mcp.json` の `github` サーバの `get_file_contents` を `CallMcpTool` で呼ぶ。
- **呼ぶ前に必ず**該当ツールの descriptor（`mcps/<github server>/tools/get_file_contents.json` 等）を読み、引数名（owner / repo / path / ref など）を確認してから呼ぶ。
- private リポジトリの取得は `GITHUB_TOKEN` の権限に依存する。401/403 や「サーバ未稼働」のときは gh CLI へフォールバックする。

**gh CLI 経路（フォールバック）**:

```bash
gh api "repos/{owner}/{repo}/contents/{src}?ref={ref}" --jq '.content' | base64 -d > /tmp/fetched.md
```

- `{owner}/{repo}` は `repository`、`{src}` は `files[*].src`、`{ref}` は `ref`。
- 取得に失敗したファイルは**書き込まず**、Step 4 で失敗として報告する（不完全な空ファイルを残さない）。

### Step 3: 差分判定して上書き

取得した内容を `dest`（固定3ファイルのいずれか）と比較する。

- `dest` が存在しない → **CREATED**（新規書き込み）。
- 存在し、内容が異なる → **UPDATED**（上書き。改版/更新の反映）。
- 存在し、内容が同一 → **UNCHANGED**（書き込まずスキップ。冪等）。

> `overwrite: always` の場合は差分の有無に関わらず書き込む（ただし内容同一なら結果は UNCHANGED 相当）。既定は `diff`。

### Step 4: 報告

以下を報告する:

- ファイルごとの結果（CREATED / UPDATED / UNCHANGED / FAILED）と使用経路（MCP / gh）。
- `[要確認]` のため取得しなかった項目（PO が次に `source.yaml` に記入すべき `src`）。
- 失敗があった場合は原因（認証・パス誤り・サーバ未稼働など）と対処（PAT 権限 / `src` 修正 / docker 起動）。

## 重要な制約

- `.cursor/docs/` 配下の**固定3ファイルのみ**管理する。他のファイルは作らない/触らない。
- 取得失敗時は空ファイルや部分内容を書かない。明確に FAILED として報告する。
- 設計書の**内容は編集しない**（取得した内容をそのまま配置）。manifest への反映は `create-agentic-workflow-foundation` の責務。
- 設定は `references/source.yaml` に集約する。SKILL.md にリポジトリ識別子やパスをハードコードしない。

## スコープ外

- 取得した設計書の内容生成・要約・整形。
- `create-agentic-workflow-foundation` の manifest 更新や基盤ファイル生成（親スキルの責務）。
- `.cursor/docs/` 配下の固定3ファイル以外の Domain docs の取得。
