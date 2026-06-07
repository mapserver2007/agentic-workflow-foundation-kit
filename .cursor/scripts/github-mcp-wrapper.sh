#!/usr/bin/env bash
# GitHub MCP 起動ラッパー — リポジトリ直下の .env から PAT を読み込む（秘密はリポジトリにコミットしない）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "GITHUB_TOKEN が未設定です。$ENV_FILE に GITHUB_TOKEN を設定してください。" >&2
  exit 1
fi

exec docker run -i --rm \
  -e "GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_TOKEN" \
  ghcr.io/github/github-mcp-server
