#!/usr/bin/env python3
"""ローカル Git worktree をネットワークなし・読み取り専用で検証する。"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlsplit

OWNER_RE = re.compile(r"^[A-Za-z0-9-]+$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SANITIZED_GIT_ENV_KEYS = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_GRAFT_FILE",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_QUARANTINE_PATH",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)


class InspectionError(Exception):
    """検証失敗。code は CLI の exit code に対応する。"""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RepositoryIdentity:
    canonical_url: str
    owner: str
    repo: str


@dataclass(frozen=True)
class RepositoryInspection:
    source_repository: str
    source_ref: str
    source_revision: str
    uninitialized_submodules: int
    raw_origin: str
    source_root: str
    source_root_realpath: str


def _validate_owner_repo(owner: str, repo: str) -> None:
    if not OWNER_RE.fullmatch(owner):
        raise InspectionError("owner の文字種が契約外です", 2)
    if not REPO_RE.fullmatch(repo) or repo in {".", ".."}:
        raise InspectionError("repo の文字種が契約外です", 2)


def normalize_origin_url(value: str) -> RepositoryIdentity:
    """許可された origin 表記を canonical HTTPS URL に正規化する。"""
    owner: str
    repo: str
    if value.startswith("git@github.com:"):
        path = value[len("git@github.com:") :]
        parts = path.split("/")
        if len(parts) != 2:
            raise InspectionError("origin の形式が契約外です", 2)
        owner, repo = parts
    else:
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise InspectionError("origin の形式が契約外です", 2) from exc
        scheme = parsed.scheme.lower()
        if scheme == "https":
            if parsed.username is not None or parsed.password is not None:
                raise InspectionError("credential を含む origin は使用できません", 2)
        elif scheme == "ssh":
            if parsed.username != "git" or parsed.password is not None:
                raise InspectionError("origin の SSH userinfo が契約外です", 2)
        else:
            raise InspectionError("origin の transport が契約外です", 2)
        if (
            parsed.hostname is None
            or parsed.hostname.lower() != "github.com"
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise InspectionError("origin は GitHub リポジトリルートである必要があります", 2)
        parts = parsed.path.split("/")
        if len(parts) != 3 or not parts[1] or not parts[2]:
            raise InspectionError("origin は GitHub リポジトリルートである必要があります", 2)
        owner, repo = parts[1], parts[2]
    repo = repo[:-4] if repo.endswith(".git") else repo
    _validate_owner_repo(owner, repo)
    return RepositoryIdentity(f"https://github.com/{owner}/{repo}", owner, repo)


def _safe_git(
    root: Path,
    args: Sequence[str],
    *,
    git_executable: str,
    env: Mapping[str, str] | None,
    accepted: Sequence[int] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    command = [
        git_executable,
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-C",
        os.fspath(root),
        *args,
    ]
    git_env = dict(os.environ)
    if env is not None:
        git_env.update(env)
    for key in tuple(git_env):
        if key in SANITIZED_GIT_ENV_KEYS or key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            git_env.pop(key, None)
    git_env["GIT_OPTIONAL_LOCKS"] = "0"
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    git_env["GIT_ATTR_NOSYSTEM"] = "1"
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            env=git_env,
        )
    except (OSError, ValueError) as exc:
        raise InspectionError("git を実行できません", 2) from exc
    if result.returncode not in accepted:
        raise InspectionError("ローカル Git metadata を読み取れません", 2)
    return result


def _decode_git(value: bytes) -> str:
    return value.decode("utf-8", errors="surrogateescape").strip()


def _validate_root(source_root: str) -> Path:
    if not os.path.isabs(source_root):
        raise InspectionError("source root は絶対パスで指定してください", 2)
    root = Path(source_root)
    try:
        metadata = os.lstat(root)
    except OSError as exc:
        raise InspectionError("source root を参照できません", 2) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise InspectionError("source root は symlink でないディレクトリが必要です", 2)
    return root


def inspect_repository(
    source_root: str,
    *,
    git_executable: str = "git",
    env: Mapping[str, str] | None = None,
) -> RepositoryInspection:
    """clean な origin worktree を検証し、再利用可能な来歴情報を返す。"""
    root = _validate_root(source_root)

    bare = _decode_git(
        _safe_git(root, ["rev-parse", "--is-bare-repository"], git_executable=git_executable, env=env).stdout
    )
    if bare != "false":
        raise InspectionError("bare repository は使用できません", 2)
    top = _decode_git(
        _safe_git(root, ["rev-parse", "--show-toplevel"], git_executable=git_executable, env=env).stdout
    )
    if os.path.realpath(top) != os.path.realpath(root):
        raise InspectionError("source root は worktree root と一致する必要があります", 2)

    origins_raw = _safe_git(
        root,
        ["config", "--get-all", "remote.origin.url"],
        git_executable=git_executable,
        env=env,
        accepted=(0, 1),
    ).stdout
    origins = [_decode_git(item) for item in origins_raw.splitlines() if item]
    if len(origins) != 1:
        raise InspectionError("origin は単一 URL である必要があります", 2)
    raw_origin = origins[0]
    origin = normalize_origin_url(raw_origin)

    revision = _decode_git(
        _safe_git(root, ["rev-parse", "HEAD"], git_executable=git_executable, env=env).stdout
    )
    if not SHA_RE.fullmatch(revision):
        raise InspectionError("HEAD は 40 桁 commit SHA である必要があります", 2)
    branch_result = _safe_git(
        root,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        git_executable=git_executable,
        env=env,
        accepted=(0, 1),
    )
    source_ref = _decode_git(branch_result.stdout) if branch_result.returncode == 0 else "detached"
    if not source_ref:
        raise InspectionError("checkout 中の branch を判定できません", 2)

    status_output = _safe_git(
        root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
        git_executable=git_executable,
        env=env,
    ).stdout
    if status_output:
        raise InspectionError("worktree が clean ではありません", 1)

    index_entries = _safe_git(
        root,
        ["ls-files", "-s", "-z"],
        git_executable=git_executable,
        env=env,
    ).stdout
    uninitialized = 0
    for record in index_entries.split(b"\0"):
        if not record:
            continue
        metadata, separator, path_bytes = record.partition(b"\t")
        if not separator or not metadata.startswith(b"160000 "):
            continue
        path = path_bytes.decode("utf-8", errors="surrogateescape")
        if not os.path.exists(root / path / ".git"):
            uninitialized += 1

    return RepositoryInspection(
        source_repository=origin.canonical_url,
        source_ref=source_ref,
        source_revision=revision.lower(),
        uninitialized_submodules=uninitialized,
        raw_origin=raw_origin,
        source_root=os.fspath(root),
        source_root_realpath=os.path.realpath(root),
    )


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_repository(args.source_root)
    except InspectionError as exc:
        print(f"[inspect_local_repository] ERROR: {exc}", file=sys.stderr)
        return exc.code
    print(f"source_repository: {_json_string(result.source_repository)}")
    print(f"source_ref: {_json_string(result.source_ref)}")
    print(f"source_revision: {_json_string(result.source_revision)}")
    print(f"uninitialized_submodules: {result.uninitialized_submodules}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
