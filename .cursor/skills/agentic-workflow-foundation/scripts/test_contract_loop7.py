#!/usr/bin/env python3
"""Step④ loop7: generic coverage / postcondition ordering / version / malformed / SKILL claims。"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
import check_tech_stack_conformance as conf  # noqa: E402
import materialize_runtime as mat  # noqa: E402
import provision_runtime as prov  # noqa: E402
import resolve_coderabbit as rc  # noqa: E402
import resolve_domain_docs as rd  # noqa: E402
import resolve_quality_gate as rq  # noqa: E402
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import (  # noqa: E402
    FIXTURE_RUNNER,
    base_contract,
    fixture_command_action,
    go_lifecycle_contract,
    installed_marker,
    json_field_validation,
    write_sealed_manifest,
)

TECH_SCRIPT = HERE / "tech_contract.py"


def generic_covers_packages_no_node_inference() -> bool:
    src = (HERE / "tech_contract.py").read_text(encoding="utf-8")
    if "node_modules/.bin/" in src or "dependency-marker" in src:
        print("FAIL: tech_contract still has node inference", file=sys.stderr)
        return False
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        contract = base_contract(fp, with_file_action=False)
        contract["runtime_materialization"]["reality"] = {
            "required_packages": ["pkg-a", "pkg-b"],
            "forbidden_packages": [],
        }
        contract["provisioning"]["preflight_checks"] = [
            installed_marker("markers/pkg-a.ok", "pkg-a", json_field_validation("name", "pkg-a")),
            installed_marker("markers/pkg-b.ok", "pkg-b", json_field_validation("name", "pkg-b")),
        ]
        tc.validate(contract, doc, require_approval=False)
        bad = copy.deepcopy(contract)
        bad["provisioning"]["preflight_checks"][1]["covers_packages"] = ["pkg-c"]
        try:
            tc.validate(bad, doc, require_approval=False)
        except tc.SchemaError as exc:
            if "required_packages 外" in str(exc):
                return True
            print("FAIL: unexpected schema error", exc, file=sys.stderr)
            return False
        print("FAIL: unknown covers_packages accepted", file=sys.stderr)
        return False


def copy_contract(contract: dict) -> dict:
    return copy.deepcopy(contract)


def postcondition_marker_created_after_command() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=False)
        contract["provisioning"]["policy"] = "explicit"
        contract["runtime_materialization"]["actions"] = []
        contract["provisioning"]["command_actions"] = [fixture_command_action(".provision-marker")]
        contract["provisioning"]["preflight_checks"] = []
        manifest, design = write_sealed_manifest(root, contract, "# x\nGo\n")
        approved = tc.load_approved(manifest, design)
        plan = rp.build_plan(approved, root)
        marker = root / ".cursor" / ".runtime" / "provision-state.json"
        if marker.is_file():
            print("FAIL: marker pre-exists", file=sys.stderr)
            return False
        code, report = rp.apply_plan(plan, approved, root)
        if code != 0:
            print("FAIL: apply", report, file=sys.stderr)
            return False
        if not marker.is_file():
            print("FAIL: marker not created by postcondition", file=sys.stderr)
            return False
        if ".cursor/.runtime/provision-state.json" not in report.get("changed_targets", []):
            print("FAIL: marker not in changed_targets", report, file=sys.stderr)
            return False
    return True


def production_root_command_postcondition_flow() -> bool:
    manifest = ROOT / "manifest.yaml"
    design = ROOT / ".cursor" / "docs" / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
    if not manifest.is_file():
        print("SKIP: no root manifest", file=sys.stderr)
        return True
    contract = tc.load_approved(manifest, design)
    pnpm_action = next(
        (a for a in rp.collect_command_actions(contract) if (a.get("argv") or [])[:2] == ["pnpm", "install"]),
        None,
    )
    if pnpm_action is None:
        print("FAIL: root pnpm install action missing", file=sys.stderr)
        return False
    post_generated = rp._postcondition_generated_paths(pnpm_action)
    writes = set(pnpm_action.get("writes") or [])
    if not post_generated.issubset(writes):
        print("FAIL: postcondition markers not declared in writes", file=sys.stderr)
        return False
    command_owned = [w for w in writes if w not in post_generated]
    if "pnpm-lock.yaml" not in command_owned:
        print("FAIL: expected command-owned lockfile write", file=sys.stderr)
        return False
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_path = root / "docs" / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(design.read_text(encoding="utf-8"), encoding="utf-8")
        draft = copy.deepcopy(contract)
        for key in ("contract_digest", "projection_digest", "approval"):
            draft.pop(key, None)
        draft["provisioning"]["command_actions"] = [{
            "argv": [sys.executable, str(FIXTURE_RUNNER), "touch", "--root", ".",
                     "--writes", "pnpm-lock.yaml", "node_modules/.bin/turbo"],
            "cwd": ".",
            "effects": ["project_write", "lockfile_write"],
            "writes": [
                "pnpm-lock.yaml",
                "node_modules/.bin/turbo",
                ".cursor/.runtime/provision-state.json",
            ],
            "postconditions": [{
                "kind": "record-state-digest",
                "marker": ".cursor/.runtime/provision-state.json",
                "paths": ["pnpm-lock.yaml"],
                "evidence_ref": "fixture",
            }],
            "evidence_ref": "fixture",
        }]
        manifest_copy = root / "manifest.yaml"
        manifest_copy.write_text(
            "version: 1\nproject:\n  tech_stack_design_filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md\n",
            encoding="utf-8",
        )
        tc.seal_contract(manifest_copy, draft, tc.file_digest(manifest_copy))
        approved = tc.load_approved(manifest_copy, design_path)
        plan = rp.build_plan(approved, root)
        code, report = rp.apply_plan(plan, approved, root)
        if code != 0:
            print("FAIL: fixture root flow", report, file=sys.stderr)
            return False
    return True


def production_root_toolchain_order() -> bool:
    manifest = ROOT / "manifest.yaml"
    design = ROOT / ".cursor" / "docs" / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
    if not manifest.is_file():
        print("SKIP: no root manifest", file=sys.stderr)
        return True
    contract = tc.load_approved(manifest, design)
    actual = [
        action.get("argv")
        for action in rp.collect_command_actions(contract)
    ]
    expected = [
        ["corepack", "enable"],
        ["corepack", "prepare", "pnpm@9.15.0", "--activate"],
        ["pnpm", "install", "--frozen-lockfile=false"],
    ]
    if actual != expected:
        print("FAIL: root host toolchain command order", actual, file=sys.stderr)
        return False
    package_action = next(
        action
        for action in contract["runtime_materialization"]["actions"]
        if action.get("target") == "package.json"
    )
    if package_action["values"].get("packageManager") != "pnpm@9.15.0":
        print("FAIL: corepack pin differs from packageManager", file=sys.stderr)
        return False
    return True


def marker_version_mismatch_fails() -> bool:
    manifest = ROOT / "manifest.yaml"
    design = ROOT / ".cursor" / "docs" / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
    if not manifest.is_file():
        return True
    contract = tc.load_approved(manifest, design)
    pattern_checks = [
        check
        for check in contract["provisioning"]["preflight_checks"]
        if check.get("kind") == "json-value-pattern"
    ]
    if not pattern_checks:
        print("FAIL: production root missing json-value-pattern preflight", file=sys.stderr)
        return False
    isolated = copy.deepcopy(contract)
    isolated["provisioning"]["preflight_checks"] = pattern_checks
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        marker = root / ".cursor" / ".runtime" / "toolchain-state.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        # production pattern は semver fullmatch。suffix 付き値で json-value-pattern 不一致を検証する。
        bad_version = "9.15.0-suffix"
        marker.write_text(
            json.dumps({"pnpm": {"version": bad_version}}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        errors = rp.run_preflight(isolated, root)
        if not any("json-value-pattern" in e and bad_version in e for e in errors):
            print("FAIL: version mismatch not detected", errors, file=sys.stderr)
            return False
    return True


def required_package_marker_missing_fails() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=True)
        contract["runtime_materialization"]["reality"] = {
            "required_packages": ["pkg-a"],
            "forbidden_packages": [],
        }
        contract["provisioning"]["command_actions"] = []
        contract["provisioning"]["preflight_checks"] = [
            installed_marker("markers/pkg-a.ok", "pkg-a", json_field_validation("name", "pkg-a")),
        ]
        manifest, design = write_sealed_manifest(root, contract, "# x\n")
        errors = rp.run_preflight(tc.load_approved(manifest, design), root)
        if not errors or not any("markers/pkg-a.ok" in e for e in errors):
            print("FAIL: missing installed marker not detected", errors, file=sys.stderr)
            return False
    return True


def state_digest_mismatch_fails() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=True)
        contract["provisioning"]["command_actions"] = []
        contract["provisioning"]["preflight_checks"] = [{
            "kind": "state-digests",
            "marker": ".cursor/.runtime/provision-state.json",
            "paths": ["pnpm-lock.yaml"],
            "evidence_ref": "x",
            "guidance": "digest mismatch",
        }]
        manifest, design = write_sealed_manifest(root, contract, "# x\n")
        (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        marker = root / ".cursor" / ".runtime" / "provision-state.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"digests":{"pnpm-lock.yaml":"deadbeef"}}\n', encoding="utf-8")
        errors = rp.run_preflight(tc.load_approved(manifest, design), root)
        if not any("state-digests" in e for e in errors):
            print("FAIL: state digest mismatch not detected", errors, file=sys.stderr)
            return False
    return True


def invalid_path_element_schema_error() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        contract = base_contract(fp, with_file_action=False)
        contract["provisioning"]["policy"] = "explicit"
        contract["provisioning"]["command_actions"] = [{
            "argv": [sys.executable, str(FIXTURE_RUNNER), "touch", "--root", "."],
            "cwd": ".",
            "effects": ["project_write"],
            "writes": [".provision-marker", ".cursor/.runtime/provision-state.json"],
            "postconditions": [{
                "kind": "record-state-digest",
                "marker": ".cursor/.runtime/provision-state.json",
                "paths": [""],
                "evidence_ref": "x",
            }],
            "evidence_ref": "x",
        }]
        try:
            tc.validate(contract, doc, require_approval=False)
        except tc.SchemaError:
            return True
        print("FAIL: empty path element accepted", file=sys.stderr)
        return False


def _run_cli(script: Path, args: list[str]) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def malformed_json_sections_no_traceback_all_clis() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad = root / "manifest.yaml"
        bad.write_text("tech_contract: [bad]\n", encoding="utf-8")
        design = root / "TECH.md"
        design.write_text("# x\n", encoding="utf-8")
        cases = [
            (TECH_SCRIPT, ["validate", "--design-doc", str(design), "--draft", str(bad), "--check"]),
            (prov.__file__, ["--preflight", "--manifest", str(bad), "--design-doc", str(design)]),
            (mat.__file__, ["--check", "--manifest", str(bad), "--design-doc", str(design)]),
            (conf.__file__, ["--manifest", str(bad)]),
        ]
        for script, args in cases:
            code, combined = _run_cli(Path(script), args)
            if "Traceback" in combined:
                print(f"FAIL: traceback in {script.name}", combined, file=sys.stderr)
                return False
            if code not in (1, 2):
                print(f"FAIL: unexpected exit {code} from {script.name}", combined, file=sys.stderr)
                return False
    return True


def no_tech_specific_active_python() -> bool:
    forbidden = (
        "rebuild_root_tech_contract",
        "dependency-marker",
    )
    for name in ("tech_contract.py", "runtime_plan.py", "provision_runtime.py"):
        text = (HERE / name).read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                print(f"FAIL: {name} contains {token}", file=sys.stderr)
                return False
    if (HERE / "rebuild_root_tech_contract.py").is_file():
        print("FAIL: rebuild_root_tech_contract.py exists", file=sys.stderr)
        return False
    return True


def main() -> int:
    checks = {
        "generic_covers_packages_no_node_inference": generic_covers_packages_no_node_inference,
        "postcondition_marker_created_after_command": postcondition_marker_created_after_command,
        "production_root_command_postcondition_flow": production_root_command_postcondition_flow,
        "production_root_toolchain_order": production_root_toolchain_order,
        "marker_version_mismatch_fails": marker_version_mismatch_fails,
        "required_package_marker_missing_fails": required_package_marker_missing_fails,
        "state_digest_mismatch_fails": state_digest_mismatch_fails,
        "invalid_path_element_schema_error": invalid_path_element_schema_error,
        "malformed_json_sections_no_traceback_all_clis": malformed_json_sections_no_traceback_all_clis,
        "no_tech_specific_active_python": no_tech_specific_active_python,
    }
    for name, fn in checks.items():
        if not fn():
            print(f"FAIL: {name}", file=sys.stderr)
            return 1
        print(f"PASS: {name}")
    print("[test_contract_loop7] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
