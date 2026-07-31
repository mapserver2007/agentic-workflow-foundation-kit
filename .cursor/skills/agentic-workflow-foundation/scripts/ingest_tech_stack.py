#!/usr/bin/env python3
"""techstack 設計書 §9 を生成済み root manifest.yaml の tech_stack へ取り込む（Phase 1.6）。"""
from __future__ import annotations

import argparse
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
import tech_contract as tc  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")


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
        info("manifest に tech_stack: ブロックが無いため末尾に追記する")
        new_lines = lines + [""] + block
    else:
        new_lines = lines[:start] + block + lines[last + 1:]
    new_content = newline.join(new_lines)
    if new_content == content:
        return False
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def _resolve_design_doc(cli_design_doc: str | None, manifest_path: str) -> Path:
    if cli_design_doc is not None:
        return Path(cli_design_doc)
    manifest = Path(manifest_path)
    return tc.resolve_design_doc(manifest)


def _contract_fingerprint_stale(manifest_path: str, design_doc: Path) -> bool:
    """pin 済み契約が現行設計書と乖離しているか。

    source_fingerprint が空 / 未設定のときは未 pin（kit 初回 bootstrap 等）とみなし、
    Phase 1.6 の §9 取り込みは継続する。非空の fingerprint のみ stale 判定対象。
    """
    try:
        manifest = genlib.load_manifest(manifest_path)
    except genlib.YamlError:
        return False
    contract = manifest.get("tech_contract")
    if not isinstance(contract, dict):
        return False
    pinned = contract.get("source_fingerprint")
    if not isinstance(pinned, str) or not pinned.strip():
        return False
    return pinned != tc.source_fingerprint(design_doc)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="techstack §9 を生成済み root manifest.yaml の tech_stack へ取り込む")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--design-doc", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        print(f"[ingest_tech_stack] ERROR: manifest が見つからない: {args.manifest}")
        return 2

    try:
        design_doc = _resolve_design_doc(args.design_doc, args.manifest)
    except tc.SchemaError as exc:
        print(f"[ingest_tech_stack] ERROR: {exc}")
        return 2

    if not design_doc.is_file():
        print(f"[ingest_tech_stack] ERROR: 設計書が見つからない: {design_doc}")
        return 2

    with open(design_doc, "r", encoding="utf-8") as f:
        note, items = parse_section9(f.read())
    if not items:
        print("[ingest_tech_stack] ERROR: §9 の技術スタック表が見つかりません。契約再起案が必要です")
        return 1
    if note is None:
        try:
            note = (genlib.load_manifest(args.manifest).get("tech_stack") or {}).get("note") or ""
        except genlib.YamlError:
            note = ""

    fingerprint = tc.source_fingerprint(design_doc)
    if _contract_fingerprint_stale(args.manifest, design_doc):
        print(
            "[ingest_tech_stack] ERROR: tech_contract.source_fingerprint が設計書と不一致です。"
            " validate/apply で契約を再起案してください"
        )
        return 1

    if args.check:
        with open(args.manifest, "r", encoding="utf-8") as f:
            lines = [ln.rstrip("\r") for ln in f.read().split("\n")]
        start, last = _find_block_span(lines)
        would_change = start is None or lines[start:last + 1] != build_block(note, items)
        info(
            f"取り込み対象 {len(items)} 技術。"
            f"source_fingerprint={fingerprint[:16]}… "
            f"書き換え{'あり' if would_change else 'なし'}（--check）"
        )
        return 0

    changed = write_back(args.manifest, note, items)
    info(
        f"{len(items)} 技術を root manifest tech_stack へ取り込み"
        f"（{'更新あり' if changed else '更新なし=冪等'}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
