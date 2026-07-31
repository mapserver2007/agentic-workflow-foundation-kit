#!/usr/bin/env python3
"""承認済み tech_contract の runtime renderability 検査（read-only）。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402


def _out(level: str, msg: str) -> None:
    print(f"[materialize_runtime] {level}: {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="tech_contract runtime renderability checker")
    parser.add_argument("--manifest", type=Path, default=ROOT / "manifest.yaml")
    parser.add_argument("--design-doc", type=Path)
    parser.add_argument("--check", action="store_true", help="renderability / ownership dry-run")
    args = parser.parse_args(argv)
    if not args.check:
        _out("FATAL", "apply/write は廃止されました。bin/project-setup --plan/--apply を使用してください")
        return 2
    try:
        design_doc = args.design_doc or tc.resolve_design_doc(args.manifest)
        contract = tc.load_approved(args.manifest, design_doc)
        root = args.manifest.parent
        for action in rp.collect_file_actions(contract):
            rp.render_file_bytes(action, root)
            conflict = rp.check_ownership_conflict(action, root)
            if conflict:
                raise tc.SchemaError(conflict)
        _out("PASS", "runtime file actions renderable")
        return 0
    except tc.ContractError as exc:
        _out("ERROR", str(exc))
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
        _out("FATAL", str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
