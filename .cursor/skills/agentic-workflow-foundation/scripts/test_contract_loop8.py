#!/usr/bin/env python3
"""Step④ loop8: fullmatch / validation / absent-marker / state-digests / malformed / docs."""
from __future__ import annotations

import copy
import json
import os
import re
import stat
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
    absent_marker,
    base_contract,
    executable_validation,
    go_lifecycle_contract,
    installed_marker,
    json_field_validation,
    write_sealed_manifest,
)

TECH_SCRIPT = HERE / "tech_contract.py"
SKILL = HERE.parent / "SKILL.md"
SESSION_HANDOVER = ROOT / ".cursor" / "skills" / "session-handover" / "SKILL.md"
DESIGN_CONFORMANCE = HERE.parent / "references" / "design-conformance.md"
SOURCE_MAPPING = HERE.parent / "references" / "source-mapping.md"


def version_fullmatch() -> bool:
    manifest = ROOT / "manifest.yaml"
    design = ROOT / ".cursor" / "docs" / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
    if not manifest.is_file():
        return True
    contract = tc.load_approved(manifest, design)
    if contract.get("classification", {}).get("profile") == "foundation":
        print("SKIP: foundation profile has no pnpm version preflight", file=sys.stderr)
        return True
    pattern_checks = [
        check
        for check in contract["provisioning"]["preflight_checks"]
        if check.get("kind") == "json-value-pattern"
    ]
    if not pattern_checks:
        print("FAIL: json-value-pattern preflight is missing", file=sys.stderr)
        return False
    toolchain_check = next(
        (check for check in pattern_checks if check.get("pointer") == "pnpm.version"),
        None,
    )
    if toolchain_check is None:
        print("FAIL: pnpm.version json-value-pattern preflight is missing", file=sys.stderr)
        return False
    isolated = copy.deepcopy(contract)
    isolated["provisioning"]["preflight_checks"] = [copy.deepcopy(toolchain_check)]
    isolated["provisioning"]["preflight_checks"][0]["target"] = ".state/toolchain-state.json"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "package.json").write_text('{"packageManager":"pnpm@11.17.0"}\n', encoding="utf-8")
        marker = root / ".state" / "toolchain-state.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"pnpm":{"version":"11.17.0-suffix"}}\n', encoding="utf-8")
        errors = rp.run_preflight(isolated, root)
        if not any("11.17.0-suffix" in error for error in errors):
            print("FAIL: suffix value should fail pnpm.version fullmatch", errors, file=sys.stderr)
            return False
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        contract = base_contract(fp, with_file_action=False)
        contract["provisioning"]["preflight_checks"] = [{
            "kind": "json-value-pattern",
            "target": "values.json",
            "pointer": "version",
            "pattern": "^1\\.0\\.0$",
            "evidence_ref": "x",
            "guidance": "exact only",
        }]
        manifest, design = write_sealed_manifest(Path(tmp), contract, "# x\n")
        root = Path(tmp)
        (root / "values.json").write_text('{"version":"1.0.0-beta"}\n', encoding="utf-8")
        errors = rp.run_preflight(tc.load_approved(manifest, design), root)
        if not any("json-value-pattern" in e for e in errors):
            print("FAIL: partial match accepted", errors, file=sys.stderr)
            return False
    return True


def installed_marker_empty_corrupt_wrong_name() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=False)
        contract["runtime_materialization"]["reality"] = {
            "required_packages": ["pkg-a"],
            "forbidden_packages": [],
        }
        contract["provisioning"]["command_actions"] = []
        contract["provisioning"]["preflight_checks"] = [
            installed_marker("markers/pkg-a.json", "pkg-a", json_field_validation("name", "pkg-a")),
        ]
        manifest, design = write_sealed_manifest(root, contract, "# x\n")
        approved = tc.load_approved(manifest, design)
        marker_dir = root / "markers"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / "pkg-a.json"
        cases = [
            ("missing", lambda: None),
            ("empty", lambda: marker.write_text("", encoding="utf-8")),
            ("corrupt", lambda: marker.write_text("{bad", encoding="utf-8")),
            ("wrong-name", lambda: marker.write_text('{"name":"other"}\n', encoding="utf-8")),
        ]
        for label, setup in cases:
            if marker.is_file():
                marker.unlink()
            setup()
            errors = rp.run_preflight(approved, root)
            if label == "missing":
                if not any("markers/pkg-a.json" in e for e in errors):
                    print("FAIL: missing marker not detected", errors, file=sys.stderr)
                    return False
            elif label in ("empty", "corrupt", "wrong-name"):
                if not errors:
                    print(f"FAIL: {label} marker accepted", file=sys.stderr)
                    return False
        exe = marker_dir / "tool.sh"
        contract2 = copy.deepcopy(base_contract(fp, with_file_action=True))
        contract2["runtime_materialization"]["reality"] = {
            "required_packages": ["tool"],
            "forbidden_packages": [],
        }
        contract2["provisioning"]["preflight_checks"] = [
            installed_marker("markers/tool.sh", "tool", executable_validation()),
        ]
        manifest2, design2 = write_sealed_manifest(root, contract2, "# x\n")
        approved2 = tc.load_approved(manifest2, design2)
        (root / "go.mod").write_text("module fixture\n", encoding="utf-8")
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        if rp.run_preflight(approved2, root):
            print("FAIL: valid executable marker rejected", file=sys.stderr)
            return False
        exe.write_text("", encoding="utf-8")
        if not rp.run_preflight(approved2, root):
            print("FAIL: empty executable accepted", file=sys.stderr)
            return False
    return True


def forbidden_marker_exact_cover() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        contract = base_contract(fp, with_file_action=False)
        contract["runtime_materialization"]["reality"] = {
            "required_packages": [],
            "forbidden_packages": ["bad-a", "bad-b"],
        }
        contract["provisioning"]["preflight_checks"] = [
            absent_marker("markers/bad-a", "bad-a"),
            absent_marker("markers/bad-b", "bad-b"),
        ]
        tc.validate(contract, doc, require_approval=False)
        bad = copy.deepcopy(contract)
        bad["provisioning"]["preflight_checks"][1]["covers_packages"] = ["bad-c"]
        try:
            tc.validate(bad, doc, require_approval=False)
        except tc.SchemaError as exc:
            if "forbidden_packages 外" not in str(exc):
                print("FAIL: unexpected schema error", exc, file=sys.stderr)
                return False
        else:
            print("FAIL: unknown forbidden cover accepted", file=sys.stderr)
            return False
        incomplete = copy.deepcopy(contract)
        incomplete["provisioning"]["preflight_checks"] = incomplete["provisioning"]["preflight_checks"][:1]
        try:
            tc.validate(incomplete, doc, require_approval=False)
        except tc.SchemaError as exc:
            if "forbidden_packages に preflight 未カバー" not in str(exc):
                print("FAIL: unexpected missing cover error", exc, file=sys.stderr)
                return False
        else:
            print("FAIL: incomplete forbidden cover accepted", file=sys.stderr)
            return False
        root = Path(tmp)
        manifest, design = write_sealed_manifest(root, contract, "# x\n")
        approved = tc.load_approved(manifest, design)
        (root / "markers" / "bad-a").parent.mkdir(parents=True, exist_ok=True)
        (root / "markers" / "bad-a").write_text("present\n", encoding="utf-8")
        errors = rp.run_preflight(approved, root)
        if not any("bad-a" in e and "存在してはいけません" in e for e in errors):
            print("FAIL: forbidden marker present not detected", errors, file=sys.stderr)
            return False
    return True


def state_digest_absent_rejected() -> bool:
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
            "marker": ".state/provision-state.json",
            "paths": ["pnpm-lock.yaml"],
            "evidence_ref": "x",
            "guidance": "digest required",
        }]
        manifest, design = write_sealed_manifest(root, contract, "# x\n")
        approved = tc.load_approved(manifest, design)
        marker = root / ".state" / "provision-state.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        lockfile = root / "pnpm-lock.yaml"
        lockfile.write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        marker.write_text('{"digests":{"pnpm-lock.yaml":"absent"}}\n', encoding="utf-8")
        try:
            rp.run_preflight(approved, root)
        except rp.PreflightFatal as exc:
            if "absent" not in str(exc):
                print("FAIL: unexpected absent digest rejection", exc, file=sys.stderr)
                return False
        else:
            print("FAIL: absent digest accepted for existing target", file=sys.stderr)
            return False
        lockfile.unlink()
        marker.write_text('{"digests":{"pnpm-lock.yaml":"deadbeef"}}\n', encoding="utf-8")
        errors = rp.run_preflight(approved, root)
        if not any("pnpm-lock.yaml" in e and "がありません" in e for e in errors):
            print("FAIL: missing digest target not detected", errors, file=sys.stderr)
            return False
    return True


def _run_cli(script: Path, args: list[str]) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def malformed_state_runtime_no_traceback_all_clis() -> bool:
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
            (rq.__file__, ["--manifest", str(bad), "--check"]),
            (rc.__file__, ["--manifest", str(bad), "--check"]),
            (rd.__file__, ["--manifest", str(bad), "--check"]),
        ]
        for script, args in cases:
            code, combined = _run_cli(Path(script), args)
            if "Traceback" in combined:
                print(f"FAIL: traceback in {script.name}", combined, file=sys.stderr)
                return False
            if code not in (1, 2):
                print(f"FAIL: unexpected exit {code} from {script.name}", combined, file=sys.stderr)
                return False
        marker_bad = root / "manifest-marker.yaml"
        marker_bad.write_text(
            "version: 1\nproject:\n  tech_stack_design_filename: TECH.md\n",
            encoding="utf-8",
        )
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=False)
        contract["provisioning"]["preflight_checks"] = [{
            "kind": "state-digests",
            "marker": ".state/provision-state.json",
            "paths": ["pnpm-lock.yaml"],
            "evidence_ref": "x",
            "guidance": "x",
        }]
        tc.seal_contract(marker_bad, contract, tc.file_digest(marker_bad))
        state = root / ".state" / "provision-state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text('"not-a-mapping"\n', encoding="utf-8")
        code, combined = _run_cli(conf.__file__, ["--manifest", str(marker_bad)])
        if "Traceback" in combined or code != 2:
            print("FAIL: malformed state marker should exit 2 without traceback", combined, file=sys.stderr)
            return False
    return True


def docs_contract_only_precise() -> bool:
    skill_lines = SKILL.read_text(encoding="utf-8").splitlines()
    if len(skill_lines) < 79:
        print("FAIL: SKILL too short", file=sys.stderr)
        return False
    line79 = skill_lines[78]
    if re.search(r"package\.json.*意味的整合", line79):
        print("FAIL: SKILL line79 still claims package.json semantic conformance", line79, file=sys.stderr)
        return False
    if not re.search(r"preflight_checks|declarative contract", line79):
        print("FAIL: SKILL line79 missing declarative contract wording", line79, file=sys.stderr)
        return False
    handover_lines = SESSION_HANDOVER.read_text(encoding="utf-8").splitlines()
    if len(handover_lines) < 42:
        print("FAIL: session-handover too short", file=sys.stderr)
        return False
    line42 = handover_lines[41]
    if re.search(r"tech_stack\s*から", line42):
        print("FAIL: session-handover line42 still claims tech_stack origin", line42, file=sys.stderr)
        return False
    if not re.search(r"tech_contract|quality_gate\.profile", line42):
        print("FAIL: session-handover line42 missing contract/profile projection", line42, file=sys.stderr)
        return False
    legacy_patterns = (
        (SKILL, r"workflow_pattern[`\s×]+tech_stack"),
        (SKILL, r"_tech_stack_hash"),
        (SKILL, r"registry compose"),
        (DESIGN_CONFORMANCE, r"package\.json 不在は fail-closed"),
        (DESIGN_CONFORMANCE, r"category/hash"),
    )
    for path, pattern in legacy_patterns:
        text = path.read_text(encoding="utf-8")
        if re.search(pattern, text):
            print(f"FAIL: legacy claim matched in {path.name}: {pattern}", file=sys.stderr)
            return False
    for path, needles in (
        (DESIGN_CONFORMANCE, ("validation", "absent-marker", "fullmatch")),
        (SOURCE_MAPPING, ("validation", "absent-marker", "installed-marker")),
    ):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                print(f"FAIL: {path.name} missing {needle}", file=sys.stderr)
                return False
    go = go_lifecycle_contract("0" * 64)
    reality = go.get("runtime_materialization", {}).get("reality")
    if reality is not None and reality.get("required_packages"):
        print("FAIL: go fixture should allow empty required_packages", file=sys.stderr)
        return False
    return True


def main() -> int:
    checks = {
        "version_fullmatch": version_fullmatch,
        "installed_marker_empty_corrupt_wrong_name": installed_marker_empty_corrupt_wrong_name,
        "forbidden_marker_exact_cover": forbidden_marker_exact_cover,
        "state_digest_absent_rejected": state_digest_absent_rejected,
        "malformed_state_runtime_no_traceback_all_clis": malformed_state_runtime_no_traceback_all_clis,
        "docs_contract_only_precise": docs_contract_only_precise,
    }
    for name, fn in checks.items():
        if not fn():
            print(f"FAIL: {name}", file=sys.stderr)
            return 1
        print(f"PASS: {name}")
    print("[test_contract_loop8] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
