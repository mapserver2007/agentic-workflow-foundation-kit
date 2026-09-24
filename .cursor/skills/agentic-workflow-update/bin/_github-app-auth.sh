#!/usr/bin/env bash
set -euo pipefail
set +x

readonly GITHUB_APP_CONFIG_ENV="${HOME}/.config/github-apps/config.env"

_kit_b64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

_kit_generate_jwt() {
  local key_path now header payload encoded
  key_path="${GITHUB_APP_PRIVATE_KEY_PATH:-${HOME}/.config/github-apps/private-key.pem}"
  [[ -f "$key_path" ]] || {
    echo "ERROR: GitHub App private key が見つかりません" >&2
    return 2
  }
  now=$(date +%s)
  header=$(printf '{"alg":"RS256","typ":"JWT"}' | _kit_b64url)
  payload=$(printf '{"iss":"%s","iat":%d,"exp":%d}' \
    "$GITHUB_APP_ID" "$((now - 60))" "$((now + 540))" | _kit_b64url)
  encoded="${header}.${payload}"
  printf '%s.%s' "$encoded" \
    "$(printf '%s' "$encoded" | openssl dgst -sha256 -sign "$key_path" -binary | _kit_b64url)"
}

_kit_app_get_token() {
  local owner="$1" repo="$2" jwt installation_id payload parsed permission
  [[ -f "$GITHUB_APP_CONFIG_ENV" ]] || {
    echo "ERROR: GitHub App config が見つかりません" >&2
    return 2
  }
  # shellcheck source=/dev/null
  source "$GITHUB_APP_CONFIG_ENV"
  [[ -n "${GITHUB_APP_ID:-}" ]] || {
    echo "ERROR: GITHUB_APP_ID が設定されていません" >&2
    return 2
  }
  jwt=$(_kit_generate_jwt) || return $?
  _kit_http_request_secret "$jwt" GET \
    "https://api.github.com/repos/${owner}/${repo}/installation" || {
    echo "ERROR: GitHub App installation lookup failed" >&2
    return 2
  }
  jwt=""
  [[ "$GITHUB_HTTP_CODE" == "200" ]] || {
    echo "ERROR: GitHub App installation を解決できません" >&2
    GITHUB_HTTP_BODY=""
    return 2
  }
  installation_id=$(printf '%s' "$GITHUB_HTTP_BODY" | python3 -c '
import json, sys
try:
    value = json.load(sys.stdin)
except Exception:
    value = {}
identifier = value.get("id")
print(identifier if isinstance(identifier, int) else "")
')
  GITHUB_HTTP_BODY=""
  [[ -n "$installation_id" ]] || {
    echo "ERROR: GitHub App installation ID がありません" >&2
    return 2
  }
  payload=$(printf '{"repositories":[%s]}' \
    "$(printf '%s' "$repo" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")
  jwt=$(_kit_generate_jwt) || return $?
  _kit_http_request_secret "$jwt" POST \
    "https://api.github.com/app/installations/${installation_id}/access_tokens" \
    "$payload" || {
    echo "ERROR: GitHub App token の取得に失敗しました" >&2
    return 2
  }
  jwt=""
  [[ "$GITHUB_HTTP_CODE" == "201" ]] || {
    echo "ERROR: GitHub App token を発行できません" >&2
    GITHUB_HTTP_BODY=""
    return 2
  }
  parsed=$(printf '%s' "$GITHUB_HTTP_BODY" | python3 -c '
import json, sys
try:
    value = json.load(sys.stdin)
except Exception:
    value = {}
token = value.get("token")
permission = (value.get("permissions") or {}).get("contents", "")
print(token if isinstance(token, str) else "")
print(permission if isinstance(permission, str) else "")
')
  GITHUB_HTTP_BODY=""
  GITHUB_AUTH_TOKEN="${parsed%%$'\n'*}"
  permission="${parsed#*$'\n'}"
  [[ -n "$GITHUB_AUTH_TOKEN" ]] && {
    [[ "$permission" == "read" || "$permission" == "write" ]]
  } || {
    GITHUB_AUTH_TOKEN=""
    echo "ERROR: GitHub App に Contents read 権限がありません" >&2
    return 2
  }
}

