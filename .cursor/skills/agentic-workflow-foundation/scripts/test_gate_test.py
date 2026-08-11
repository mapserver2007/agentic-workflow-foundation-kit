#!/usr/bin/env python3
"""gate-test.py の完了チェック parser / CLI 回帰テスト。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
GATE = ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "gate-test.py"


def _report(
    heading: str = "## 10. 完了チェック",
    items: Optional[List[str]] = None,
    prefix: str = "",
    suffix: str = "",
) -> str:
    lines = items or [
        "- [x] 実装完了",
        "- [x] テスト完了",
        "- [x] コードゲート通過",
    ]
    return f"{prefix}{heading}\n" + "\n".join(lines) + f"\n{suffix}"


def _run(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), str(path), *args],
        capture_output=True,
        text=True,
    )


def _assert_exit(path: Path, expected: int, *args: str) -> subprocess.CompletedProcess:
    result = _run(path, *args)
    assert result.returncode == expected, (
        f"expected exit {expected}, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result


def test_numbered_heading_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "numbered.md"
        path.write_text(_report(), encoding="utf-8")
        _assert_exit(path, 0)


def test_un_numbered_heading_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "plain.md"
        path.write_text(_report("## 完了チェック"), encoding="utf-8")
        _assert_exit(path, 0)


def test_uppercase_checkbox_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "uppercase.md"
        path.write_text(
            _report(
                items=[
                    "- [X] 実装完了",
                    "- [X] テスト完了",
                    "- [X] コードゲート通過",
                ]
            ),
            encoding="utf-8",
        )
        _assert_exit(path, 0)


def test_unchecked_item_fails() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "unchecked.md"
        path.write_text(
            _report(items=["- [ ] 実装完了", "- [x] テスト完了", "- [x] コードゲート通過"]),
            encoding="utf-8",
        )
        _assert_exit(path, 1)


def test_missing_item_fails() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "missing.md"
        path.write_text(
            _report(items=["- [x] 実装完了", "- [x] テスト完了"]),
            encoding="utf-8",
        )
        _assert_exit(path, 1)


def test_missing_heading_is_fatal() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "no-heading.md"
        path.write_text("# Report\n", encoding="utf-8")
        _assert_exit(path, 2)


def test_duplicate_heading_is_fatal() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "duplicate-heading.md"
        path.write_text(
            _report() + "\n## 完了チェック\n",
            encoding="utf-8",
        )
        _assert_exit(path, 2)


def test_items_outside_section_are_ignored() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "outside.md"
        path.write_text(
            "- [x] 実装完了\n"
            "- [x] テスト完了\n"
            "- [x] コードゲート通過\n"
            "## 完了チェック\n"
            "## 次の節\n",
            encoding="utf-8",
        )
        _assert_exit(path, 1)


def test_items_in_next_h2_are_ignored() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "next-h2.md"
        path.write_text(
            "## 完了チェック\n"
            "- [x] 実装完了\n"
            "## 次の節\n"
            "- [x] テスト完了\n"
            "- [x] コードゲート通過\n",
            encoding="utf-8",
        )
        _assert_exit(path, 1)


def test_invalid_paths_and_utf8_are_fatal() -> None:
    with tempfile.TemporaryDirectory() as td:
        directory = Path(td) / "directory"
        directory.mkdir()
        _assert_exit(directory, 2)
        _assert_exit(Path(td) / "missing.md", 2)
        invalid = Path(td) / "invalid.md"
        invalid.write_bytes(b"\xff\xfe")
        _assert_exit(invalid, 2)


def test_human_and_json_have_same_result() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "formats.md"
        path.write_text(_report(), encoding="utf-8")
        human = _assert_exit(path, 0, "--format", "human")
        json_result = _assert_exit(path, 0, "--format=json")
        payload = json.loads(json_result.stdout)
        assert payload["exit_code"] == human.returncode
        assert payload["fatal"] is False
        assert [check["status"] for check in payload["checks"]] == ["PASS"] * 3


def test_template_parenthetical_notes_are_valid() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "notes.md"
        path.write_text(
            _report(
                items=[
                    "- [x] 実装完了",
                    "- [x] テスト完了（G-TEST: foundation）",
                    "- [x] コードゲート通過 (G-BUILD / G-LINT / G-TEST)",
                ]
            ),
            encoding="utf-8",
        )
        _assert_exit(path, 0)


def test_partial_item_name_does_not_pass() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "partial.md"
        path.write_text(
            _report(items=["- [x] 実装完了済み", "- [x] テスト完了", "- [x] コードゲート通過"]),
            encoding="utf-8",
        )
        _assert_exit(path, 1)


def test_duplicate_item_is_fatal_regardless_of_state() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "duplicate-item.md"
        path.write_text(
            _report(
                items=[
                    "- [x] 実装完了",
                    "- [ ] 実装完了",
                    "- [x] テスト完了",
                    "- [x] コードゲート通過",
                ]
            ),
            encoding="utf-8",
        )
        result = _assert_exit(path, 2, "--format=json")
        payload = json.loads(result.stdout)
        checks: Dict[str, Dict[str, object]] = {
            check["id"]: check for check in payload["checks"]
        }
        assert checks["G-TEST-COMP-001"]["status"] == "FATAL"


def test_split_heading_is_fatal() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "split-heading.md"
        path.write_text("##\n完了チェック\n", encoding="utf-8")
        _assert_exit(path, 2)


def main() -> int:
    if not GATE.exists():
        print("SKIP: gate-test.py not found (pre-generate)", file=sys.stderr)
        return 0

    tests = [
        test_numbered_heading_passes,
        test_un_numbered_heading_passes,
        test_uppercase_checkbox_passes,
        test_unchecked_item_fails,
        test_missing_item_fails,
        test_missing_heading_is_fatal,
        test_duplicate_heading_is_fatal,
        test_items_outside_section_are_ignored,
        test_items_in_next_h2_are_ignored,
        test_invalid_paths_and_utf8_are_fatal,
        test_human_and_json_have_same_result,
        test_template_parenthetical_notes_are_valid,
        test_partial_item_name_does_not_pass,
        test_duplicate_item_is_fatal_regardless_of_state,
        test_split_heading_is_fatal,
    ]
    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL: {test.__name__}: {exc}", file=sys.stderr)
            failed += 1
    print(f"[test_gate_test] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
