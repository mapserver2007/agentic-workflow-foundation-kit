#!/usr/bin/env python3
"""GitHub provider / HTTPS Git wrapper の fixture テスト。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
TEMPLATES = SKILL_DIR / "templates"
BIN_TEMPLATES = TEMPLATES / "bin"
ROOT = SKILL_DIR.parents[2]
ENGINE_SCRIPTS = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
sys.path.insert(0, str(ENGINE_SCRIPTS))
sys.path.insert(0, str(HERE))

import genlib  # noqa: E402
import run_resolved_engine as rre  # noqa: E402


def _render_auth(provider: str, service: str = "svc", account: str = "acct") -> str:
    return (
        (BIN_TEMPLATES / "_github-auth.sh.template")
        .read_text(encoding="utf-8")
        .replace("{{github_access.api_credential_provider}}", provider)
        .replace("{{github_access.keychain.service}}", service)
        .replace("{{github_access.keychain.account}}", account)
    )


def _fixture_bin(root: Path, provider: str, service: str = "svc", account: str = "acct") -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    files = {
        "_github-auth.sh": _render_auth(provider, service=service, account=account),
        "_github-app-auth.sh": (
            BIN_TEMPLATES / "_github-app-auth.sh.template"
        ).read_text(encoding="utf-8"),
        "_github-keychain-auth.sh": (
            BIN_TEMPLATES / "_github-keychain-auth.sh.template"
        ).read_text(encoding="utf-8"),
    }
    for name, content in files.items():
        path = bin_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o700)
    return bin_dir


def _bash(script: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=cwd,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def _assert(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _test_app_installation_scope(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-app-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "github_app")
        config_dir = root / "home" / ".config" / "github-apps"
        config_dir.mkdir(parents=True)
        (config_dir / "config.env").write_text("GITHUB_APP_ID=123\n", encoding="utf-8")
        script = f"""
source {bin_dir / "_github-auth.sh"}
_generate_jwt() {{ printf '%s' 'fixture-jwt'; }}
curl() {{
  local config url="" arg
  config=$(cat)
  [[ "$config" == *"Authorization: Bearer fixture-jwt"* ]] || return 97
  for arg in "$@"; do
    [[ "$arg" == https://* ]] && url="$arg"
  done
  case "$url" in
    */repos/org/repo-a/installation) printf '%s\\n200' '{{"id":101}}' ;;
    */repos/org/repo-b/installation) printf '%s\\n200' '{{"id":202}}' ;;
    */repos/org/repo-c/installation) printf '%s\\n200' '{{"id":303}}' ;;
    */repos/org/repo-d/installation) printf '%s\\n200' '{{"id":404}}' ;;
    */app/installations/101/access_tokens) printf '%s\\n201' '{{"token":"SENTINEL_A","permissions":{{"contents":"write"}}}}' ;;
    */app/installations/202/access_tokens) printf '%s\\n201' '{{"token":"SENTINEL_B","permissions":{{"contents":"read"}}}}' ;;
    */app/installations/303/access_tokens) printf '%s\\n401' '{{"message":"SENTINEL_401"}}' ;;
    */app/installations/404/access_tokens) printf '%s\\n403' '{{"message":"SENTINEL_403"}}' ;;
    *) printf '%s\\n404' '{{"message":"SENTINEL_REFLECTION","documentation_url":"https://docs.github.com/rest"}}' ;;
  esac
}}
_get_github_token org repo-a git-write
[[ "$GITHUB_AUTH_TOKEN" == SENTINEL_A ]]
GITHUB_AUTH_TOKEN=""
_get_github_token org repo-b git-read
[[ "$GITHUB_AUTH_TOKEN" == SENTINEL_B ]]
GITHUB_AUTH_TOKEN=""
if _get_github_token org repo-b git-write; then exit 89; fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
if _get_github_token org repo-c git-read; then exit 87; fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
if _get_github_token org repo-d git-read; then exit 88; fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
if _get_github_token org missing git-read; then exit 90; fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
printf 'PASS\\n'
"""
        result = _bash(script, root, {"HOME": str(root / "home")})
        _assert(result.returncode == 0, f"app fixture failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "app fixture exposed data on stdout", errors)
        combined = result.stdout + result.stderr
        _assert("SENTINEL_A" not in combined, "app token A leaked", errors)
        _assert("SENTINEL_B" not in combined, "app token B leaked", errors)
        _assert("SENTINEL_REFLECTION" not in combined, "API error body leaked", errors)
        _assert("SENTINEL_401" not in combined, "401 body leaked", errors)
        _assert("SENTINEL_403" not in combined, "403 body leaked", errors)


def _test_app_jwt_failure(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-app-jwt-failure-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "github_app")
        config_dir = root / "home" / ".config" / "github-apps"
        config_dir.mkdir(parents=True)
        (config_dir / "config.env").write_text("GITHUB_APP_ID=123\n", encoding="utf-8")
        http_called = root / "http-called"
        script = f"""
source {bin_dir / "_github-auth.sh"}
_github_http_request_secret() {{ touch {http_called}; return 0; }}
if _get_github_token org repo api-read; then exit 89; fi
rc=$?
[[ "$rc" -eq 2 ]]
[[ ! -e {http_called} ]]
printf 'PASS\\n'
"""
        result = _bash(script, root, {"HOME": str(root / "home")})
        _assert(result.returncode == 0, f"JWT failure fixture failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "JWT failure fixture output mismatch", errors)


def _test_dispatcher_and_askpass(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-dispatch-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "keychain")
        askpass_dir = root / "tmp"
        askpass_dir.mkdir()
        script = f"""
source {bin_dir / "_github-auth.sh"}
_github_keychain_get_token() {{ GITHUB_AUTH_TOKEN='SENTINEL_KEYCHAIN'; }}
captured=$(_get_github_token org repo api-read)
[[ -z "$captured" && "$GITHUB_AUTH_TOKEN" == SENTINEL_KEYCHAIN ]]
GITHUB_AUTH_TOKEN=""
askpass={askpass_dir / "askpass"}
_github_write_askpass "$askpass"
[[ "$(GITHUB_OPERATION_TOKEN=SENTINEL_ASKPASS "$askpass" 'Username for https://github.com')" == x-access-token ]]
password=$(GITHUB_OPERATION_TOKEN=SENTINEL_ASKPASS "$askpass" 'Password for https://github.com')
[[ "$password" == SENTINEL_ASKPASS ]]
if GITHUB_OPERATION_TOKEN=SENTINEL_ASKPASS "$askpass" 'Unknown prompt'; then exit 91; fi
rm -f "$askpass"
_get_github_token() {{ GITHUB_AUTH_TOKEN='SENTINEL_GIT'; }}
git() {{
  if [[ "$*" != *"credential.helper="* ]]; then
    touch {askpass_dir / "credential-helper-called"}
    return 92
  fi
  [[ "$*" != *SENTINEL_GIT* ]] || return 93
  [[ "${{GITHUB_OPERATION_TOKEN:-}}" == SENTINEL_GIT ]] || return 93
  return 1
}}
if TMPDIR={askpass_dir} _github_git_run org repo git-read fetch origin; then exit 94; fi
if compgen -G '{askpass_dir}/github-askpass.*' >/dev/null; then exit 95; fi
[[ ! -e {askpass_dir / "credential-helper-called"} ]]
_get_github_token() {{ GITHUB_AUTH_TOKEN='SENTINEL_ABORT'; }}
git() {{
  [[ "$*" == *"credential.helper="* ]] || return 92
  return 77
}}
if TMPDIR={askpass_dir} _github_git_run org repo git-read fetch origin; then exit 96; fi
if compgen -G '{askpass_dir}/github-askpass.*' >/dev/null; then exit 97; fi
python3 -c '
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for path in root.rglob("*"):
    if path.is_file() and b"SENTINEL_" in path.read_bytes():
        raise SystemExit(1)
' {askpass_dir}
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"dispatcher/askpass fixture failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "dispatcher fixture exposed token", errors)
        combined = result.stdout + result.stderr
        for sentinel in ("SENTINEL_KEYCHAIN", "SENTINEL_ASKPASS", "SENTINEL_GIT"):
            _assert(sentinel not in combined, f"{sentinel} leaked", errors)


def _test_keychain_backend(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-keychain-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "keychain")
        script = f"""
source {bin_dir / "_github-auth.sh"}
uname() {{ printf 'Darwin\\n'; }}
_github_keychain_security() {{
  [[ "$#" -eq 6 ]]
  [[ "$1" == find-generic-password && "$2" == -s && "$3" == svc ]]
  [[ "$4" == -a && "$5" == acct && "$6" == -w ]]
  printf 'SENTINEL_PAT'
}}
_github_keychain_get_token org repo api-read
[[ "$GITHUB_AUTH_TOKEN" == SENTINEL_PAT ]]
GITHUB_AUTH_TOKEN=""
_github_keychain_security() {{
  [[ "$3" == wrong-svc || "$5" == wrong-acct ]] && {{ printf 'SENTINEL_WRONG\\n'; return 0; }}
  return 44
}}
if _github_keychain_get_token org repo api-read; then exit 96; fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
_github_keychain_security() {{ return 36; }}
if _github_keychain_get_token org repo api-read; then exit 97; fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
_github_keychain_security() {{
  [[ "$3" == svc && "$5" == acct ]] || return 44
  printf ''
  return 0
}}
if _github_keychain_get_token org repo api-read; then exit 98; fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
uname() {{ printf 'Linux\\n'; }}
if _github_keychain_get_token org repo api-read; then exit 100; fi
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"keychain fixture failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "keychain fixture exposed token", errors)
        combined = result.stdout + result.stderr
        _assert("SENTINEL_PAT" not in combined, "Keychain PAT leaked", errors)
        _assert("SENTINEL_WRONG" not in combined, "wrong Keychain item leaked", errors)

    with tempfile.TemporaryDirectory(prefix="github-keychain-config-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "keychain", service="", account="acct")
        script = f"""
source {bin_dir / "_github-auth.sh"}
uname() {{ printf 'Darwin\\n'; }}
if _github_keychain_get_token org repo api-read; then exit 101; fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"keychain config fixture failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "keychain config fixture output mismatch", errors)


def _test_api_secret_transport(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-api-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "keychain")
        temp_dir = root / "tmp"
        temp_dir.mkdir()
        script = f"""
source {bin_dir / "_github-auth.sh"}
export TMPDIR={temp_dir}
escaped=$(_github_curl_config_escape 'a"b\\c')
[[ "$escaped" == 'a\\"b\\\\c' ]]
_github_keychain_get_token() {{ GITHUB_AUTH_TOKEN='SENTINEL_API'; }}
curl() {{
  local config arg
  config=$(cat)
  [[ "$config" == *"Authorization: Bearer SENTINEL_API"* ]] || return 71
  [[ "$config" == *'data-binary = "@'* ]] || return 74
  for arg in "$@"; do
    [[ "$arg" != *SENTINEL_API* ]] || return 72
    [[ "$arg" != *SENTINEL_BODY* ]] || return 75
  done
  if [[ "$*" == *"/failure"* ]]; then
    printf '%s\\n403' '{{"message":"SENTINEL_REFLECTED","documentation_url":"https://docs.github.com/rest"}}'
  else
    printf '%s\\n200' '{{"ok":true}}'
  fi
}}
_github_api_request org repo api-read POST https://api.github.com/success 200 '{{"body":"SENTINEL_BODY"}}'
[[ "$GITHUB_HTTP_BODY" == '{{"ok":true}}' && -z "$GITHUB_AUTH_TOKEN" ]]
if compgen -G '{temp_dir}/github-api-body.*' >/dev/null; then exit 76; fi
if _github_api_request org repo api-read GET https://api.github.com/failure 200; then
  exit 73
else
  rc=$?
fi
[[ "$rc" -eq 1 ]]
[[ -z "$GITHUB_AUTH_TOKEN" ]]
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"API secret transport failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "API transport output mismatch", errors)
        combined = result.stdout + result.stderr
        _assert("SENTINEL_API" not in combined, "API credential leaked", errors)
        _assert("SENTINEL_REFLECTED" not in combined, "API error body leaked", errors)


def _test_remote_parser(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-parser-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "github_app")
        script = f"""
source {bin_dir / "_github-auth.sh"}
_github_parse_remote_url https://github.com/org/repo.git
[[ "$OWNER" == org && "$REPO" == repo ]]
_github_parse_remote_url git@github.com:org/repo.git
[[ "$OWNER" == org && "$REPO" == repo ]]
_github_parse_remote_url ssh://git@github.com/org/repo.git
[[ "$OWNER" == org && "$REPO" == repo ]]
for url in \
  https://example.com/org/repo.git \
  https://token@github.com/org/repo.git \
  https://github.com.evil.test/org/repo.git \
  prefix-git@github.com:org/repo.git \
  https://github.com/org/repo/extra; do
  if _github_parse_remote_url "$url"; then exit 74; fi
  rc=$?
  [[ "$rc" -eq 2 ]]
done
if _github_validate_name owner 'bad/name'; then exit 75; fi
rc=$?
[[ "$rc" -eq 2 ]]
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"remote parser fixture failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "remote parser output mismatch", errors)


def _test_ssh_remote_https_override(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-remote-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "github_app")
        script = f"""
source {bin_dir / "_github-auth.sh"}
_get_github_token() {{ GITHUB_AUTH_TOKEN='SENTINEL_REMOTE'; }}
GIT_RECORD=""
git() {{
  GIT_RECORD+="|$*"
  if [[ "$*" == *"remote get-url --push origin"* || "$*" == *"remote get-url origin"* ]]; then
    printf 'git@github.com:org/repo.git\\n'
    return 0
  fi
  [[ "$*" == *"credential.helper="* ]] || return 81
  [[ "$*" == *"remote.origin.url=https://github.com/org/repo.git"* ]] || return 82
  [[ "$*" != *SENTINEL_REMOTE* ]] || return 83
  [[ "${{GITHUB_OPERATION_TOKEN:-}}" == SENTINEL_REMOTE ]] || return 84
  return 0
}}
before_fetch=$(git remote get-url origin)
before_push=$(git remote get-url --push origin)
_github_git_with_remote . origin git-read fetch --prune origin
_github_git_with_remote . origin git-write push -u origin HEAD
after_fetch=$(git remote get-url origin)
after_push=$(git remote get-url --push origin)
[[ "$before_fetch" == "$after_fetch" && "$before_push" == "$after_push" ]]
[[ "$GIT_RECORD" != *SENTINEL_REMOTE* ]]
git() {{
  if [[ "$*" == *"remote get-url --push origin"* ]]; then
    printf 'git@github.com:org/other.git\\n'
  elif [[ "$*" == *"remote get-url origin"* ]]; then
    printf 'git@github.com:org/repo.git\\n'
  else
    return 85
  fi
}}
_github_git_run() {{ touch {root / "invalid-git-run"}; return 0; }}
if _github_git_with_remote . origin git-read fetch origin; then
  exit 87
else
  rc=$?
fi
[[ "$rc" -eq 2 ]]
[[ ! -e {root / "invalid-git-run"} ]]
if _detect_owner_repo origin; then
  exit 86
else
  rc=$?
fi
[[ "$rc" -eq 2 ]]
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"SSH remote fixture failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "SSH remote fixture output mismatch", errors)
        _assert("SENTINEL_REMOTE" not in result.stdout + result.stderr, "remote token leaked", errors)


def _test_exit_code_contract(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-exitcode-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "github_app")
        script = f"""
source {bin_dir / "_github-auth.sh"}
if _github_parse_remote_url https://evil.example.com/org/repo.git; then exit 71; fi
rc=$?
[[ "$rc" -eq 2 ]]
if _get_github_token org repo unsupported-op; then exit 72; fi
rc=$?
[[ "$rc" -eq 2 ]]
git() {{ return 1; }}
if _detect_owner_repo origin; then exit 73; fi
rc=$?
[[ "$rc" -eq 1 ]]
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"exit code contract failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "exit code contract output mismatch", errors)

    with tempfile.TemporaryDirectory(prefix="github-exitcode-keychain-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "keychain")
        script = f"""
source {bin_dir / "_github-auth.sh"}
_github_keychain_get_token() {{ return 2; }}
if _get_github_token org repo api-read; then exit 74; fi
rc=$?
[[ "$rc" -eq 2 ]]
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"keychain exit code contract failed: {result.stderr}", errors)


def _test_cross_repo_https_transport(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-crossrepo-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "github_app")
        worktree = root / "clone-base" / "demo-repo"
        worktree.mkdir(parents=True)
        script = f"""
source {bin_dir / "_github-auth.sh"}
_get_github_token() {{ GITHUB_AUTH_TOKEN='SENTINEL_CROSS'; }}
HTTPS_URL="https://github.com/myorg/demo-repo.git"
SSH_ORIGIN="git@github.com:myorg/demo-repo.git"
GIT_RECORD=""
git() {{
  GIT_RECORD+="|$*"
  case "$*" in
    *"remote get-url origin"*) printf '%s\\n' "$SSH_ORIGIN"; return 0 ;;
    *"remote get-url --push origin"*) printf '%s\\n' "$SSH_ORIGIN"; return 0 ;;
  esac
  [[ "$*" == *"credential.helper="* ]] || return 91
  [[ "$*" != *SENTINEL_CROSS* ]] || return 92
  [[ "${{GITHUB_OPERATION_TOKEN:-}}" == SENTINEL_CROSS ]] || return 93
  case "$*" in
    *clone*) [[ "$*" == *"$HTTPS_URL"* ]] || return 94 ;;
    *fetch*) [[ "$*" == *"$HTTPS_URL"* ]] || return 95 ;;
    *pull*) [[ "$*" == *"$HTTPS_URL"* ]] || return 96 ;;
  esac
  return 0
}}
before_origin=$(git -C {worktree} remote get-url origin)
_github_git_run myorg demo-repo git-read clone --quiet "$HTTPS_URL" {worktree / "new-clone"}
clone_record="$GIT_RECORD"
GIT_RECORD=""
_github_git_run myorg demo-repo git-read -C {worktree} fetch --prune --quiet "$HTTPS_URL" "+refs/heads/*:refs/remotes/origin/*"
fetch_record="$GIT_RECORD"
GIT_RECORD=""
_github_git_run myorg demo-repo git-read -C {worktree} pull --quiet "$HTTPS_URL" main
pull_record="$GIT_RECORD"
after_origin=$(git -C {worktree} remote get-url origin)
[[ "$before_origin" == "$after_origin" ]]
[[ "$clone_record" == *"$HTTPS_URL"* ]]
[[ "$fetch_record" == *"$HTTPS_URL"* && "$fetch_record" != *"$SSH_ORIGIN"* ]]
[[ "$pull_record" == *"$HTTPS_URL"* && "$pull_record" != *"$SSH_ORIGIN"* ]]
combined="$clone_record$fetch_record$pull_record"
[[ "$combined" != *SENTINEL_CROSS* ]]
_get_github_token() {{ GITHUB_AUTH_TOKEN='SENTINEL_HTTPS'; }}
HTTPS_ORIGIN="https://github.com/myorg/demo-repo.git"
GIT_RECORD=""
git() {{
  GIT_RECORD+="|$*"
  case "$*" in
    *"remote get-url origin"*) printf '%s\\n' "$HTTPS_ORIGIN"; return 0 ;;
    *"remote get-url --push origin"*) printf '%s\\n' "$HTTPS_ORIGIN"; return 0 ;;
  esac
  [[ "$*" == *"credential.helper="* ]] || return 91
  [[ "$*" != *SENTINEL_HTTPS* ]] || return 92
  return 0
}}
_github_git_run myorg demo-repo git-read -C {worktree} fetch --prune --quiet "$HTTPS_URL" "+refs/heads/*:refs/remotes/origin/*"
[[ "$GIT_RECORD" == *"$HTTPS_URL"* ]]
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"cross-repo transport failed: {result.stderr}", errors)
        _assert(result.stdout == "PASS\n", "cross-repo transport output mismatch", errors)
        combined = result.stdout + result.stderr
        _assert("SENTINEL_CROSS" not in combined, "cross-repo token leaked", errors)
        _assert("SENTINEL_HTTPS" not in combined, "cross-repo HTTPS token leaked", errors)


def _test_cross_repo_wrapper_exit_codes(errors: list[str]) -> None:
    cross_repo = (BIN_TEMPLATES / "cross-repo-sync-safe.template").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="github-crossrepo-wrapper-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "github_app")
        (bin_dir / "cross-repo-sync-safe").write_text(cross_repo, encoding="utf-8")
        (bin_dir / "cross-repo-sync-safe").chmod(0o700)
        missing_config = root / "missing-config.json"
        result_missing = _bash(f"{bin_dir / 'cross-repo-sync-safe'} sync missing.json demo 2>&1", root)
        _assert(result_missing.returncode == 2, "missing config should exit 2", errors)
        result_bad_action = _bash(
            f"{bin_dir / 'cross-repo-sync-safe'} bad-action {missing_config} demo 2>&1",
            root,
        )
        _assert(result_bad_action.returncode == 2, "bad action should exit 2", errors)
        config = root / "config.json"
        config.write_text(
            '{"clone_base_path":"/tmp/x","github_org":"org","repositories":[{"name":"demo","active":false}]}',
            encoding="utf-8",
        )
        result_inactive = _bash(
            f"{bin_dir / 'cross-repo-sync-safe'} sync {config} demo 2>&1",
            root,
        )
        _assert(result_inactive.returncode == 2, "inactive repo should exit 2", errors)


def _test_static_contract(errors: list[str]) -> None:
    common = (BIN_TEMPLATES / "_github-auth.sh.template").read_text(encoding="utf-8")
    app = (BIN_TEMPLATES / "_github-app-auth.sh.template").read_text(encoding="utf-8")
    keychain = (BIN_TEMPLATES / "_github-keychain-auth.sh.template").read_text(encoding="utf-8")
    cross_repo = (BIN_TEMPLATES / "cross-repo-sync-safe.template").read_text(encoding="utf-8")
    _assert("_get_github_token" in common, "dispatcher entrypoint missing", errors)
    _assert("credential.helper=" in common and "GIT_ASKPASS" in common, "Git isolation missing", errors)
    _assert('--data-binary "$payload"' not in common, "API body remains in curl argv", errors)
    _assert('data-binary = "@%s"' in common, "API body file config missing", errors)
    _assert("/repos/${owner}/${repo}/installation" in app, "repo installation lookup missing", errors)
    _assert(
        app.count("jwt=$(_generate_jwt) || return $?") == 2,
        "JWT generation failures are not propagated at both call sites",
        errors,
    )
    _assert(
        "_github_curl_config_escape" in common
        and 'printf \'header = "Authorization: Bearer %s"\\n\' "$escaped_secret"' in common
        and 'printf \'header = "Authorization: Bearer %s"\\n\' "$escaped_token"' in common,
        "curl config secrets are not escaped at every call site",
        errors,
    )
    _assert("GITHUB_APP_INSTALLATION_ID" not in app, "fixed installation ID remains", errors)
    _assert("/usr/bin/security" in keychain and "-s \"$GITHUB_KEYCHAIN_SERVICE\"" in keychain,
            "Keychain exact service lookup missing", errors)
    _assert("-a \"$GITHUB_KEYCHAIN_ACCOUNT\"" in keychain, "Keychain exact account lookup missing", errors)
    _assert("git_protocol" not in cross_repo, "cross-repo protocol selector remains", errors)
    _assert("_github_git_run" in cross_repo, "cross-repo Git helper missing", errors)
    _assert("_github_git_with_remote" not in cross_repo,
            "cross-repo transport still depends on stored origin", errors)
    _assert('fetch --prune --quiet "$HTTPS_REPO_URL"' in cross_repo,
            "cross-repo fetch does not use explicit HTTPS URL", errors)
    _assert('pull --quiet "$HTTPS_REPO_URL" "$branch"' in cross_repo,
            "cross-repo pull does not use explicit HTTPS URL", errors)

    wrapper_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in BIN_TEMPLATES.glob("github-*-safe.template")
    )
    _assert("_get_installation_token" not in wrapper_text, "legacy App token call remains", errors)
    _assert("Authorization: token" not in wrapper_text, "token header remains in wrapper argv", errors)

    skill_paths = list((TEMPLATES / "skills").rglob("*.template"))
    network_command = re.compile(r"^\s*git\s+(fetch|push|clone|pull)(?:\s|$)", re.MULTILINE)
    for path in skill_paths:
        text = path.read_text(encoding="utf-8")
        _assert(not network_command.search(text), f"direct Git network guidance remains: {path}", errors)

    seed = (SKILL_DIR / "manifest.yaml").read_text(encoding="utf-8")
    config_template = (
        TEMPLATES / "skills" / "cross-repository-knowledge-link" / "config.json.template"
    ).read_text(encoding="utf-8")
    _assert("git_protocol:" not in seed, "seed git_protocol remains", errors)
    _assert('"git_protocol"' not in config_template, "generated config git_protocol remains", errors)


def _run_guard_hook(guard: Path, command: str) -> tuple[int, str, dict[str, str] | None]:
    result = subprocess.run(
        ["bash", str(guard)],
        input=json.dumps({"command": command}),
        text=True,
        capture_output=True,
        check=False,
    )
    stdout = result.stdout.strip()
    if stdout == "{}":
        return result.returncode, stdout, None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return result.returncode, stdout, None
    if not isinstance(parsed, dict):
        return result.returncode, stdout, None
    return result.returncode, stdout, parsed


def _assert_guard_permission(
    errors: list[str],
    guard: Path,
    command: str,
    expected: str,
    *,
    reason_fragment: str | None = None,
) -> None:
    returncode, stdout, response = _run_guard_hook(guard, command)
    _assert(
        returncode == 0,
        f"guard exited {returncode} for {command!r}: {stdout!r}",
        errors,
    )
    if expected == "allow":
        _assert(stdout == "{}", f"guard blocked allow command: {command!r} -> {stdout!r}", errors)
        return
    if response is None:
        errors.append(f"guard returned invalid JSON for {command!r}: {stdout!r}")
        return
    _assert(
        response.get("permission") == expected,
        f"guard expected {expected} for {command!r}, got {response!r}",
        errors,
    )
    if reason_fragment:
        combined = f"{response.get('reason', '')} {response.get('agent_message', '')}"
        _assert(reason_fragment in combined, f"guard message missing {reason_fragment!r}: {command!r}", errors)


def _test_guard_deny_patterns(errors: list[str]) -> None:
    guard = TEMPLATES / "hooks" / "guard-git-write.sh.template"
    deny_commands = (
        "git push --force origin feature",
        "git push origin --delete old-branch",
        "git push origin :branch",
        "git push origin +:branch",
        "git push upstream :feature",
        "git push upstream +:release/v1",
        "git reset --hard origin/main",
        "gh pr merge 1",
        "gh repo delete org/repo",
        "gh pr list",
        "command gh repo view",
        "/usr/local/bin/gh release list",
        "env gh pr list",
        "env FOO=bar gh pr list",
        "FOO=bar gh pr list",
        "sudo gh pr list",
        "bash -c 'gh pr list'",
        "sh -c 'gh issue view 1'",
        "zsh -c 'gh api repos/org/repo'",
        "gh issue comment 1 --body test",
        "gh pr create --title t --body b",
        "gh auth token",
    )
    for command in deny_commands:
        _assert_guard_permission(errors, guard, command, "deny")

    _assert_guard_permission(
        errors,
        guard,
        "gh issue comment 1 --body test",
        "deny",
        reason_fragment="現在未対応",
    )


def _test_guard_allow_and_ask_regression(errors: list[str]) -> None:
    guard = TEMPLATES / "hooks" / "guard-git-write.sh.template"
    allow_commands = (
        "git status --short",
        "git diff --stat",
        "bin/github-pr-create-safe main /tmp/title /tmp/body",
        "./bin/github-issue-read-safe 42",
        "printf 'gh pr list\\n'",
        "echo 'use gh pr create via wrapper'",
        "grep -R 'gh pr merge' docs/",
    )
    for command in allow_commands:
        _assert_guard_permission(errors, guard, command, "allow")

    ask_commands = (
        "git commit --amend --no-edit",
        "git rebase main",
        "env",
        "printenv",
        "git config --global --list",
    )
    for command in ask_commands:
        _assert_guard_permission(errors, guard, command, "ask")


def _test_curl_transport_constraints(errors: list[str]) -> None:
    auth_template = (BIN_TEMPLATES / "_github-auth.sh.template").read_text(encoding="utf-8")
    for needle in (
        "readonly GITHUB_CURL_CONNECT_TIMEOUT=10",
        "readonly GITHUB_CURL_MAX_TIME=60",
        "--proto '=https'",
        "--proto-redir '=https'",
        "_github_curl()",
    ):
        _assert(needle in auth_template, f"_github-auth missing curl constraint: {needle}", errors)

    issue_read = (BIN_TEMPLATES / "github-issue-read-safe.template").read_text(encoding="utf-8")
    _assert("_github_curl -sSL" in issue_read, "public attachment path bypasses _github_curl", errors)
    _assert(
        "_github_download_text" in issue_read,
        "private attachment path missing authenticated download helper",
        errors,
    )

    with tempfile.TemporaryDirectory(prefix="github-curl-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "keychain")
        curl_log = root / "curl-log.txt"
        script = f"""
source {bin_dir / "_github-auth.sh"}
curl() {{
  local arg
  for arg in "$@"; do
    printf '%s\\n' "$arg" >> {curl_log}
  done
  if [[ "$*" == *"/success"* ]]; then
    printf '%s\\n200' '{{"ok":true}}'
  elif [[ "$*" == *user-attachments/files/* ]]; then
    printf 'attachment-body'
    return 0
  else
    printf '%s\\n403' '{{"message":"fail"}}'
  fi
}}
_github_keychain_get_token() {{ GITHUB_AUTH_TOKEN='SENTINEL_CURL'; }}
_github_api_request org repo api-read GET https://api.github.com/success 200
[[ -z "$GITHUB_AUTH_TOKEN" ]]
if _github_download_text org repo https://github.com/user-attachments/files/1/download 1024; then
  [[ "$GITHUB_HTTP_BODY" == attachment-body ]] || exit 81
else
  exit 81
fi
[[ -z "$GITHUB_AUTH_TOKEN" ]]
att_content=$(_github_curl -sSL --max-filesize 4096 https://github.com/user-attachments/files/1/public.txt)
[[ "$att_content" == attachment-body ]] || exit 82
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"curl transport fixture failed: {result.stderr}", errors)
        log_text = curl_log.read_text(encoding="utf-8") if curl_log.is_file() else ""
        _assert(log_text.count("--connect-timeout") >= 3, "curl --connect-timeout missing on paths", errors)
        _assert(log_text.count("--max-time") >= 3, "curl --max-time missing on paths", errors)
        _assert(log_text.count("--proto") >= 3, "curl --proto missing on paths", errors)
        _assert(log_text.count("--proto-redir") >= 3, "curl --proto-redir missing on paths", errors)
        _assert(log_text.count("=https") >= 6, "curl HTTPS proto flags missing on paths", errors)


def _test_positive_id_contract(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="github-id-fixture-") as tmp:
        root = Path(tmp)
        bin_dir = _fixture_bin(root, "keychain")
        script = f"""
source {bin_dir / "_github-auth.sh"}
_github_validate_positive_id "PR number" "123" || exit 71
for bad in 0 001; do
  if _github_validate_positive_id "PR number" "$bad"; then exit 72; fi
  rc=$?
  [[ "$rc" -eq 2 ]]
done
[[ "$(_github_normalize_comment_id r123)" == "123" ]]
[[ "$(_github_normalize_comment_id 456)" == "456" ]]
for bad in r0 r001 0 001; do
  if _github_normalize_comment_id "$bad"; then exit 73; fi
  rc=$?
  [[ "$rc" -eq 2 ]]
done
printf 'PASS\\n'
"""
        result = _bash(script, root)
        _assert(result.returncode == 0, f"positive ID fixture failed: {result.stderr}", errors)

    wrappers: list[tuple[str, list[str], int]] = [
        ("github-pr-comment-safe.template", ["0", "/dev/null"], 2),
        ("github-pr-reviews-safe.template", ["org", "repo", "001"], 2),
        ("github-issue-read-safe.template", ["0"], 2),
        ("github-pr-reply-safe.template", ["1", "r0", "/dev/null"], 2),
        ("github-pr-reply-safe.template", ["1", "001", "/dev/null"], 2),
    ]
    for template_name, args, expected_rc in wrappers:
        with tempfile.TemporaryDirectory(prefix=f"github-wrapper-id-{template_name}-") as tmp:
            root = Path(tmp)
            bin_dir = _fixture_bin(root, "keychain")
            wrapper_src = (BIN_TEMPLATES / template_name).read_text(encoding="utf-8")
            wrapper_path = bin_dir / template_name.replace(".template", "")
            wrapper_path.write_text(wrapper_src, encoding="utf-8")
            wrapper_path.chmod(0o700)
            body_file = root / "body.md"
            body_file.write_text("test", encoding="utf-8")
            rendered_args = [str(arg).replace("/dev/null", str(body_file)) for arg in args]
            result = _bash(
                f"{wrapper_path} {' '.join(rendered_args)} 2>&1",
                root,
            )
            _assert(
                result.returncode == expected_rc,
                f"{template_name} args {args!r} expected rc {expected_rc}, got {result.returncode}",
                errors,
            )


def _test_skill_prerequisite_fail_closed(errors: list[str]) -> None:
    skill_paths = (
        TEMPLATES / "skills" / "agent-github-pr" / "SKILL.md.template",
        TEMPLATES / "skills" / "agent-github-pr" / "references" / "pr-commands.md.template",
        TEMPLATES / "skills" / "agent-github-issue" / "SKILL.md.template",
        TEMPLATES / "skills" / "agent-github-issue" / "references" / "issue-commands.md.template",
    )
    prerequisite_re = re.compile(
        r"test -x bin/github-(?:pr-create-safe|issue-create-safe|issue-read-safe)"
        r"(?:\s*&&\s*test -x bin/github-(?:issue-create-safe|issue-read-safe))?"
        r"\s*\|\|\s*\{\s*echo \"GitHub wrapper not found\" >&2;\s*exit 1;\s*\}"
    )
    fail_open_re = re.compile(
        r"test -x bin/github-(?:pr-create-safe|issue-create-safe|issue-read-safe)"
        r"(?:\s*&&\s*test -x bin/github-(?:issue-create-safe|issue-read-safe))?"
        r"\s*\|\|\s*echo"
    )
    for path in skill_paths:
        text = path.read_text(encoding="utf-8")
        _assert(
            prerequisite_re.search(text) is not None,
            f"fail-closed wrapper prerequisite missing: {path}",
            errors,
        )
        _assert(
            fail_open_re.search(text) is None,
            f"fail-open wrapper prerequisite remains: {path}",
            errors,
        )

    with tempfile.TemporaryDirectory(prefix="github-skill-prereq-") as tmp:
        root = Path(tmp)
        (root / "bin").mkdir()
        checks = (
            "test -x bin/github-pr-create-safe || { echo \"GitHub wrapper not found\" >&2; exit 1; }",
            "test -x bin/github-issue-create-safe && test -x bin/github-issue-read-safe || { echo \"GitHub wrapper not found\" >&2; exit 1; }",
        )
        for check in checks:
            result = _bash(check, root)
            _assert(result.returncode == 1, f"missing wrapper should exit 1: {check}", errors)
            _assert(
                "GitHub wrapper not found" in result.stderr,
                f"missing wrapper should print stderr message: {check}",
                errors,
            )


def _test_feature_matrix(errors: list[str]) -> None:
    feature_names = ("code_review", "github_pr", "github_issue", "cross_repo_knowledge")
    expected_specific = {
        "code_review": {
            "bin/github-git-fetch-safe",
            "bin/github-pr-reviews-safe",
            "bin/github-pr-comment-safe",
            "bin/github-pr-reply-safe",
        },
        "github_pr": {"bin/github-pr-create-safe"},
        "github_issue": {
            "bin/github-issue-create-safe",
            "bin/github-issue-read-safe",
        },
        "cross_repo_knowledge": {"bin/cross-repo-sync-safe"},
    }
    helpers = {
        "bin/_github-auth.sh",
        "bin/_github-app-auth.sh",
        "bin/_github-keychain-auth.sh",
    }
    for active in (None, *feature_names, "all"):
        manifest = genlib.load_manifest(str(SKILL_DIR / "manifest.yaml"))
        for name in feature_names:
            manifest[name]["enabled"] = active == "all" or active == name
        resolved = rre._filter_outputs_by_features(manifest)
        paths = {item["path"] for item in resolved["outputs"]}
        expected = set()
        if active == "all":
            for values in expected_specific.values():
                expected.update(values)
        elif active in expected_specific:
            expected.update(expected_specific[active])
        expected_helpers = helpers if active is not None else set()
        _assert(
            paths.intersection(helpers) == expected_helpers,
            f"helper feature matrix mismatch: {active}",
            errors,
        )
        all_specific = set().union(*expected_specific.values())
        _assert(
            paths.intersection(all_specific) == expected,
            f"wrapper feature matrix mismatch: {active}",
            errors,
        )

    # GitHub API feature をすべて無効にしても、cross-repo の HTTPS Git transport は
    # provider dispatcher と両 backend を必要とする。
    manifest = genlib.load_manifest(str(SKILL_DIR / "manifest.yaml"))
    for name in feature_names:
        manifest[name]["enabled"] = name == "cross_repo_knowledge"
    manifest["github_access"] = {
        "api_credential_provider": "keychain",
        "keychain": {"service": "cross-only-service", "account": "cross-only-account"},
    }
    paths = {item["path"] for item in rre._filter_outputs_by_features(manifest)["outputs"]}
    _assert(helpers.issubset(paths), "cross-repo + keychain omitted auth helpers", errors)
    _assert("bin/cross-repo-sync-safe" in paths, "cross-repo wrapper missing", errors)
    _assert(
        not paths.intersection(
            {
                "bin/github-git-fetch-safe",
                "bin/github-pr-create-safe",
                "bin/github-issue-create-safe",
                "bin/github-issue-read-safe",
            }
        ),
        "cross-repo only unexpectedly enabled GitHub API wrappers",
        errors,
    )


def _test_root_overlay_to_wrapper_constants(errors: list[str]) -> None:
    """root overlay の provider locator が resolved wrapper 定数へ届くことを検証する。"""
    root_manifest = ROOT / "manifest.yaml"
    with tempfile.TemporaryDirectory(prefix="github-root-overlay-") as tmp:
        fixture_root = Path(tmp) / "manifest.yaml"
        root_text = root_manifest.read_text(encoding="utf-8")
        overlay = (
            "github_access:\n"
            "  api_credential_provider: keychain\n"
            "  keychain:\n"
            "    service: overlay-service\n"
            "    account: overlay-account\n"
        )
        fixture_text, substitutions = re.subn(
            r"^github_access:\n(?:^[ \t].*(?:\n|$))+",
            overlay,
            root_text,
            flags=re.MULTILINE,
        )
        if substitutions != 1:
            errors.append("root overlay fixture could not replace github_access")
            return
        fixture_root.write_text(fixture_text, encoding="utf-8")
        fixture_design = (
            fixture_root.parent
            / ".cursor"
            / "docs"
            / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
        )
        fixture_design.parent.mkdir(parents=True)
        fixture_design.write_text(
            (ROOT / ".cursor" / "docs" / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        resolved = rre.resolved_manifest(str(SKILL_DIR / "manifest.yaml"), str(fixture_root))
        access = resolved.get("github_access") or {}
        keychain = access.get("keychain") or {}
        _assert(access.get("api_credential_provider") == "keychain", "root provider overlay lost", errors)
        _assert(keychain.get("service") == "overlay-service", "root service overlay lost", errors)
        _assert(keychain.get("account") == "overlay-account", "root account overlay lost", errors)

        rendered = _render_auth(
            access.get("api_credential_provider", ""),
            keychain.get("service", ""),
            keychain.get("account", ""),
        )
        _assert(
            'readonly GITHUB_CREDENTIAL_PROVIDER="keychain"' in rendered,
            "resolved provider did not render into auth wrapper",
            errors,
        )
        _assert(
            'readonly GITHUB_KEYCHAIN_SERVICE="overlay-service"' in rendered
            and 'readonly GITHUB_KEYCHAIN_ACCOUNT="overlay-account"' in rendered,
            "resolved Keychain locator did not render into auth wrapper",
            errors,
        )


def _test_generated_legacy_audit(errors: list[str]) -> None:
    """生成済み docs/skills に廃止済み認証案内を残さない。"""
    generated_docs = (
        ROOT / "AGENTS.md",
        ROOT / "CLAUDE.md",
        ROOT / "docs" / "QUALITY_GATE.md",
        ROOT / ".cursor" / "hooks" / "README.md",
    )
    generated_skills = (ROOT / ".cursor" / "skills")
    forbidden = ("PAT 未設定だから gh deny", "GitHub App 常時必須", "git_protocol:")
    for path in generated_docs:
        if not path.is_file():
            errors.append(f"generated doc missing: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for legacy in forbidden:
            _assert(legacy not in text, f"generated legacy text remains: {path}: {legacy}", errors)
    network_command = re.compile(r"^\s*git\s+(fetch|push|clone|pull)(?:\s|$)", re.MULTILINE)
    for path in generated_skills.rglob("*.md"):
        if "agentic-workflow-foundation" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for legacy in forbidden:
            _assert(legacy not in text, f"generated legacy text remains: {path}: {legacy}", errors)
        _assert(
            not network_command.search(text),
            f"generated direct Git network guidance remains: {path}",
            errors,
        )


def main() -> int:
    errors: list[str] = []
    _test_app_installation_scope(errors)
    _test_app_jwt_failure(errors)
    _test_dispatcher_and_askpass(errors)
    _test_keychain_backend(errors)
    _test_api_secret_transport(errors)
    _test_remote_parser(errors)
    _test_ssh_remote_https_override(errors)
    _test_exit_code_contract(errors)
    _test_cross_repo_https_transport(errors)
    _test_cross_repo_wrapper_exit_codes(errors)
    _test_static_contract(errors)
    _test_guard_deny_patterns(errors)
    _test_guard_allow_and_ask_regression(errors)
    _test_curl_transport_constraints(errors)
    _test_positive_id_contract(errors)
    _test_skill_prerequisite_fail_closed(errors)
    _test_feature_matrix(errors)
    _test_root_overlay_to_wrapper_constants(errors)
    _test_generated_legacy_audit(errors)
    if errors:
        for error in errors:
            print(f"[test_github_auth_runtime] FAIL: {error}")
        return 1
    print("[test_github_auth_runtime] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
