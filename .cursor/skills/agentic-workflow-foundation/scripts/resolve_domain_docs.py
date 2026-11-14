#!/usr/bin/env python3
"""承認済み tech_contract の Domain docs 構造を generic に投影する。"""
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
SCALAR_KEYS = ("primary_language", "api_style", "database", "architecture", "framework", "test_framework", "package_manager")
SECTION_KEYS = ("spec_sections", "architecture_sections", "api_sections", "data_model_sections", "coding_standards_sections", "workflow_sections")


def _out(level: str, message: str) -> None:
    print(f"[resolve_domain_docs] {level}: {message}")


def _resolve(manifest_path: str) -> dict:
    path = Path(manifest_path)
    design_doc = tc.resolve_design_doc(path)
    contract = tc.load_approved(path, design_doc)
    resolved = (contract.get("domain_docs") or {}).get("resolved")
    if not isinstance(resolved, dict):
        raise ValueError("tech_contract.domain_docs.resolved がありません")
    required = set(SCALAR_KEYS + SECTION_KEYS)
    if not required.issubset(resolved):
        raise ValueError("tech_contract.domain_docs.resolved が完全ではありません。fallback は許可されません")
    for key in SCALAR_KEYS:
        if not isinstance(resolved[key], str) or not resolved[key]:
            raise ValueError(f"tech_contract.domain_docs.resolved.{key} が不正です")
    for key in SECTION_KEYS:
        if not isinstance(resolved[key], list) or not all(
            isinstance(item, dict) and isinstance(item.get("title"), str)
            for item in resolved[key]
        ):
            raise ValueError(f"tech_contract.domain_docs.resolved.{key} が不正です")
    return resolved


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_top_block(lines: list[str], key: str) -> tuple[int | None, int | None]:
    start = next((index for index, line in enumerate(lines) if line.rstrip() == f"{key}:" and _indent_of(line) == 0), None)
    if start is None:
        return None, None
    end = start
    for index in range(start + 1, len(lines)):
        if lines[index].strip() and _indent_of(lines[index]) == 0:
            break
        end = index
    return start, end


def _domain_docs_block(resolved: dict) -> list[str]:
    return dump_yaml({"domain_docs": resolved})


def _render_manifest(content: str, resolved: dict) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [line.rstrip("\r") for line in content.split("\n")]
    start, end = _find_top_block(lines, "domain_docs")
    block = _domain_docs_block(resolved)
    return newline.join(lines[:start] + block + lines[end + 1:] if start is not None else lines + [""] + block)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="tech_contract から Domain docs を投影する")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not os.path.exists(args.manifest):
        _out("ERROR", f"manifest が見つからない: {args.manifest}")
        return 2
    try:
        resolved = _resolve(args.manifest)
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
    except genlib.YamlError as exc:
        _out("ERROR", str(exc))
        return 2
    with open(args.manifest, encoding="utf-8") as handle:
        content = handle.read()
    rendered = _render_manifest(content, resolved)
    try:
        projected = genlib.parse_yaml(rendered).get("domain_docs")
        if projected != resolved:
            raise tc.SchemaError("Domain docs 投影後の YAML round-trip が契約値と一致しません")
    except (genlib.YamlError, tc.SchemaError, OSError) as exc:
        _out("ERROR", str(exc))
        return 2
    if args.check:
        _out("INFO", f"domain_docs 解決結果: 書き換え{'あり' if rendered != content else 'なし'}（--check）")
        return 0
    if rendered != content:
        try:
            rp._atomic_write_bytes(Path(args.manifest), rendered.encode("utf-8"))
        except OSError as exc:
            _out("ERROR", f"manifest 書き込み失敗: {exc}")
            return 2
    _out("PASS", "contract.domain_docs を root manifest へ投影")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
