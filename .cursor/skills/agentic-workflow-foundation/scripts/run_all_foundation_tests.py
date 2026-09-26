#!/usr/bin/env python3
"""Foundation script tests の集約 runner。

bin/foundation-gate scripts / self から呼ばれる。
test_worker_contract.py は audit 後段で自動実行されるため、
self (audit + scripts) 経由時の重複実行は許容する（冪等）。

実行順序は固定。子プロセスの exit 2 は致命的エラーとして維持し、
それ以外の失敗は即停止して exit 1 を返す。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def propagate_exit(returncode: int) -> int:
    """子プロセスの終了コードを集約する。exit 2 は致命的エラーとして維持する。"""
    if returncode == 0:
        return 0
    if returncode == 2:
        return 2
    return 1

TESTS_IN_ORDER = [
    "test_engine_readonly.py",
    "test_seed_audit_scope.py",
    "test_generate_skip_unchanged.py",
    "test_genlib_literal_render.py",
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
    "test_coderabbit_yaml.py",
    "test_consumer_foundation_disabled.py",
    "test_contract_consumers.py",
    "test_provision_runtime.py",
    "test_resolve_quality_gate.py",
    "test_materialize_runtime.py",
    "test_check_tech_stack_conformance.py",
    "test_resolve_budget_thresholds.py",
    "test_session_progress_emitter.py",
    "test_session_progress_append.py",
    "test_review_start_gate.py",
    "test_kit_update.py",
    "test_validate_deep_thinking.py",
    "test_validate_requirement_analysis.py",
    "test_validate_agent_kaizen.py",
    "test_python39_annotation_compat.py",
    "test_worker_contract.py",
    "test_gate_adr.py",
    "test_domain_doc_scope.py",
    "test_gate_report_doc_scope.py",
    "test_gate_domain_write_scope.py",
    "test_workflow_gate_domain_scope.py",
    "test_domain_docs_wiring.py",
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
    "test_campaign_cleanup.py",
    "test_campaign_session_binding.py",
    "test_session_byte_count.py",
]
TEST_HELPERS = {
    "test_contract_fixture.py",
    "test_root_snapshot.py",
}


def main() -> int:
    from test_root_snapshot import assert_unchanged, snapshot  # noqa: WPS433

    before = snapshot()
    missing = [name for name in TESTS_IN_ORDER if not (HERE / name).is_file()]
    if missing:
        for test_name in missing:
            print(f"[run_all_foundation_tests] FAIL: registered test not found: {test_name}")
        return 1
    discovered = {path.name for path in HERE.glob("test_*.py")}
    unregistered = sorted(discovered - set(TESTS_IN_ORDER) - TEST_HELPERS)
    if unregistered:
        for test_name in unregistered:
            print(f"[run_all_foundation_tests] FAIL: unregistered test file: {test_name}")
        return 1

    total = 0
    passed = 0
    with tempfile.TemporaryDirectory(prefix="foundation-test-skill-home-") as skill_home:
        test_env = dict(os.environ)
        test_env["AGENTIC_WORKFLOW_UPDATE_HOME"] = skill_home
        for test_name in TESTS_IN_ORDER:
            test_path = HERE / test_name
            total += 1
            print(f"[run_all_foundation_tests] RUN: {test_name}")
            result = subprocess.run(
                [sys.executable, str(test_path)],
                cwd=str(HERE),
                env=test_env,
            )
            status = propagate_exit(result.returncode)
            if status != 0:
                print(f"[run_all_foundation_tests] FAIL: {test_name} (exit {result.returncode})")
                return status
            passed += 1
            drift = assert_unchanged(before, snapshot())
            if drift:
                print(f"[run_all_foundation_tests] FAIL: root snapshot drift after {test_name}: {drift}")
                return 1

        print(f"[run_all_foundation_tests] {passed}/{total} passed (pass 1)")
        passed2 = 0
        for test_name in TESTS_IN_ORDER:
            test_path = HERE / test_name
            print(f"[run_all_foundation_tests] RUN (pass 2): {test_name}")
            result = subprocess.run(
                [sys.executable, str(test_path)],
                cwd=str(HERE),
                env=test_env,
            )
            status = propagate_exit(result.returncode)
            if status != 0:
                print(f"[run_all_foundation_tests] FAIL pass 2: {test_name} (exit {result.returncode})")
                return status
            passed2 += 1
            drift = assert_unchanged(before, snapshot())
            if drift:
                print(f"[run_all_foundation_tests] FAIL: root snapshot drift pass 2 after {test_name}: {drift}")
                return 1

    print(f"[run_all_foundation_tests] {passed2}/{total} passed (pass 2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
