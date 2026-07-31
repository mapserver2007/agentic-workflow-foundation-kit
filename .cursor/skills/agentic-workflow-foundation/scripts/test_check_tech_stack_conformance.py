#!/usr/bin/env python3
"""contract preflight 整合ゲートの fixture テスト。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import conformance_contract, write_conformance_manifest  # noqa: E402

SCRIPT = HERE / "check_tech_stack_conformance.py"


def run(manifest: Path) -> int:
    return subprocess.run([sys.executable, str(SCRIPT), "--manifest", str(manifest)]).returncode


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest, design = write_conformance_manifest(root)
        if run(manifest) != 1:
            print("FAIL: absent package.json was not rejected")
            return 1
        contract = conformance_contract(tc.source_fingerprint(design))
        for action in contract["runtime_materialization"]["actions"]:
            rp.apply_file_action(action, root)
        if run(manifest) != 0:
            print("FAIL: valid preflight rejected")
            return 1
    print("[test_check_tech_stack_conformance] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
