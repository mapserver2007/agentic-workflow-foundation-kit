#!/usr/bin/env python3
"""Foundation script tests の集約 runner。

bin/foundation-gate scripts / self から呼ばれる。
test_worker_contract.py は audit 後段で自動実行されるため、
self (audit + scripts) 経由時の重複実行は許容する（冪等）。

実行順序は固定。1 件でも失敗すれば即停止し exit 1 を返す。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

TESTS_IN_ORDER = [
    "test_engine_readonly.py",
    "test_apply_kit_init.py",
    "test_resolve_quality_gate.py",
    "test_resolve_budget_thresholds.py",
    "test_validate_deep_thinking.py",
    "test_validate_agent_kaizen.py",
    "test_worker_contract.py",
    "test_gate_adr.py",
    "test_gate_maintenance_docs.py",
    "test_project_gate_command.py",
    "test_workflow_orchestrator_gate_matrix.py",
    "test_plan_gate_review.py",
]


def main() -> int:
    total = 0
    passed = 0
    for test_name in TESTS_IN_ORDER:
        test_path = HERE / test_name
        if not test_path.exists():
            print(f"[run_all_foundation_tests] SKIP: {test_name} (not found)")
            continue
        total += 1
        print(f"[run_all_foundation_tests] RUN: {test_name}")
        result = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=str(HERE),
            env=dict(os.environ),
        )
        if result.returncode != 0:
            print(f"[run_all_foundation_tests] FAIL: {test_name} (exit {result.returncode})")
            return 1
        passed += 1

    print(f"[run_all_foundation_tests] {passed}/{total} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
