#!/usr/bin/env python3
"""生成済み CodeRabbit 設定が有効な YAML であることを検査する。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main() -> int:
    try:
        import yaml
    except ImportError:
        print("[test_coderabbit_yaml] FATAL: PyYAML が必要です", file=sys.stderr)
        return 2

    path = ROOT / ".coderabbit.yaml"
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"[test_coderabbit_yaml] FAIL: {exc}", file=sys.stderr)
        return 1
    if not isinstance(value, dict):
        print("[test_coderabbit_yaml] FAIL: top-level mapping が必要です", file=sys.stderr)
        return 1
    instructions = ((value.get("reviews") or {}).get("path_instructions") or [])
    if not instructions or not all(
        isinstance(item, dict) and isinstance(item.get("instructions"), str)
        for item in instructions
    ):
        print("[test_coderabbit_yaml] FAIL: path_instructions が不正です", file=sys.stderr)
        return 1
    print("[test_coderabbit_yaml] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
