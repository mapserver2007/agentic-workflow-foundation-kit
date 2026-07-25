#!/usr/bin/env python3
"""tech_stack から G-* と package script contract を決定する（Phase 1.65）。"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
GENLIB_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if GENLIB_DIR not in sys.path:
    sys.path.insert(0, GENLIB_DIR)

import genlib  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")

GEN_CONTRACT = [
    "OpenAPI bundle を生成し、bundle 成功を検証する",
    "OpenAPI 由来の型生成、または生成物の再生成差分チェックを実行する",
]

BUILD_CONTRACT = [
    "TypeScript typecheck を実行する",
    "Next.js / OpenNext build を実行する",
    "Hono Worker build を実行する",
]

LINT_CONTRACT = [
    "Redocly lint を実行する",
    "Spectral lint を実行する",
    "TypeScript / ESLint 相当の静的検査を実行する",
]

TEST_CONTRACT = [
    "Vitest を実行する",
    "Cloudflare Workers pool 上のテストを実行する",
    "OpenAPI contract test を実行する",
    "response validation test を実行する",
]


def _out(level: str, msg: str) -> None:
    print(f"[resolve_quality_gate] {level}: {msg}")


def _yaml_quote(value: str) -> str:
    s = "" if value is None else str(value)
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


def _normalize(value: str) -> str:
    text = (value or "").replace("`", "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _tech_names(manifest: dict) -> set[str]:
    items = (manifest.get("tech_stack") or {}).get("items") or []
    names = set()
    for item in items:
        if isinstance(item, dict):
            names.add(_normalize(item.get("technology", "")))
    return names


def _has(names: set[str], needle: str) -> bool:
    n = _normalize(needle)
    return any(n in name for name in names)


def _resolve(manifest: dict):
    pattern = str((manifest.get("project") or {}).get("workflow_pattern") or "")
    names = _tech_names(manifest)
    if pattern != "開発型":
        return "FATAL", f"workflow_pattern が開発型でない: {pattern!r}（開発型専用）"
    required = ["pnpm", "next.js", "hono", "typescript", "cloudflare workers"]
    missing = [name for name in required if not _has(names, name)]
    if missing:
        return None, f"開発型 G-* 決定に必要な技術が不足: {', '.join(missing)}"

    has_openapi = _has(names, "openapi") and _has(names, "redocly") and _has(names, "spectral")
    has_workers_test = _has(names, "vitest") and _has(names, "cloudflare")
    if not has_openapi:
        return None, "OpenAPI / Redocly / Spectral が揃っていないため G-LINT contract を決定できない"
    if not has_workers_test:
        return None, "Vitest / Cloudflare Workers pool が揃っていないため G-TEST contract を決定できない"

    return {
        "quality_gate": {
            "gen_cmd": "pnpm run gen",
            "build_cmd": "pnpm run build",
            "lint_cmd": "pnpm run lint",
            "test_cmd": "pnpm run test",
        },
        "gate_command": "bin/quality-gate verify",
        "contract": {
            "gen": GEN_CONTRACT,
            "build": BUILD_CONTRACT,
            "lint": LINT_CONTRACT,
            "test": TEST_CONTRACT,
        },
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


def _contract_block(contract):
    lines = ["quality_gate_contract:"]
    for key in ("gen", "build", "lint", "test"):
        lines.append(f"  {key}:")
        for item in contract[key]:
            lines.append(f"    - {_yaml_quote(item)}")
    return lines


def _replace_nested(lines, parent: str, child: str, block):
    start, last, p_last = _find_nested_block(lines, parent, child)
    if start is None:
        return lines + [f"{parent}:"] + block
    if start > last:
        insert_at = p_last + 1
        return lines[:insert_at] + block + lines[insert_at:]
    return lines[:start] + block + lines[last + 1:]


def _replace_top(lines, key: str, block, after_key: str | None = None):
    start, last = _find_top_block(lines, key)
    if start is not None:
        return lines[:start] + block + lines[last + 1:]
    if after_key:
        a_start, a_last = _find_top_block(lines, after_key)
        if a_start is not None:
            insert_at = a_last + 1
            return lines[:insert_at] + [""] + block + lines[insert_at:]
    return lines + [""] + block


def _render_manifest(content: str, resolved: dict) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]
    lines = _replace_nested(lines, "project", "quality_gate", _quality_gate_block(resolved["quality_gate"]))
    lines = _replace_nested(lines, "session", "verification", _verification_block(resolved["gate_command"]))
    lines = _replace_top(lines, "quality_gate_contract", _contract_block(resolved["contract"]), after_key="session")
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

    if args.check:
        _out("INFO", f"G-* 解決結果: {resolved['gate_command']} / 書き換え{'あり' if changed else 'なし'}（--check）")
        return 0
    if changed:
        with open(args.manifest, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
    _out("PASS", f"G-* と script contract を root manifest へ反映（{'更新あり' if changed else '更新なし=冪等'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
