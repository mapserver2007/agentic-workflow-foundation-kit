#!/usr/bin/env python3
"""承認済み tech_contract の runtime file/command action を plan/apply/preflight する。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="承認済み tech contract provisioning")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    parser.add_argument("--manifest", type=Path, default=HERE.parents[3] / "manifest.yaml")
    parser.add_argument("--design-doc", type=Path, required=True)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--approve-plan", help="plan_digest を明示承認するトークン")
    args = parser.parse_args(argv)
    try:
        contract = tc.load_approved(args.manifest, args.design_doc)
        root = args.manifest.parent
        if args.preflight:
            try:
                errors = rp.run_preflight(contract, root)
            except rp.PreflightFatal as exc:
                print(f"FATAL: {exc}", file=sys.stderr)
                return 2
            if errors:
                print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
                return 2
            print("PASS: runtime preflight")
            return 0
        plan = rp.build_plan(contract, root)
        if args.plan:
            if args.plan_file:
                raise tc.ContractError("--plan は read-only です")
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        if not args.plan_file or not args.plan_file.is_file():
            raise tc.SchemaError("--apply には --plan-file が必要です")
        if not args.approve_plan:
            raise tc.SchemaError("--apply には --approve-plan <plan_digest> が必要です")
        saved = json.loads(args.plan_file.read_text(encoding="utf-8"))
        current = rp.build_plan(contract, root)
        if saved != current or args.approve_plan != plan["plan_digest"]:
            raise tc.ContractError("plan digest / contract / target preimage が現在と一致しません")
        if rp.digest_path(args.manifest) != plan["manifest_preimage"]:
            raise tc.ContractError("root manifest が plan 後に変化しました")
        code, report = rp.apply_plan(plan, contract, root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return code
    except tc.ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
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
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
