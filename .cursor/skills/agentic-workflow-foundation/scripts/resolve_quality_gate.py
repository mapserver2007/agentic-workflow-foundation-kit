#!/usr/bin/env python3
"""tech_stack から G-* と package script contract を決定する（Phase 1.65）。"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
GENLIB_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if GENLIB_DIR not in sys.path:
    sys.path.insert(0, GENLIB_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import genlib  # noqa: E402
import capability_registry as reg  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")


def _out(level: str, msg: str) -> None:
    print(f"[resolve_quality_gate] {level}: {msg}")


def _yaml_quote(value: str) -> str:
    s = "" if value is None else str(value)
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


def _resolve(manifest: dict):
    status, reason = reg.check_eligibility(manifest)
    if status == "FATAL":
        return "FATAL", reason
    if status == "SKIP":
        return None, reason

    gate_cmds = reg.compose_gate_cmds(manifest)
    if not gate_cmds:
        return None, "パッケージマネージャ capability が不足"

    return {
        "quality_gate": gate_cmds,
        "gate_command": "bin/quality-gate verify",
        "contract": reg.compose_contract(manifest),
    }, None


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_top_block(lines, key: str):
    start = None
    for idx, line in enumerate(lines):
        if line.rstrip() == f"{key}:" and _indent_of(line) == 0:
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
        if _indent_of(lines[j]) > 0:
            last = j
            j += 1
            continue
        break
    return start, last


def _find_nested_block(lines, parent: str, child: str):
    p_start, p_last = _find_top_block(lines, parent)
    if p_start is None:
        return None, None, None
    c_start = None
    for idx in range(p_start + 1, p_last + 1):
        if lines[idx].rstrip() == f"  {child}:":
            c_start = idx
            break
    if c_start is None:
        return p_last + 1, p_last, p_last
    last = c_start
    j = c_start + 1
    while j < len(lines):
        if lines[j].strip() == "":
            j += 1
            continue
        if _indent_of(lines[j]) > 2:
            last = j
            j += 1
            continue
        break
    return c_start, last, p_last


def _replace_nested(lines, parent: str, child: str, block):
    start, last, p_last = _find_nested_block(lines, parent, child)
    if start is None:
        return lines + [f"{parent}:"] + block
    if start > last:
        insert_at = p_last + 1
        return lines[:insert_at] + block + lines[insert_at:]
    return lines[:start] + block + lines[last + 1:]


def _remove_top_block(lines, key: str):
    start, last = _find_top_block(lines, key)
    if start is None:
        return lines
    remove_start = start
    if remove_start > 0 and lines[remove_start - 1].strip() == "":
        remove_start -= 1
    return lines[:remove_start] + lines[last + 1:]


def _quality_gate_block(values):
    return [
        "  quality_gate:",
        f"    gen_cmd: {_yaml_quote(values['gen_cmd'])}",
        f"    build_cmd: {_yaml_quote(values['build_cmd'])}",
        f"    lint_cmd: {_yaml_quote(values['lint_cmd'])}",
        f"    test_cmd: {_yaml_quote(values['test_cmd'])}",
    ]


def _verification_block(gate_command: str):
    return [
        "  verification:",
        f"    gate_command: {_yaml_quote(gate_command)}",
    ]


def _render_manifest(content: str, resolved: dict) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]
    lines = _replace_nested(lines, "project", "quality_gate", _quality_gate_block(resolved["quality_gate"]))
    lines = _replace_nested(lines, "session", "verification", _verification_block(resolved["gate_command"]))
    lines = _remove_top_block(lines, "quality_gate_contract")
    return newline.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="tech_stack から G-* と script contract を決定する")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        _out("ERROR", f"manifest が見つからない: {args.manifest}")
        return 2
    try:
        manifest = genlib.load_manifest(args.manifest)
    except genlib.YamlError as e:
        _out("ERROR", f"manifest 解析失敗: {e}")
        return 2

    resolved, reason = _resolve(manifest)
    if resolved == "FATAL":
        _out("ERROR", reason)
        return 2
    if resolved is None:
        _out("WARN", reason or "G-* を決定できないため既存値を維持")
        return 0

    with open(args.manifest, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = _render_manifest(content, resolved)
    changed = new_content != content
    contract_count = sum(len(v) for v in resolved["contract"].values())

    if args.check:
        _out(
            "INFO",
            f"G-* 解決結果: {resolved['gate_command']} / contract {contract_count} 行（compose のみ・非永続）"
            f" / manifest 書き換え{'あり' if changed else 'なし'}（--check）",
        )
        return 0
    if changed:
        with open(args.manifest, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
    _out(
        "PASS",
        f"G-* を root manifest へ反映（contract {contract_count} 行は compose のみ・非永続）"
        f"（{'更新あり' if changed else '更新なし=冪等'}）",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
