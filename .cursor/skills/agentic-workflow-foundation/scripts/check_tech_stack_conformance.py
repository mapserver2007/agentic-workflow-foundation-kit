#!/usr/bin/env python3
"""承認済み tech_contract の preflight / postcondition を generic に評価する整合ゲート。"""
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

import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")


def _out(level: str, msg: str) -> None:
    print(f"[check_tech_stack_conformance] {level}: {msg}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="tech_contract preflight 整合ゲート")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        _out("ERROR", f"manifest が見つからない: {args.manifest}")
        return 2

    try:
        manifest_path = Path(args.manifest)
        design_doc = tc.resolve_design_doc(manifest_path)
        contract = tc.load_approved(manifest_path, design_doc)
    except tc.ContractError as exc:
        _out("FAIL", str(exc))
        return 1
    except (
        tc.SchemaError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        AttributeError,
        OSError,
        re.error,
        rp.PreflightFatal,
    ) as exc:
        _out("ERROR", str(exc))
        return 2

    root = manifest_path.parent
    try:
        errors = rp.run_preflight(contract, root)
    except rp.PreflightFatal as exc:
        _out("ERROR", str(exc))
        return 2
    if errors:
        for error in errors:
            _out("FAIL", error)
        _out("FAIL", f"整合ゲート不合格（{len(errors)} 件）。PO に報告し中断する")
        return 1

    _out("PASS", "tech_contract preflight 整合 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
