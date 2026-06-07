#!/usr/bin/env bash
# check-mcp-env.sh — GitHub MCP 用の環境診断
# 秘密はリポジトリに書かない。PAT はリポジトリ直下の .env で供給する。

set -uo pipefail

ok=0
warn=0
fail=0

pass() { echo "  OK   $1"; ok=$((ok + 1)); }
note() { echo "  NOTE $1"; warn=$((warn + 1)); }
err()  { echo "  NG   $1"; fail=$((fail + 1)); }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

echo "GitHub MCP 環境チェック"
echo

# --- .env ---
if [[ -f "$ENV_FILE" ]]; then
  pass ".env が存在する: ${ENV_FILE}"
else
  err ".env がない: ${ENV_FILE} を作成し GITHUB_TOKEN を設定"
fi

# --- GITHUB_TOKEN（.env から読み込み） ---
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  pass "GITHUB_TOKEN が .env に設定されている"
else
  err "GITHUB_TOKEN が .env にない: ${ENV_FILE} に GITHUB_TOKEN=ghp_... を追加"
fi

# --- Docker ---
if ! command -v docker >/dev/null 2>&1; then
  err "docker コマンドが見つからない"
elif ! docker info >/dev/null 2>&1; then
  err "Docker デーモンに接続できない（Docker Desktop を起動）"
else
  pass "Docker デーモンに接続できる"
fi

# --- GitHub MCP イメージ ---
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if docker image inspect ghcr.io/github/github-mcp-server:latest >/dev/null 2>&1; then
    pass "ghcr.io/github/github-mcp-server イメージがローカルにある"
  else
    note "イメージ未 pull（MCP 初回接続時に自動取得される）"
  fi
fi

# --- コンテナ起動（トークンがあるときのみ） ---
if [[ -n "${GITHUB_TOKEN:-}" ]] && command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  mcp_boot_log="$(
    printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"check-mcp-env","version":"1.0"}}}\n' \
      | docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_TOKEN" ghcr.io/github/github-mcp-server 2>&1 \
      || true
  )"
  if [[ "$mcp_boot_log" == *"GitHub MCP Server running on stdio"* ]]; then
    pass "github-mcp-server コンテナが PAT 付きで起動できる"
  elif [[ "$mcp_boot_log" == *"GITHUB_PERSONAL_ACCESS_TOKEN not set"* ]]; then
    err "github-mcp-server が PAT 未設定で終了した"
  else
    err "github-mcp-server の起動に失敗（PAT 無効・イメージ破損の可能性）"
  fi
fi

echo
echo "結果: OK=$ok / NOTE=$warn / NG=$fail"

if [[ $fail -gt 0 ]]; then
  echo
  echo "次の手順:"
  echo "  1. リポジトリ直下に .env を作成し  GITHUB_TOKEN=ghp_...  を設定"
  echo "  2. Docker Desktop を起動"
  echo "  3. Cursor を完全終了して再起動し、Settings → MCP で github を確認"
  exit 1
fi

if [[ $warn -gt 0 ]]; then
  exit 0
fi

echo "GitHub MCP の前提は満たしています。"
exit 0
