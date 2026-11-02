#!/usr/bin/env python3
"""検証済み候補を workspace 直下 gen の規約パスへ symlink-safe に原子的公開する。"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import secrets
import stat
import sys
from pathlib import Path
from typing import Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from validate_design_doc import ValidationError, review_counts, validate_bytes  # noqa: E402


OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+-\d{14}$")


def output_directory_name(source_repository: str, published_at: datetime.datetime) -> str:
    """出力ディレクトリ名 `<repository>-<yyyyMMddHHmmss>` を作る。時刻は24時間制。"""
    repository = source_repository.rstrip("/").rsplit("/", 1)[-1]
    if repository.endswith(".git"):
        repository = repository[:-4]
    name = f"{repository}-{published_at.strftime('%Y%m%d%H%M%S')}"
    if not OUTPUT_NAME_RE.fullmatch(name):
        raise PublishError("repository 名から安全な出力ディレクトリを作れません", 2)
    return name


class PublishError(Exception):
    """公開失敗。code は CLI の exit code に対応する。"""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def _default_workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _inspect_existing_path(path: Path, label: str, *, require_directory: bool) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise PublishError(f"{label} を検査できません", 2) from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise PublishError(f"{label} に symlink は使用できません", 2)
    expected = stat.S_ISDIR(metadata.st_mode) if require_directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        kind = "ディレクトリ" if require_directory else "通常ファイル"
        raise PublishError(f"{label} は {kind} 必須です", 2)
    return True


def _validate_output_chain(workspace: Path, output_dir: Path, output: Path) -> None:
    if not _inspect_existing_path(workspace, "workspace root", require_directory=True):
        raise PublishError("workspace root が存在しません", 2)
    current = workspace
    for name, label in (
        ("gen", "workspace/gen"),
        (output_dir.name, "出力ディレクトリ"),
    ):
        current = current / name
        if not _inspect_existing_path(current, label, require_directory=True):
            break
    _inspect_existing_path(output, "出力ファイル", require_directory=False)


def _snapshot_candidate(candidate: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise PublishError("候補ファイルを no-follow で開けません", 2) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
            raise PublishError("候補は symlink でない通常ファイル必須です", 2)
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        stable_fields_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        stable_fields_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        data = b"".join(chunks)
        if stable_fields_before != stable_fields_after or after.st_nlink < 1 or len(data) != after.st_size:
            raise PublishError("候補ファイルが読み取り中に変更されました", 2)
        return data
    except OSError as exc:
        raise PublishError("候補ファイルの snapshot 読み取りに失敗しました", 2) from exc
    finally:
        os.close(descriptor)


def _open_directory(parent_fd: int, name: str, label: str) -> int:
    try:
        os.mkdir(name, dir_fd=parent_fd)
    except FileExistsError:
        pass
    except OSError as exc:
        raise PublishError(f"{label} を作成できません", 2) from exc
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise PublishError(f"{label} を no-follow で開けません", 2) from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise PublishError(f"{label} はディレクトリ必須です", 2)
    return descriptor


def _output_metadata(output_fd: int, output_name: str) -> os.stat_result | None:
    try:
        metadata = os.stat(output_name, dir_fd=output_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PublishError("出力ファイルを検査できません", 2) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise PublishError("出力ファイルは symlink でない通常ファイル必須です", 2)
    return metadata


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _publish_snapshot(
    workspace: Path,
    output_dir_name: str,
    output_name: str,
    data: bytes,
    *,
    approve_overwrite: bool,
) -> None:
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        workspace_fd = os.open(workspace, root_flags)
    except OSError as exc:
        raise PublishError("workspace root を no-follow で開けません", 2) from exc
    descriptors = [workspace_fd]
    temporary_name = ""
    try:
        gen_fd = _open_directory(workspace_fd, "gen", "workspace/gen")
        descriptors.append(gen_fd)
        output_fd = _open_directory(gen_fd, output_dir_name, "出力ディレクトリ")
        descriptors.append(output_fd)

        existing = _output_metadata(output_fd, output_name)
        if existing is not None and not approve_overwrite:
            raise PublishError("既存成果物の上書きが承認されていません", 1)

        temporary_name = f".TECHNOLOGY_STACK_UNIFIED_DESIGN.{secrets.token_hex(12)}.tmp"
        temp_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            temporary_fd = os.open(temporary_name, temp_flags, 0o600, dir_fd=output_fd)
            try:
                _write_all(temporary_fd, data)
                os.fsync(temporary_fd)
            finally:
                os.close(temporary_fd)
            if approve_overwrite:
                _output_metadata(output_fd, output_name)
                os.replace(
                    temporary_name,
                    output_name,
                    src_dir_fd=output_fd,
                    dst_dir_fd=output_fd,
                )
                temporary_name = ""
            else:
                try:
                    os.link(
                        temporary_name,
                        output_name,
                        src_dir_fd=output_fd,
                        dst_dir_fd=output_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as exc:
                    raise PublishError("出力先が同時に作成されたため公開しません", 1) from exc
                try:
                    os.unlink(temporary_name, dir_fd=output_fd)
                except OSError:
                    # create-if-absent 自体は完了済み。cleanup 失敗を公開失敗にしない。
                    pass
                else:
                    temporary_name = ""
        except PublishError:
            raise
        except OSError as exc:
            raise PublishError("atomic publish に失敗しました", 2) from exc
    finally:
        if temporary_name and len(descriptors) == 3:
            try:
                os.unlink(temporary_name, dir_fd=descriptors[-1])
            except OSError:
                pass
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def publish_document(
    candidate_path: str,
    source_root: str,
    *,
    workspace_root: str | None = None,
    approve_overwrite: bool = False,
    survey_dir: str | None = None,
    quality: bool = True,
    published_at: datetime.datetime | None = None,
) -> Path:
    workspace_input = Path(workspace_root) if workspace_root is not None else _default_workspace_root()
    if not workspace_input.is_absolute() or ".." in workspace_input.parts:
        raise PublishError("workspace root は絶対パス必須です", 2)
    workspace = Path(os.path.abspath(workspace_input))
    candidate = Path(candidate_path)

    gen_root = workspace / "gen"
    if not _inspect_existing_path(workspace, "workspace root", require_directory=True):
        raise PublishError("workspace root が存在しません", 2)
    workspace_real = Path(os.path.realpath(workspace))
    candidate_real = Path(os.path.realpath(candidate))
    gen_root_real = Path(os.path.realpath(gen_root))
    if _is_relative_to(candidate_real, gen_root_real):
        raise PublishError("gen 配下の候補は公開できません", 2)

    data = _snapshot_candidate(candidate)
    try:
        validation = validate_bytes(
            data,
            source_root=source_root,
            syntax_only=False,
            quality=quality,
            survey_dir=survey_dir,
        )
    except ValidationError as exc:
        raise PublishError(str(exc), exc.code) from exc
    if validation.inspection is None:
        raise PublishError("publish では来歴再検証が必須です", 2)

    output_dir = gen_root / output_directory_name(
        validation.inspection.source_repository,
        published_at or datetime.datetime.now(),
    )
    output = output_dir / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
    if os.path.commonpath((os.fspath(workspace), os.fspath(output))) != os.fspath(workspace):
        raise PublishError("出力先が workspace 外です", 2)
    _validate_output_chain(workspace, output_dir, output)
    output_parent_real = Path(os.path.realpath(output_dir))
    if not _is_relative_to(output_parent_real, workspace_real):
        raise PublishError("出力先が workspace 外へ解決されます", 2)

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PublishError("候補は UTF-8 必須です", 2) from exc
    declaration_count, confirmation_count, none_count, evidence_count = review_counts(text)
    _publish_snapshot(
        workspace,
        output_dir.name,
        output.name,
        data,
        approve_overwrite=approve_overwrite,
    )
    print(
        "[publish_design_doc] REVIEW: "
        f"宣言={declaration_count} [要確認]={confirmation_count} "
        f"該当なし={none_count} evidence={evidence_count}"
    )
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        default="tmp/tech-stack-reverse-candidate.md",
    )
    parser.add_argument("--source-root", required=True)
    parser.add_argument(
        "--survey-dir",
        default="tmp/tech-stack-survey",
        help="survey_repository.py survey の出力先。全量読解の台帳と調査範囲行を再検証する",
    )
    parser.add_argument("--workspace-root")
    parser.add_argument("--approve-overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = publish_document(
            args.candidate,
            args.source_root,
            workspace_root=args.workspace_root,
            approve_overwrite=args.approve_overwrite,
            survey_dir=args.survey_dir,
        )
    except PublishError as exc:
        print(f"[publish_design_doc] ERROR: {exc}", file=sys.stderr)
        return exc.code
    workspace = Path(args.workspace_root) if args.workspace_root else _default_workspace_root()
    print(f"[publish_design_doc] PASS: {output.relative_to(Path(os.path.abspath(workspace)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
