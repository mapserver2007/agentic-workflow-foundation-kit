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
    "test_github_auth_runtime.py",
    "test_ingest_tech_stack.py",
    "test_tech_contract.py",
    "test_contract_lifecycle_e2e.py",
    "test_contract_loop4.py",
    "test_contract_loop5.py",
    "test_contract_loop6.py",
    "test_contract_loop7.py",
    "test_contract_loop8.py",
    "test_contract_loop9.py",
    "test_contract_loop10.py",
    "test_contract_domain_sections.py",
    "test_resolved_contract_projection.py",
    "test_project_ignore_dirs.py",
    "test_full_lifecycle_e2e.py",
    "test_profile_selector_static.py",
    "test_contract_consumers.py",
    "test_provision_runtime.py",
    "test_resolve_quality_gate.py",
    "test_materialize_runtime.py",
    "test_check_tech_stack_conformance.py",
    "test_resolve_budget_thresholds.py",
    "test_session_progress_emitter.py",
    "test_session_progress_append.py",
    "test_review_start_gate.py",
    "test_validate_deep_thinking.py",
    "test_validate_agent_kaizen.py",
    "test_python39_annotation_compat.py",
    "test_worker_contract.py",
    "test_gate_adr.py",
    "test_gate_maintenance_docs.py",
    "test_project_gate_command.py",
    "test_workflow_orchestrator_gate_matrix.py",
    "test_step2_approval_boundary.py",
    "test_gate_test.py",
    "test_workflow_gate_step4_profile.py",
    "test_workflow_gate_step4_integration.py",
    "test_envelope_enforcement.py",
    "test_plan_gate_review.py",
    "test_bootstrap_dead_blocks.py",
]


def main() -> int:
    from test_root_snapshot import assert_unchanged, snapshot  # noqa: WPS433

    before = snapshot()
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
        drift = assert_unchanged(before, snapshot())
        if drift:
            print(f"[run_all_foundation_tests] FAIL: root snapshot drift after {test_name}: {drift}")
            return 1

    print(f"[run_all_foundation_tests] {passed}/{total} passed (pass 1)")
    passed2 = 0
    for test_name in TESTS_IN_ORDER:
        test_path = HERE / test_name
        if not test_path.exists():
            continue
        print(f"[run_all_foundation_tests] RUN (pass 2): {test_name}")
        result = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=str(HERE),
            env=dict(os.environ),
        )
        if result.returncode != 0:
            print(f"[run_all_foundation_tests] FAIL pass 2: {test_name} (exit {result.returncode})")
            return 1
        passed2 += 1
        drift = assert_unchanged(before, snapshot())
        if drift:
            print(f"[run_all_foundation_tests] FAIL: root snapshot drift pass 2 after {test_name}: {drift}")
            return 1

    print(f"[run_all_foundation_tests] {passed2}/{total} passed (pass 2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
