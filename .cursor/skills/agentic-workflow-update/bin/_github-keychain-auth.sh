#!/usr/bin/env bash
set -euo pipefail
set +x

_kit_keychain_get_token() {
  local token
  [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] || {
    echo "ERROR: keychain provider は macOS のみ対応しています" >&2
    return 2
  }
  [[ -n "${GITHUB_KEYCHAIN_SERVICE:-}" && -n "${GITHUB_KEYCHAIN_ACCOUNT:-}" ]] || {
    echo "ERROR: Keychain service/account が設定されていません" >&2
    return 2
  }
  token=$(
    /usr/bin/security find-generic-password \
      -s "$GITHUB_KEYCHAIN_SERVICE" \
      -a "$GITHUB_KEYCHAIN_ACCOUNT" \
      -w 2>/dev/null
  ) || {
    echo "ERROR: 専用 GitHub credential を Keychain から取得できません" >&2
    return 2
  }
  [[ -n "$token" && "$token" != *$'\n'* && "$token" != *$'\r'* ]] || {
    echo "ERROR: Keychain credential が空または不正です" >&2
    return 2
  }
  GITHUB_AUTH_TOKEN="$token"
  token=""
}

