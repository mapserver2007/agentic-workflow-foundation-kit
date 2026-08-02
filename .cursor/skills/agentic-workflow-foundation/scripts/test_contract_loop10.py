#!/usr/bin/env python3
"""Step④ loop10: postcondition plan visibility / digest / argv safety。"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON_EXE = "python3"
sys.path.insert(0, str(HERE))
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract, fixture_command_action, write_sealed_manifest  # noqa: E402


def _contract_with_capture(fingerprint: str) -> dict:
    contract = base_contract(fingerprint, with_file_action=False)
    contract["provisioning"]["policy"] = "explicit"
    contract["runtime_materialization"]["actions"] = []
    action = fixture_command_action(".provision-marker")
    marker = ".state/toolchain-state.json"
    action["writes"].append(marker)
    action["postconditions"].append({
        "kind": "capture-toolchain-version",
        "argv": [PYTHON_EXE, "--version"],
        "marker": marker,
        "pointer": "python.version",
        "pattern": r"^Python \d+\.\d+\.\d+$",
        "evidence_ref": "design §9",
    })
    contract["provisioning"]["command_actions"] = [action]
    contract["provisioning"]["preflight_checks"] = []
    return contract


def postcondition_visible_and_digest_bound() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# fixture\n", encoding="utf-8")
        contract = _contract_with_capture(tc.source_fingerprint(design))
        tc.validate(contract, design, require_approval=False)
        manifest, design = write_sealed_manifest(root, contract, "# fixture\n")
        approved = tc.load_approved(manifest, design)
        plan = rp.build_plan(approved, root)
        command = next(item for item in plan["actions"] if item["phase"] == "command")
        planned = command.get("postconditions")
        capture = next(
            (item for item in planned or [] if item.get("kind") == "capture-toolchain-version"),
            None,
        )
        if capture is None:
            print("FAIL: capture postcondition is hidden from plan", file=sys.stderr)
            return False
        if capture.get("argv") != [PYTHON_EXE, "--version"]:
            print("FAIL: postcondition argv missing from plan", capture, file=sys.stderr)
            return False
        if capture.get("effects") != ["project_write"]:
            print("FAIL: postcondition effects missing from plan", capture, file=sys.stderr)
            return False
        if capture.get("writes") != [".state/toolchain-state.json"]:
            print("FAIL: postcondition writes missing from plan", capture, file=sys.stderr)
            return False
        changed = copy.deepcopy(approved["provisioning"]["command_actions"][0])
        changed["postconditions"][-1]["pattern"] = r"^different$"
        if rp.payload_digest(changed) == command["payload_digest"]:
            print("FAIL: postcondition payload excluded from digest", file=sys.stderr)
            return False
    return True


def unsafe_capture_argv_rejected_without_side_effect() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "TECH.md"
        design.write_text("# fixture\n", encoding="utf-8")
        contract = base_contract(tc.source_fingerprint(design), with_file_action=False)
        contract["provisioning"]["policy"] = "explicit"
        action = {
            "argv": ["true"],
            "cwd": ".",
            "effects": ["host_write"],
            "writes": [".state/toolchain-state.json"],
            "postconditions": [{
                "kind": "capture-toolchain-version",
                "argv": [sys.executable, "-c", "open('hidden.out','w').write('x')"],
                "marker": ".state/toolchain-state.json",
                "pointer": "python.version",
                "pattern": ".*",
                "evidence_ref": "design §9",
            }],
            "evidence_ref": "design §9",
        }
        contract["provisioning"]["command_actions"] = [action]
        try:
            tc.validate(contract, design, require_approval=False)
        except tc.SchemaError:
            pass
        else:
            print("FAIL: side-effect capture argv accepted by schema", file=sys.stderr)
            return False
        try:
            rp._apply_postconditions(action, root, root)
        except ValueError:
            pass
        else:
            print("FAIL: side-effect capture argv executed at runtime", file=sys.stderr)
            return False
        if (root / "hidden.out").exists():
            print("FAIL: undeclared hidden.out was created", file=sys.stderr)
            return False
    return True


def host_toolchain_actions_validate() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        design = Path(tmp) / "TECH.md"
        design.write_text("# fixture\n", encoding="utf-8")
        contract = base_contract(tc.source_fingerprint(design), with_file_action=False)
        contract["provisioning"]["policy"] = "explicit"
        contract["runtime_materialization"]["actions"] = []
        marker = ".state/toolchain-state.json"
        contract["provisioning"]["command_actions"] = [
            {
                "argv": ["corepack", "enable"],
                "cwd": ".",
                "effects": ["host_write"],
                "writes": [marker],
                "postconditions": [{
                    "kind": "capture-toolchain-version",
                    "argv": ["corepack", "--version"],
                    "marker": marker,
                    "pointer": "corepack.version",
                    "pattern": r"^\d+\.\d+\.\d+$",
                    "evidence_ref": "design §9",
                }],
                "evidence_ref": "design §9",
            },
            {
                "argv": ["corepack", "prepare", "pnpm@9.15.0", "--activate"],
                "cwd": ".",
                "effects": ["host_write", "network"],
                "writes": [marker],
                "postconditions": [{
                    "kind": "capture-toolchain-version",
                    "argv": ["pnpm", "--version"],
                    "marker": marker,
                    "pointer": "pnpm.version",
                    "pattern": r"^\d+\.\d+\.\d+$",
                    "evidence_ref": "design §9",
                }],
                "evidence_ref": "design §9",
            },
        ]
        contract["provisioning"]["preflight_checks"] = []
        tc.validate(contract, design, require_approval=False)
    return True


def safe_capture_apply_is_tracked() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# fixture\n", encoding="utf-8")
        contract = _contract_with_capture(tc.source_fingerprint(design))
        manifest, design = write_sealed_manifest(root, contract, "# fixture\n")
        approved = tc.load_approved(manifest, design)
        plan = rp.build_plan(approved, root)
        code, report = rp.apply_plan(plan, approved, root)
        marker = ".state/toolchain-state.json"
        if code != 0 or marker not in report.get("changed_targets", []):
            print("FAIL: safe capture marker not tracked", code, report, file=sys.stderr)
            return False
    return True


def allowed_shape_hidden_write_is_detected_and_reported() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bin_dir = root / "fixture-bin"
        bin_dir.mkdir()
        executable = bin_dir / "evil-version"
        executable.write_text(
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            "Path('hidden.out').write_text('x', encoding='utf-8')\n"
            "print('1.2.3')\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# fixture\n", encoding="utf-8")
        contract = base_contract(tc.source_fingerprint(design), with_file_action=False)
        contract["provisioning"]["policy"] = "explicit"
        contract["runtime_materialization"]["actions"] = []
        contract["provisioning"]["preflight_checks"] = []
        contract["provisioning"]["command_actions"] = [{
            "argv": ["true"],
            "cwd": ".",
            "effects": ["host_write"],
            "writes": ["marker.json"],
            "postconditions": [{
                "kind": "capture-toolchain-version",
                "argv": ["evil-version", "--version"],
                "marker": "marker.json",
                "pointer": "evil.version",
                "pattern": r"^\d+\.\d+\.\d+$",
                "evidence_ref": "design §9",
            }],
            "evidence_ref": "design §9",
        }]
        manifest, design = write_sealed_manifest(root, contract, "# fixture\n")
        approved = tc.load_approved(manifest, design)
        plan = rp.build_plan(approved, root)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
        try:
            code, report = rp.apply_plan(plan, approved, root)
        finally:
            os.environ["PATH"] = old_path
        if code != 2:
            print("FAIL: hidden write from allowed argv shape was accepted", code, report, file=sys.stderr)
            return False
        if "hidden.out" not in report.get("changed_targets", []):
            print("FAIL: hidden write missing from partial report", report, file=sys.stderr)
            return False
        if "undeclared project paths" not in report.get("recovery", ""):
            print("FAIL: hidden write reason missing", report, file=sys.stderr)
            return False
    return True


def main() -> int:
    checks = {
        "postcondition_visible_and_digest_bound": postcondition_visible_and_digest_bound,
        "unsafe_capture_argv_rejected_without_side_effect": unsafe_capture_argv_rejected_without_side_effect,
        "host_toolchain_actions_validate": host_toolchain_actions_validate,
        "safe_capture_apply_is_tracked": safe_capture_apply_is_tracked,
        "allowed_shape_hidden_write_is_detected_and_reported": allowed_shape_hidden_write_is_detected_and_reported,
    }
    for name, fn in checks.items():
        if not fn():
            print(f"FAIL: {name}", file=sys.stderr)
            return 1
        print(f"PASS: {name}")
    print("[test_contract_loop10] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
