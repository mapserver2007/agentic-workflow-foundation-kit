#!/usr/bin/env bash
set -euo pipefail
set +x

readonly GITHUB_CREDENTIAL_PROVIDER="${AGENTIC_WORKFLOW_UPDATE_CREDENTIAL_PROVIDER:-github_app}"
readonly GITHUB_KEYCHAIN_SERVICE="${AGENTIC_WORKFLOW_UPDATE_KEYCHAIN_SERVICE:-agentic-workflow-github-api}"
readonly GITHUB_KEYCHAIN_ACCOUNT="${AGENTIC_WORKFLOW_UPDATE_KEYCHAIN_ACCOUNT:-}"
readonly GITHUB_CURL_TIMEOUT=60

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_github-app-auth.sh
source "${SCRIPT_DIR}/_github-app-auth.sh"
# shellcheck source=_github-keychain-auth.sh
source "${SCRIPT_DIR}/_github-keychain-auth.sh"

GITHUB_AUTH_TOKEN=""
GITHUB_HTTP_CODE=""
GITHUB_HTTP_BODY=""
OWNER=""
REPO=""

_kit_validate_name() {
  local label="$1" value="$2"
  [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "ERROR: invalid GitHub ${label}" >&2
    return 2
  }
}

_kit_curl() {
  curl \
    --connect-timeout 10 \
    --max-time "$GITHUB_CURL_TIMEOUT" \
    --proto '=https' \
    --proto-redir '=https' \
    "$@"
}

_kit_http_request_secret() {
  local secret="$1" method="$2" url="$3" payload="${4:-}"
  local escaped response payload_file=""
  escaped="${secret//\\/\\\\}"
  escaped="${escaped//\"/\\\"}"
  if [[ -n "$payload" ]]; then
    umask 077
    payload_file=$(mktemp "${TMPDIR:-/tmp}/kit-update-api.XXXXXX")
    printf '%s' "$payload" > "$payload_file"
  fi
  trap '[[ -z "${payload_file:-}" ]] || rm -f -- "$payload_file"' RETURN
  response=$(
    {
      printf 'header = "Authorization: Bearer %s"\n' "$escaped"
      if [[ -n "$payload_file" ]]; then
        printf 'data-binary = "@%s"\n' "$payload_file"
      fi
    } |
      if [[ -n "$payload_file" ]]; then
        _kit_curl --config - -sS -w $'\n%{http_code}' \
          -X "$method" -H "Accept: application/vnd.github+json" \
          -H "Content-Type: application/json" "$url"
      else
        _kit_curl --config - -sS -w $'\n%{http_code}' \
          -X "$method" -H "Accept: application/vnd.github+json" "$url"
      fi
  ) || {
    trap - RETURN
    [[ -z "$payload_file" ]] || rm -f -- "$payload_file"
    GITHUB_HTTP_CODE=""
    GITHUB_HTTP_BODY=""
    return 1
  }
  trap - RETURN
  [[ -z "$payload_file" ]] || rm -f -- "$payload_file"
  GITHUB_HTTP_CODE="${response##*$'\n'}"
  GITHUB_HTTP_BODY="${response%$'\n'*}"
}

_kit_parse_remote_url() {
  local url="$1"
  if [[ "$url" =~ ^https://github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
  elif [[ "$url" =~ ^git@github\.com:([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
  elif [[ "$url" =~ ^ssh://git@github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
  else
    echo "ERROR: GitHub の HTTPS/SSH remote だけを許可します" >&2
    return 2
  fi
  _kit_validate_name owner "$OWNER" || return $?
  _kit_validate_name repo "$REPO" || return $?
}

_kit_detect_owner_repo() {
  local worktree="$1" remote="$2" remote_url
  remote_url=$(git -C "$worktree" remote get-url "$remote" 2>/dev/null) || {
    echo "ERROR: git remote '${remote}' が設定されていません" >&2
    return 1
  }
  _kit_parse_remote_url "$remote_url"
}

_kit_get_token() {
  local owner="$1" repo="$2"
  _kit_validate_name owner "$owner" || return $?
  _kit_validate_name repo "$repo" || return $?
  GITHUB_AUTH_TOKEN=""
  case "$GITHUB_CREDENTIAL_PROVIDER" in
    github_app)
      _kit_app_get_token "$owner" "$repo" git-read
      ;;
    keychain)
      _kit_keychain_get_token "$owner" "$repo" git-read
      ;;
    *)
      echo "ERROR: unsupported credential provider" >&2
      return 2
      ;;
  esac
  [[ -n "$GITHUB_AUTH_TOKEN" && "$GITHUB_AUTH_TOKEN" != *$'\n'* && "$GITHUB_AUTH_TOKEN" != *$'\r'* ]] || {
    GITHUB_AUTH_TOKEN=""
    echo "ERROR: credential provider returned an invalid token" >&2
    return 2
  }
}

_kit_write_askpass() {
  local path="$1"
  cat > "$path" <<'ASKPASS'
#!/usr/bin/env bash
set -euo pipefail
set +x
case "${1:-}" in
  *sername*|*Username*) printf '%s\n' "x-access-token" ;;
  *assword*|*Password*) printf '%s\n' "${AGENTIC_WORKFLOW_UPDATE_TOKEN:?}" ;;
  *) exit 1 ;;
esac
ASKPASS
  chmod 700 "$path"
}

_kit_git_run() {
  local owner="$1" repo="$2"
  shift 2
  _kit_get_token "$owner" "$repo" || return $?
  (
    set +x
    umask 077
    local askpass
    askpass=$(mktemp "${TMPDIR:-/tmp}/kit-update-askpass.XXXXXX")
    trap 'rm -f -- "$askpass"' EXIT INT TERM HUP
    _kit_write_askpass "$askpass"
    GIT_TERMINAL_PROMPT=0 \
      GIT_ASKPASS="$askpass" \
      GCM_INTERACTIVE=Never \
      AGENTIC_WORKFLOW_UPDATE_TOKEN="$GITHUB_AUTH_TOKEN" \
      git -c credential.helper= -c credential.useHttpPath=true "$@"
  )
  local rc=$?
  GITHUB_AUTH_TOKEN=""
  return "$rc"
}

_kit_git_with_remote() {
  local worktree="$1" remote="$2"
  shift 2
  local before after https_url
  before=$(git -C "$worktree" remote get-url "$remote" 2>/dev/null) || return 1
  (
    _kit_detect_owner_repo "$worktree" "$remote" || exit $?
    https_url="https://github.com/${OWNER}/${REPO}.git"
    _kit_git_run "$OWNER" "$REPO" \
      -C "$worktree" -c "remote.${remote}.url=${https_url}" "$@"
  )
  local rc=$?
  after=$(git -C "$worktree" remote get-url "$remote" 2>/dev/null) || return 1
  if [[ "$before" != "$after" ]]; then
    echo "ERROR: persistent remote URL が変更されました" >&2
    return 2
  fi
  return "$rc"
}

_kit_git_clone() {
  local source_root="$1" target="$2" branch="$3"
  _kit_detect_owner_repo "$source_root" origin || return $?
  _kit_git_run "$OWNER" "$REPO" clone --single-branch \
    --branch "$branch" \
    "https://github.com/${OWNER}/${REPO}.git" "$target"
}

