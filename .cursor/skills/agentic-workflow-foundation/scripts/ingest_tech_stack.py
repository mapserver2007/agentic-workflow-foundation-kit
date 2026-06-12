#!/usr/bin/env python3
"""techstack 設計書 §9 を生成済み root manifest.yaml の tech_stack へ取り込む（Phase 1.6）。"""
from __future__ import annotations

import argparse
import json
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

DEFAULT_DESIGN_DOC = os.path.join(ROOT, ".cursor", "docs", "TECHNOLOGY_STACK_UNIFIED_DESIGN.md")
DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")
DEFAULT_PACKAGE_JSON = os.path.join(ROOT, "package.json")

NAME_MAP = {
    "next.js": "next",
    "@opennextjs/cloudflare": "@opennextjs/cloudflare",
    "hono": "hono",
    "wrangler": "wrangler",
    "typescript": "typescript",
    "vitest": "vitest",
    "turborepo": "turbo",
    "spectral": "@stoplight/spectral-cli",
    "redocly cli": "@redocly/cli",
    "openapi-typescript": "openapi-typescript",
    "openapi-fetch": "openapi-fetch",
    "openapi-react-query": "openapi-react-query",
    "orval": "orval",
    "prism": "@stoplight/prism-cli",
    "pnpm": "__packageManager__",
}


def warn(msg: str) -> None:
    print(f"[ingest_tech_stack] WARN: {msg}")


def info(msg: str) -> None:
    print(f"[ingest_tech_stack] {msg}")


def _split_row(line: str):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_section9(text: str):
    lines = text.split("\n")
    start = None
    for idx, line in enumerate(lines):
        if re.match(r"^###\s+9\.", line.strip()):
            start = idx
            break
    if start is None:
        return None, []

    note = None
    items = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if re.match(r"^###\s+\d", stripped) or stripped == "---":
            if items:
                break
            if stripped == "---":
                continue
            break
        if note is None and stripped.startswith(">"):
            raw = stripped.lstrip(">").strip()
            raw = re.sub(r"^\*\*[^*]+\*\*[:：]\s*", "", raw)
            raw = raw.replace("**", "").replace("`", "")
            raw = re.sub(r"(?<=[^\x00-\x7F]) (?=[^\x00-\x7F])", "", raw)
            if raw.strip():
                note = raw.strip()
            continue
        if stripped.startswith("|"):
            cells = _split_row(stripped)
            if len(cells) < 4:
                continue
            if "レイヤ" in cells[0] or set(cells[0]) <= set("-: "):
                continue
            items.append({
                "layer": cells[0],
                "technology": cells[1],
                "version_policy": cells[2],
                "note": cells[3],
            })
    return note, items


def load_package_versions(package_json_path: str):
    if not os.path.exists(package_json_path):
        return None
    try:
        with open(package_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        warn(f"package.json の読込/解析に失敗（上書きをスキップ）: {e}")
        return None
    versions = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = data.get(key)
        if isinstance(block, dict):
            for name, ver in block.items():
                if isinstance(ver, str):
                    versions[name] = ver
    pm = data.get("packageManager")
    if isinstance(pm, str):
        versions["__packageManager__"] = pm
    return versions


def _normalize_tech(technology: str) -> str:
    return technology.replace("`", "").strip().lower()


def _match_package_name(technology: str, versions: dict):
    norm = _normalize_tech(technology)
    if norm in NAME_MAP:
        return NAME_MAP[norm]
    for key, pkg in NAME_MAP.items():
        if key in norm:
            return pkg
    return None


def apply_real_versions(items, versions):
    if not versions:
        return 0
    overridden = 0
    for it in items:
        pkg = _match_package_name(it["technology"], versions)
        if not pkg:
            continue
        ver = versions.get(pkg)
        if not ver:
            continue
        if pkg == "__packageManager__":
            ver = ver.split("@")[-1]
        if it["version_policy"] != ver:
            it["version_policy"] = ver
            overridden += 1
    return overridden


def _yaml_quote(value: str) -> str:
    s = "" if value is None else str(value)
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


def build_block(note, items):
    lines = ["tech_stack:"]
    lines.append(f"  note: {_yaml_quote(note)}")
    lines.append("  items:")
    for it in items:
        lines.append(f"    - layer: {_yaml_quote(it['layer'])}")
        lines.append(f"      technology: {_yaml_quote(it['technology'])}")
        lines.append(f"      version_policy: {_yaml_quote(it['version_policy'])}")
        lines.append(f"      note: {_yaml_quote(it['note'])}")
    return lines


def _find_block_span(lines):
    start = None
    for idx, line in enumerate(lines):
        if line.rstrip() == "tech_stack:" and not line[:1].isspace():
            start = idx
            break
    if start is None:
        return None, None
    last = start
    j = start + 1
    while j < len(lines):
        line = lines[j]
        if line.strip() == "":
            j += 1
            continue
        if line[:1].isspace():
            last = j
            j += 1
        else:
            break
    return start, last


def write_back(manifest_path: str, note, items):
    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]
    start, last = _find_block_span(lines)
    block = build_block(note, items)
    if start is None:
        warn("manifest に tech_stack: ブロックが無いため末尾に追記する")
        new_lines = lines + [""] + block
    else:
        new_lines = lines[:start] + block + lines[last + 1:]
    new_content = newline.join(new_lines)
    if new_content == content:
        return False
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="techstack §9 を生成済み root manifest.yaml の tech_stack へ取り込む")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--design-doc", default=DEFAULT_DESIGN_DOC)
    parser.add_argument("--package-json", default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        print(f"[ingest_tech_stack] ERROR: manifest が見つからない: {args.manifest}")
        return 2
    if not os.path.exists(args.design_doc):
        warn(f"techstack 設計書が無いため取り込みをスキップ（既定値を維持）: {args.design_doc}")
        return 0

    with open(args.design_doc, "r", encoding="utf-8") as f:
        note, items = parse_section9(f.read())
    if not items:
        warn("§9 の技術スタック表が見つからないため取り込みをスキップ（既定値を維持）")
        return 0
    if note is None:
        try:
            note = (genlib.load_manifest(args.manifest).get("tech_stack") or {}).get("note") or ""
        except genlib.YamlError:
            note = ""

    versions = load_package_versions(args.package_json)
    if versions is None:
        info("package.json が無いため version_policy は設計書の方針を採用（fail-open）")
    else:
        info(f"package.json から {apply_real_versions(items, versions)} 件の version_policy を実態優先で上書き")

    if args.check:
        with open(args.manifest, "r", encoding="utf-8") as f:
            lines = [ln.rstrip("\r") for ln in f.read().split("\n")]
        start, last = _find_block_span(lines)
        would_change = start is None or lines[start:last + 1] != build_block(note, items)
        info(f"取り込み対象 {len(items)} 技術。書き換え{'あり' if would_change else 'なし'}（--check）")
        return 0

    changed = write_back(args.manifest, note, items)
    info(f"{len(items)} 技術を root manifest tech_stack へ取り込み（{'更新あり' if changed else '更新なし=冪等'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
