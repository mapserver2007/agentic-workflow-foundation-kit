#!/usr/bin/env python3
"""agentic-workflow-update のhost個人スキル配置を一元化する。"""
from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import tempfile
from pathlib import Path


class HostInstallError(RuntimeError):
    """host updaterの配置契約違反またはI/O失敗。"""


class HostInstallResult:
    """配置結果。backup はトランザクション成功まで残す旧ツリー。"""

    def __init__(self, destination: Path, backup: Path | None) -> None:
        self.destination = destination
        self.backup = backup
        self.committed = False


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _validate_source(source: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise HostInstallError(
            f"updater正本が通常ディレクトリではありません: {source}"
        )
    symlinks = [path.relative_to(source) for path in source.rglob("*") if path.is_symlink()]
    if symlinks:
        raise HostInstallError(
            f"updater正本にsymlinkが含まれています: {symlinks[0]}"
        )
    if not (source / "SKILL.md").is_file():
        raise HostInstallError("updater SKILL.mdがありません")


def stage_host_updater(source: Path, base: Path) -> HostInstallResult:
    """source treeを配置し、旧ツリーの退避は削除せずに返す。"""
    if source.is_symlink():
        raise HostInstallError(f"updater正本がsymlinkです: {source}")
    source = source.resolve()
    base = Path(base).expanduser()
    if base.is_symlink():
        raise HostInstallError(f"個人スキル配置先がsymlinkです: {base}")
    base = base.resolve()
    _validate_source(source)
    destination = base / "agentic-workflow-update"
    try:
        base.mkdir(parents=True, exist_ok=True)
        staging_parent = Path(
            tempfile.mkdtemp(prefix=".agentic-workflow-update.", dir=base)
        )
    except OSError as exc:
        raise HostInstallError(f"個人スキル配置先を準備できません: {exc}") from exc

    staged = staging_parent / "agentic-workflow-update"
    backup = base / f".agentic-workflow-update.previous.{os.getpid()}"
    try:
        shutil.copytree(
            source,
            staged,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        _validate_source(staged)
        if backup.exists() or backup.is_symlink():
            raise HostInstallError("updater退避先が既に存在します")
        if destination.exists() or destination.is_symlink():
            os.replace(destination, backup)
        try:
            os.replace(staged, destination)
        except OSError:
            if backup.exists() or backup.is_symlink():
                os.replace(backup, destination)
            raise
        retained = backup if backup.exists() or backup.is_symlink() else None
        return HostInstallResult(destination, retained)
    except HostInstallError:
        raise
    except OSError as exc:
        raise HostInstallError(f"個人updater更新に失敗しました: {exc}") from exc
    finally:
        _remove(staging_parent)


def commit_host_updater(result: HostInstallResult) -> None:
    """トランザクション成功後に旧ツリーの退避を削除する。"""
    backup = result.backup
    if backup is not None and (backup.exists() or backup.is_symlink()):
        _remove(backup)
    result.committed = True


def restore_host_updater(result: HostInstallResult) -> None:
    """配置前の host ツリーへ戻す。退避が無い初回配置は配置先を削除する。"""
    if result.committed:
        return
    destination = result.destination
    backup = result.backup
    owned_discard: Path | None = None
    try:
        if backup is not None and (backup.exists() or backup.is_symlink()):
            discarded = destination.parent / f".agentic-workflow-update.discard.{os.getpid()}"
            if discarded.exists() or discarded.is_symlink():
                raise HostInstallError("updater復元の退避先が既に存在します")
            if destination.exists() or destination.is_symlink():
                os.replace(destination, discarded)
                owned_discard = discarded
            os.replace(backup, destination)
            return
        if destination.exists() or destination.is_symlink():
            _remove(destination)
    except HostInstallError:
        raise
    except OSError as exc:
        raise HostInstallError(f"個人updaterの復元に失敗しました: {exc}") from exc
    finally:
        if owned_discard is not None and (owned_discard.exists() or owned_discard.is_symlink()):
            _remove(owned_discard)


@contextlib.contextmanager
def host_install_lock(base: Path):
    """host skill home をアプリ横断で直列化する。同一 flock は入れ子にしない。"""
    base = Path(base).expanduser()
    if base.is_symlink():
        raise HostInstallError(f"個人スキル配置先がsymlinkです: {base}")
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HostInstallError(f"個人スキル配置先を準備できません: {exc}") from exc
    lock_path = base / ".agentic-workflow-update.lock"
    if lock_path.is_symlink():
        raise HostInstallError(f"host lock がsymlinkです: {lock_path}")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise HostInstallError(f"host lock を安全に開けません: {lock_path}") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def install_host_updater(source: Path, base: Path) -> Path:
    """source treeをbase/agentic-workflow-updateへ原子的に配置する。"""
    with host_install_lock(base):
        result = stage_host_updater(source, base)
        commit_host_updater(result)
    return result.destination
