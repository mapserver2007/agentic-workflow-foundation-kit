#!/usr/bin/env python3
"""承認済み tech_contract の CodeRabbit 設定を投影する（Phase 1.66）。

tech_contract.review.coderabbit を技術名推論なしで root manifest.yaml の
coderabbit セクションへ投影する。stale・未承認・digest 不一致の契約は拒否する。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
GENLIB_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if GENLIB_DIR not in sys.path:
    sys.path.insert(0, GENLIB_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import genlib  # noqa: E402
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from yaml_emitter import dump_yaml  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")

def _out(level: str, msg: str) -> None:
    print(f"[resolve_coderabbit] {level}: {msg}")


def resolve(manifest_path: str) -> dict:
    path = Path(manifest_path)
    design_doc = tc.resolve_design_doc(path)
    contract = tc.load_approved(path, design_doc)
    review_contract = (contract.get("review") or {}).get("coderabbit")
    if isinstance(review_contract, dict):
        required = {"enabled", "language", "tools_enabled", "tools_disabled", "path_filters", "path_instructions"}
        if required.issubset(review_contract):
            return dict(review_contract)
    raise tc.SchemaError("tech_contract.review.coderabbit が完全ではありません")


# ── manifest 書き込み ────────────────────────────────────────

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


def _build_coderabbit_block(resolved: dict) -> list[str]:
    return dump_yaml({"coderabbit": resolved})


def _render_manifest(content: str, resolved: dict) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]
    block = _build_coderabbit_block(resolved)

    start, last = _find_top_block(lines, "coderabbit")
    if start is not None:
        new_lines = lines[:start] + block + lines[last + 1:]
    else:
        after_key = "domain_docs"
        a_start, a_last = _find_top_block(lines, after_key)
        if a_start is not None:
            insert_at = a_last + 1
            new_lines = lines[:insert_at] + [""] + block + lines[insert_at:]
        else:
            new_lines = lines + [""] + block

    return newline.join(new_lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="承認済み tech_contract から CodeRabbit 設定を投影する"
    )
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

    try:
        resolved = resolve(args.manifest)
    except tc.ContractError as exc:
        _out("ERROR", str(exc))
        return 1
    except (
        tc.SchemaError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
        AttributeError,
        OSError,
        re.error,
    ) as exc:
        _out("ERROR", str(exc))
        return 2
    with open(args.manifest, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = _render_manifest(content, resolved)
    changed = new_content != content
    try:
        projected = genlib.parse_yaml(new_content).get("coderabbit")
        if projected != resolved:
            raise tc.SchemaError("CodeRabbit 投影後の YAML round-trip が契約値と一致しません")
    except (genlib.YamlError, tc.SchemaError, OSError) as exc:
        _out("ERROR", str(exc))
        return 2

    if args.check:
        _out("INFO", f"CodeRabbit 設定解決結果: 書き換え{'あり' if changed else 'なし'}（--check）")
        return 0
    if changed:
        try:
            rp._atomic_write_bytes(Path(args.manifest), new_content.encode("utf-8"))
        except OSError as exc:
            _out("ERROR", f"manifest 書き込み失敗: {exc}")
            return 2
    _out("PASS", f"CodeRabbit 設定を root manifest へ反映（{'更新あり' if changed else '更新なし=冪等'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
