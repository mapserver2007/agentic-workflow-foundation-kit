#!/usr/bin/env python3
"""check_design_drift.py — 統一設計書の改版を fingerprint(sha256) で検知する。

manifest.yaml > design_docs[].sha256 と現在の設計書ハッシュを照合し、
不一致（= 設計書が改版された / 初回未記録）を検出する。改版時は影響を受ける
manifest キーと出力ファイルを source-mapping.md ベースで列挙する。

使い方:
  python3 check_design_drift.py           # 照合のみ。drift があれば exit 1
  python3 check_design_drift.py --update  # 現在のハッシュを manifest に書き戻す（PO 承認後に実行）
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "manifest-generator", "scripts"
    ),
)
import genlib  # noqa: E402

# 設計書 ID -> 改版時に影響する manifest キー / 出力ファイル（source-mapping.md と対応）
IMPACT = {
    "unified": {
        "manifest_keys": [
            "framework.naming",
            "framework.hook_events",
            "framework.exit_codes",
            "framework.design_dimensions",
            "framework.budget_thresholds",
        ],
        "outputs": [
            "AGENTS.md",
            "CLAUDE.md",
            ".cursor/rules/*.mdc",
            ".cursor/hooks.json",
            "docs/QUALITY_GATE.md",
            "docs/DECISIONS.md",
            "docs/AGENT_RUNBOOK.md",
            "docs/session-handoff-guide.md",
        ],
    },
    "bas": {
        "manifest_keys": [
            "framework.accd_axes",
            "framework.agent_conduct",
        ],
        "outputs": [
            ".cursor/rules/02-agent-conduct.mdc",
            "docs/AGENT_RUNBOOK.md",
        ],
    },
    "techstack": {
        "manifest_keys": [
            "framework.tech_stack_note",
            "framework.tech_stack",
        ],
        "outputs": [
            "docs/tech-stack.md",
            "AGENTS.md",
        ],
    },
}


def collect(manifest: dict, root: str):
    docs = manifest.get("design_docs") or []
    results = []
    for d in docs:
        did = d.get("id")
        rel = d.get("path", "")
        stored = (d.get("sha256") or "").strip()
        abspath = os.path.join(root, rel)
        if not os.path.isfile(abspath):
            results.append((did, rel, stored, None, "missing"))
            continue
        current = genlib.sha256_file(abspath)
        if stored == "":
            state = "unrecorded"
        elif stored == current:
            state = "match"
        else:
            state = "drift"
        results.append((did, rel, stored, current, state))
    return results


def update_manifest(manifest_path: str, updates: dict[str, str]) -> None:
    """design_docs 内の各 id に対応する sha256 行を現在値へ書き換える（line-based）。"""
    with open(manifest_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    current_id = None
    in_design = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^design_docs:\s*$", line):
            in_design = True
            continue
        if in_design and re.match(r"^[A-Za-z_]", line):
            # design_docs ブロックを抜けた
            in_design = False
        if not in_design:
            continue
        m = re.match(r"^\s*-?\s*id:\s*(.+?)\s*$", line)
        if m:
            current_id = m.group(1).strip().strip('"').strip("'")
            continue
        if current_id in updates and re.match(r"^\s*sha256:\s*", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f'{indent}sha256: "{updates[current_id]}"\n'
            current_id = None
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)


def run(do_update: bool) -> int:
    skill_dir = genlib.skill_dir_of(__file__)
    root = genlib.root_from_skill_dir(skill_dir)
    manifest_path = os.path.join(skill_dir, "manifest.yaml")
    try:
        manifest = genlib.load_manifest(manifest_path)
    except genlib.YamlError as e:
        print(f"FATAL: manifest 解析失敗: {e}", file=sys.stderr)
        return 2

    results = collect(manifest, root)
    drifted = [r for r in results if r[4] in ("drift", "unrecorded")]
    missing = [r for r in results if r[4] == "missing"]

    print("設計書 fingerprint 照合:")
    for did, rel, stored, current, state in results:
        label = {
            "match": "OK   一致",
            "drift": "DRIFT 改版検知",
            "unrecorded": "NEW  未記録(初回)",
            "missing": "MISS 設計書不在",
        }[state]
        print(f"  [{label}] {did}: {rel}")
        if state in ("drift", "unrecorded") and current:
            print(f"        current sha256: {current}")

    if missing:
        print("\nFATAL: 設計書ファイルが見つからない（パスを確認）:", file=sys.stderr)
        for did, rel, *_ in missing:
            print(f"  - {did}: {rel}", file=sys.stderr)
        return 2

    if do_update:
        updates = {r[0]: r[3] for r in drifted if r[3]}
        if updates:
            update_manifest(manifest_path, updates)
            print(f"\n更新: {len(updates)} 件の sha256 を manifest に書き戻した。")
            print("次に generate.py で再生成し audit.py で検証すること。")
        else:
            print("\n更新対象なし（全て一致）。")
        return 0

    if drifted:
        print("\n影響範囲（source-mapping.md 参照。manifest 更新が必要な可能性）:")
        seen_keys, seen_outputs = set(), set()
        for did, *_ in drifted:
            imp = IMPACT.get(did, {})
            for k in imp.get("manifest_keys", []):
                seen_keys.add(k)
            for o in imp.get("outputs", []):
                seen_outputs.add(o)
        print("  影響 manifest キー:")
        for k in sorted(seen_keys):
            print(f"    - {k}")
        print("  影響出力ファイル:")
        for o in sorted(seen_outputs):
            print(f"    - {o}")
        print(
            "\n対応: (1) 設計書差分を source-mapping.md で展開 -> (2) 該当 manifest キー更新"
            "(Meta 層変更は PO 承認) -> (3) check_design_drift.py --update で sha256 書き戻し"
            " -> (4) generate.py 再生成 -> (5) audit.py 検証"
        )
        return 1

    print("\nOK: 設計書に改版なし（全 fingerprint 一致）。")
    return 0


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    do_update = "--update" in argv
    return run(do_update)


if __name__ == "__main__":
    sys.exit(main())
