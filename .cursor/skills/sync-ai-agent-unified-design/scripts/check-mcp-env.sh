#!/usr/bin/env bash
# check-mcp-env.sh — GitHub MCP 用の環境診断・（任意）launchctl 登録
# 秘密はリポジトリに書かない。PAT は ~/.zshenv 等のユーザー環境で供給する。

set -uo pipefail

FIX=false
if [[ "${1:-}" == "--fix" ]]; then
  FIX=true
fi

ok=0
warn=0
fail=0

pass() { echo "  OK   $1"; ok=$((ok + 1)); }
note() { echo "  NOTE $1"; warn=$((warn + 1)); }
err()  { echo "  NG   $1"; fail=$((fail + 1)); }

echo "GitHub MCP 環境チェック"
echo

# ~/.zshenv は zsh のみ。シェルに未設定なら読み込んで試す（値は表示しない）
if [[ -z "${GITHUB_TOKEN:-}" && -f "${HOME}/.zshenv" ]]; then
  # shellcheck disable=SC1090
  source "${HOME}/.zshenv" 2>/dev/null || true
fi

# --- GITHUB_TOKEN（シェル） ---
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  pass "GITHUB_TOKEN がシェル環境に設定されている"
else
  err "GITHUB_TOKEN がシェル環境にない（~/.zshenv に export を追加）"
fi

# --- GITHUB_TOKEN（launchd / Cursor 向け） ---
launchctl_token=""
if launchctl_token="$(launchctl getenv GITHUB_TOKEN 2>/dev/null)"; then
  :
else
  launchctl_token=""
fi

if [[ -n "$launchctl_token" ]]; then
  pass "GITHUB_TOKEN が launchctl に登録されている（GUI 起動の Cursor が参照可能）"
elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
  err "GITHUB_TOKEN が launchctl 未登録（Dock/Finder 起動の Cursor は PAT を読めない）"
  if $FIX; then
    launchctl setenv GITHUB_TOKEN "$GITHUB_TOKEN"
    pass "--fix: launchctl setenv GITHUB_TOKEN を実行した（Cursor を再起動すること）"
    fail=$((fail - 1))
  else
    note "修復: $0 --fix  または  launchctl setenv GITHUB_TOKEN \"\$GITHUB_TOKEN\""
  fi
else
  err "GITHUB_TOKEN が launchctl 未登録（先に ~/.zshenv へ PAT を設定）"
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
  echo "  1. ~/.zshenv に  export GITHUB_TOKEN=\"ghp_...\"  を追加"
  echo "  2. $0 --fix  で launchctl へ登録（ログアウトで消える）"
  echo "  3. Cursor を完全終了して再起動し、Settings → MCP で github を確認"
  exit 1
fi

if [[ $warn -gt 0 ]]; then
  exit 0
fi

echo "GitHub MCP の前提は満たしています。"
exit 0
