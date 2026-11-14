#!/usr/bin/env python3
"""root manifest の行単位 YAML ブロック操作の共有ヘルパー。

`apply_kit_init.py` / `ingest_tech_stack.py` / `resolve_*.py` / `run_resolved_engine.py` が
同一実装を個別に持っていたため、ここへ集約する。コメントや空行を保つため YAML を
再シリアライズせず、行のまま範囲を扱う。
"""
from __future__ import annotations


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def yaml_quote(value: object) -> str:
    """値を YAML のダブルクォート文字列にする（`"` を含む値はシングルクォート）。"""
    s = "" if value is None else str(value)
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


def find_top_block(lines: list[str], key: str) -> tuple[int | None, int | None]:
    """インデント0の `key:` 行から、その配下（インデント>0）が続く範囲 (start, last) を返す。

    末尾の空行は範囲に含めない。`key:` が無ければ (None, None)。
    """
    start = None
    for idx, line in enumerate(lines):
        if line.rstrip() == f"{key}:" and indent_of(line) == 0:
            start = idx
            break
    if start is None:
        return None, None
    last = start
    j = start + 1
    while j < len(lines):
        if lines[j].strip() == "":
            j += 1
            continue
        if indent_of(lines[j]) > 0:
            last = j
            j += 1
            continue
        break
    return start, last
