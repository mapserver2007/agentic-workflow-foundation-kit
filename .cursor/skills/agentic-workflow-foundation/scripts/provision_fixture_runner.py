#!/usr/bin/env python3
"""テスト fixture: 宣言済み writes を network/host 変更なしで生成する。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _touch_paths(root: Path, paths: list[str]) -> None:
    for rel in paths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix == ".json":
            if not target.is_file():
                target.write_text("{}\n", encoding="utf-8")
        elif rel.endswith("pnpm-lock.yaml"):
            target.write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        elif "node_modules" in rel:
            target.write_text("#!/bin/sh\necho fixture\n", encoding="utf-8")
            target.chmod(0o755)
        else:
            target.write_text("fixture-ok\n", encoding="utf-8")


def _write_bundle(root: Path, spec_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    for item in spec:
        rel = item["path"]
        content = item.get("content", "fixture-ok\n")
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="provision test fixture runner")
    parser.add_argument("mode", choices=("touch", "bundle"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--writes", nargs="*", default=[".provision-marker"])
    parser.add_argument("--spec", type=Path, help="bundle mode: JSON [{path, content}]")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        if args.mode == "touch":
            _touch_paths(root, list(args.writes))
            return 0
        if not args.spec or not args.spec.is_file():
            print("FATAL: --spec required for bundle mode", file=sys.stderr)
            return 2
        return _write_bundle(root, args.spec)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
