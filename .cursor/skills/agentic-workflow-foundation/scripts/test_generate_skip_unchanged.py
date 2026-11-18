#!/usr/bin/env python3
"""生成エンジンの未変更出力スキップと権限拒否処理を検査する。"""
from __future__ import annotations

import contextlib
import errno
import io
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ENGINE_SCRIPTS = HERE.parents[1] / "agentic-workflow-engine" / "scripts"
if str(ENGINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ENGINE_SCRIPTS))

import generate  # noqa: E402


MANIFEST = """\
marker_id: test-generator
outputs:
  - path: generated-a.txt
    template: a.template
    mode: render
    executable: true
  - path: generated-b.txt
    template: b.template
    mode: render
  - path: seed.md
    template: seed.template
    mode: seed
"""


def _make_skill(root: Path, manifest: str = MANIFEST) -> Path:
    skill_dir = root / ".cursor" / "skills" / "test-skill"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "templates").mkdir()
    (skill_dir / "manifest.yaml").write_text(manifest, encoding="utf-8")
    (skill_dir / "templates" / "a.template").write_text("alpha\n", encoding="utf-8")
    (skill_dir / "templates" / "b.template").write_text("bravo\n", encoding="utf-8")
    (skill_dir / "templates" / "seed.template").write_text("seed-v1\n", encoding="utf-8")
    return skill_dir


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_skip_unchanged_and_seed() -> None:
    with tempfile.TemporaryDirectory(prefix="generate-skip-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_skill(root)

        _assert(generate.run(str(skill_dir), check=False) == 0, "initial generation failed")
        output_a = root / "generated-a.txt"
        output_b = root / "generated-b.txt"
        seed = root / "seed.md"
        _assert(output_a.read_text(encoding="utf-8") == "alpha\n", "render output A mismatch")
        _assert(output_b.read_text(encoding="utf-8") == "bravo\n", "render output B mismatch")
        _assert(seed.read_text(encoding="utf-8") == "seed-v1\n", "seed output mismatch")

        past = 1_000_000_000
        for path in (output_a, output_b, seed):
            os.utime(path, (past, past))
        before = {path: path.stat() for path in (output_a, output_b, seed)}

        _assert(generate.run(str(skill_dir), check=False) == 0, "unchanged generation failed")
        for path in (output_a, output_b, seed):
            after = path.stat()
            _assert(after.st_mtime_ns == before[path].st_mtime_ns, f"mtime changed: {path}")
            _assert(after.st_size == before[path].st_size, f"size changed: {path}")

        (skill_dir / "templates" / "b.template").write_text("bravo-v2\n", encoding="utf-8")
        _assert(generate.run(str(skill_dir), check=False) == 0, "changed generation failed")
        _assert(output_b.read_text(encoding="utf-8") == "bravo-v2\n", "changed output B mismatch")
        _assert(output_b.stat().st_mtime_ns > past, "changed output B was not rewritten")
        _assert(output_a.stat().st_mtime_ns == before[output_a].st_mtime_ns, "output A was rewritten")

        (skill_dir / "templates" / "seed.template").write_text("seed-v2\n", encoding="utf-8")
        _assert(generate.run(str(skill_dir), check=False) == 0, "existing seed generation failed")
        _assert(seed.read_text(encoding="utf-8") == "seed-v1\n", "existing seed was overwritten")
        _assert(seed.stat().st_mtime_ns == before[seed].st_mtime_ns, "existing seed mtime changed")


def test_executable_bits_and_check_are_non_mutating() -> None:
    with tempfile.TemporaryDirectory(prefix="generate-mode-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_skill(root)
        _assert(generate.run(str(skill_dir), check=False) == 0, "initial mode generation failed")
        output_a = root / "generated-a.txt"

        content_before = output_a.read_bytes()
        mode_without_user = output_a.stat().st_mode & ~stat.S_IXUSR
        output_a.chmod(mode_without_user)
        before_check = output_a.stat()
        _assert(generate.run(str(skill_dir), check=True) == 0, "check with mode drift failed")
        after_check = output_a.stat()
        _assert(output_a.read_bytes() == content_before, "check changed executable content")
        _assert(after_check.st_mtime_ns == before_check.st_mtime_ns, "check changed mtime")
        _assert(
            after_check.st_mode & generate.EXECUTABLE_BITS == mode_without_user & generate.EXECUTABLE_BITS,
            "check changed executable mode",
        )

        _assert(generate.run(str(skill_dir), check=False) == 0, "mode repair failed")
        repaired = output_a.stat().st_mode
        _assert(repaired & generate.EXECUTABLE_BITS == generate.EXECUTABLE_BITS, "mode was not repaired")
        _assert(output_a.read_bytes() == content_before, "mode repair rewrote content")


def test_merge_seed_sections_boundaries() -> None:
    merge = generate.merge_seed_sections

    # 空の構造節: 投影なしと投影ありが同じなら置換しない。手編集は保持する。
    merged, replaced = merge("## A\nmine\n## B\ntext\n", "## A\n## B\ntext\n", "## A\n## B\nproj\n")
    _assert(merged == "## A\nmine\n## B\nproj\n" and replaced == ["## B"], f"empty section: {merged!r}")

    # 末尾改行なし。
    merged, replaced = merge("## A\nmine\n## B\ntext", "## A\n\n## B\ntext", "## A\n\n## B\nproj")
    _assert(merged == "## A\nmine\n## B\nproj", f"no trailing newline: {merged!r}")

    # 構造見出しの重複は出現順に対応づける。
    merged, replaced = merge(
        "## X\nmine\n## X\nb\n", "## X\na\n## X\nb\n", "## X\na\n## X\nB!\n"
    )
    _assert(merged == "## X\nmine\n## X\nB!\n" and replaced == ["## X"], f"duplicate headings: {merged!r}")

    # CRLF は正規化せず、一致しない節は保持する。
    crlf = "## A\r\nmine\r\n## B\r\ntext\r\n"
    merged, replaced = merge(crlf, "## A\n## B\ntext\n", "## A\n## B\nproj\n")
    _assert(merged == crlf and replaced == [], f"CRLF must be preserved: {merged!r}")

    # コードフェンス内の `## ` は境界にならない。
    fenced = "## A\n```text\n## not a heading\n```\n## B\ntext\n"
    _assert(generate.structural_headings(fenced) == ["## A", "## B"], "fenced heading counted")
    merged, replaced = merge(fenced, "## A\n```text\n## not a heading\n```\n## B\ntext\n", "## A\n```text\n## not a heading\n```\n## B\nproj\n")
    _assert(merged.endswith("## B\nproj\n") and replaced == ["## B"], f"fenced merge: {merged!r}")

    # 前文は常に保持する。
    merged, _ = merge("hand\n## A\n## B\ntext\n", "pre\n## A\n## B\ntext\n", "pre\n## A\n## B\nproj\n")
    _assert(merged == "hand\n## A\n## B\nproj\n", f"preamble: {merged!r}")

    # 既存ファイルに構造見出しが無ければ SectionMismatch。
    try:
        merge("## A\nmine\n", "## A\n## B\ntext\n", "## A\n## B\nproj\n")
    except generate.SectionMismatch as exc:
        _assert(exc.heading == "## B", "wrong mismatch heading")
    else:
        raise AssertionError("missing structural heading accepted")


def test_merge_rejects_projected_duplicate_heading() -> None:
    """投影本文が構造見出しと同名の `##` を含むと、境界を誤認せず不一致として拒否する。"""
    merge = generate.merge_seed_sections
    pristine = "## エラー\n\nTODO\n\n## 参照\n\n- a\n"
    expected = "## エラー\n\nP1\n\n## 参照\n\nP2-remainder\n\n## 参照\n\n- a\n"
    existing = "## エラー\n\nTODO\n\n## 参照\n\n- hand edited\n"
    try:
        merged, _ = merge(existing, pristine, expected)
    except generate.SectionMismatch as exc:
        _assert(exc.heading == "## 参照", f"wrong mismatch heading: {exc.heading!r}")
    else:
        raise AssertionError(f"projected duplicate heading accepted: {merged!r}")


def test_permission_errors_are_aggregated() -> None:
    manifest = """\
marker_id: permission-test
outputs:
  - path: denied-write.txt
    template: denied-write.template
    mode: render
  - path: denied-chmod.txt
    template: denied-chmod.template
    mode: render
    executable: true
  - path: success.txt
    template: success.template
    mode: render
"""
    with tempfile.TemporaryDirectory(prefix="generate-permission-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_skill(root, manifest)
        (skill_dir / "templates" / "denied-write.template").write_text("write\n", encoding="utf-8")
        (skill_dir / "templates" / "denied-chmod.template").write_text("chmod\n", encoding="utf-8")
        (skill_dir / "templates" / "success.template").write_text("success\n", encoding="utf-8")
        denied_chmod = root / "denied-chmod.txt"
        denied_chmod.write_text("chmod\n", encoding="utf-8")
        denied_chmod.chmod(0o644)

        original_write = generate._write
        original_chmod = os.chmod
        denied_write = root / "denied-write.txt"

        def injected_write(path: str, content: str, executable: bool) -> None:
            if path == str(denied_write):
                raise PermissionError(errno.EPERM, "write denied")
            original_write(path, content, executable)

        def injected_chmod(path: str, mode: int) -> None:
            if path == str(denied_chmod):
                raise PermissionError(errno.EIO, "chmod denied")
            original_chmod(path, mode)

        stderr = io.StringIO()
        with (
            patch.object(generate, "_write", side_effect=injected_write),
            patch.object(generate.os, "chmod", side_effect=injected_chmod),
            contextlib.redirect_stderr(stderr),
        ):
            result = generate.run(str(skill_dir), check=False)

        _assert(result == 2, "permission errors must return exit 2")
        error_text = stderr.getvalue()
        _assert("denied-write.txt" in error_text, "write denial path missing from stderr")
        _assert("denied-chmod.txt" in error_text, "chmod denial path missing from stderr")
        _assert((root / "success.txt").is_file(), "generation did not continue after denial")


def test_symlink_output_is_rejected_before_write() -> None:
    with tempfile.TemporaryDirectory(prefix="generate-symlink-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_skill(root)
        outside = Path(temp_dir) / "outside.txt"
        outside.write_text("original\n", encoding="utf-8")
        output = root / "generated-a.txt"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.symlink_to(outside)

        _assert(generate.run(str(skill_dir), check=False) == 2, "symlink output must fail")
        _assert(outside.read_text(encoding="utf-8") == "original\n", "symlink target was changed")
        _assert(output.is_symlink(), "symlink was unexpectedly replaced")


def main() -> int:
    tests = (
        ("skip unchanged and seed", test_skip_unchanged_and_seed),
        ("executable bits and check", test_executable_bits_and_check_are_non_mutating),
        ("merge seed sections boundaries", test_merge_seed_sections_boundaries),
        ("merge rejects projected duplicate heading", test_merge_rejects_projected_duplicate_heading),
        ("permission error aggregation", test_permission_errors_are_aggregated),
        ("symlink output rejection", test_symlink_output_is_rejected_before_write),
    )
    for label, test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_generate_skip_unchanged] FAIL: {label}: {exc}", file=sys.stderr)
            return 1
        print(f"[test_generate_skip_unchanged] PASS: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
