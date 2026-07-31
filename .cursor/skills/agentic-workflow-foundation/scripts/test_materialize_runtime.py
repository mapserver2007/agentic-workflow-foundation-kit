#!/usr/bin/env python3
"""contract runtime action の generic projection 回帰（read-only materialize）。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import materialize_runtime as runtime  # noqa: E402
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract, write_sealed_manifest  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design_text = "# fixture\n"
        design.write_text(design_text, encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp)
        contract["runtime_materialization"]["actions"] = [{
            "kind": "owned-text-render",
            "target": "generated/config.txt",
            "ownership": "tool",
            "conflict_policy": "fail",
            "evidence_ref": "fixture",
            "content": "contract-owned\n",
        }]
        manifest, design = write_sealed_manifest(root, contract, design_text)

        result = subprocess.run(
            [sys.executable, str(HERE / "materialize_runtime.py"),
             "--manifest", str(manifest), "--design-doc", str(design)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 2:
            print("FAIL: apply path not rejected", result.stderr)
            return 1

        if runtime.main(["--manifest", str(manifest), "--design-doc", str(design), "--check"]) != 0:
            print("FAIL: --check renderability")
            return 1

        actions = [{
            "kind": "owned-text-render",
            "target": "generated/config.txt",
            "ownership": "tool",
            "conflict_policy": "fail",
            "evidence_ref": "fixture",
            "content": "contract-owned\n",
        }]
        for action in actions:
            try:
                rp.apply_file_action(action, root, dry_run=True)
            except Exception:
                print("FAIL: dry-run")
                return 1
        if (root / "generated/config.txt").exists():
            print("FAIL: dry-run wrote target")
            return 1
        rp.apply_file_action(actions[0], root, dry_run=False)
        target = root / "generated/config.txt"
        if target.read_text(encoding="utf-8") != "contract-owned\n":
            print("FAIL: apply via runtime_plan")
            return 1
        target.write_text("drift\n", encoding="utf-8")
        try:
            rp.apply_file_action(actions[0], root, dry_run=False)
        except ValueError:
            pass
        else:
            print("FAIL: drift was accepted")
            return 1
    print("[test_materialize_runtime] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
