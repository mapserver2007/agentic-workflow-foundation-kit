#!/usr/bin/env python3
"""Step④ loop9: malformed preflight fatal / required-forbidden disjoint。"""
from __future__ import annotations

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
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import (  # noqa: E402
    absent_marker,
    base_contract,
    fixture_command_action,
    installed_marker,
    json_field_validation,
    write_sealed_manifest,
)


def _run_cli(script: str, args: list[str]) -> tuple[int, str]:
    result = subprocess.run([sys.executable, script, *args], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def _preflight_contract(root: Path, checks: list[dict], *, with_file: bool = True) -> tuple[Path, Path]:
    design = root / "docs" / "TECH.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("# x\n", encoding="utf-8")
    fp = tc.source_fingerprint(design)
    contract = base_contract(fp, with_file_action=with_file)
    contract["provisioning"]["preflight_checks"] = checks
    contract["provisioning"]["command_actions"] = [fixture_command_action(".provision-marker")]
    return write_sealed_manifest(root, contract, "# x\n")


def _assert_fatal_cli(script: str, args: list[str]) -> bool:
    code, combined = _run_cli(script, args)
    if "Traceback" in combined:
        print(f"FAIL: traceback in {Path(script).name}", combined, file=sys.stderr)
        return False
    if code != 2:
        print(f"FAIL: expected exit 2 from {Path(script).name}, got {code}", combined, file=sys.stderr)
        return False
    return True


def _assert_fatal_preflight_clis(root: Path, design: Path) -> bool:
    manifest = root / "manifest.yaml"
    return (
        _assert_fatal_cli(conf.__file__, ["--manifest", str(manifest)])
        and _assert_fatal_cli(
            prov.__file__,
            ["--preflight", "--manifest", str(manifest), "--design-doc", str(design)],
        )
    )


def _assert_fatal_materialize_cli(root: Path, design: Path) -> bool:
    manifest = root / "manifest.yaml"
    return _assert_fatal_cli(
        mat.__file__,
        ["--check", "--manifest", str(manifest), "--design-doc", str(design)],
    )


def json_key_present_scalar_fatal() -> bool:
    payloads = ('"scalar"', "[1, 2, 3]", "42")
    for payload in payloads:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, design = _preflight_contract(root, [{
                "kind": "json-key-present",
                "target": "data.json",
                "key": "name",
                "evidence_ref": "x",
                "guidance": "mapping required",
            }])
            (root / "data.json").write_text(f"{payload}\n", encoding="utf-8")
            try:
                rp.run_preflight(tc.load_approved(manifest, design), root)
            except rp.PreflightFatal:
                pass
            else:
                print(f"FAIL: scalar/list root accepted in run_preflight: {payload}", file=sys.stderr)
                return False
            if not _assert_fatal_preflight_clis(root, design):
                print(f"FAIL: CLIs did not fatal on scalar/list: {payload}", file=sys.stderr)
                return False
    return True


def invalid_utf8_state_fatal_all_clis() -> bool:
    preflight_scenarios = [
        ("json-key-present-utf8", lambda root: (root / "data.json").write_bytes(b"\xff\xfe"), [{
            "kind": "json-key-present",
            "target": "data.json",
            "key": "name",
            "evidence_ref": "x",
            "guidance": "utf8",
        }]),
        ("state-digests-nested", lambda root: (
            (root / "markers").mkdir(parents=True, exist_ok=True),
            (root / "markers" / "state.json").write_text(
                '{"digests":"not-a-mapping"}\n', encoding="utf-8",
            ),
        ), [{
            "kind": "state-digests",
            "marker": "markers/state.json",
            "paths": ["pnpm-lock.yaml"],
            "evidence_ref": "x",
            "guidance": "nested",
        }]),
    ]
    for label, setup, checks in preflight_scenarios:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, design = _preflight_contract(root, checks)
            setup(root)
            if not _assert_fatal_preflight_clis(root, design):
                print(f"FAIL: preflight CLIs for {label}", file=sys.stderr)
                return False

    materialize_setups = [
        ("materialize-utf8", lambda root: (root / "package.json").write_bytes(b"\xff\xfe")),
        ("materialize-scalar", lambda root: (root / "package.json").write_text("[]\n", encoding="utf-8")),
    ]
    for label, setup in materialize_setups:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "docs" / "TECH.md"
            design.parent.mkdir(parents=True, exist_ok=True)
            design.write_text("# x\n", encoding="utf-8")
            fp = tc.source_fingerprint(design)
            contract = base_contract(fp, with_file_action=False)
            contract["provisioning"]["policy"] = "explicit"
            contract["runtime_materialization"]["actions"] = [{
                "kind": "json-key-merge",
                "target": "package.json",
                "ownership": "project",
                "conflict_policy": "merge_owned",
                "evidence_ref": "x",
                "owned_keys": ["name"],
                "values": {"name": "fixture"},
            }]
            contract["provisioning"]["preflight_checks"] = []
            contract["provisioning"]["command_actions"] = []
            write_sealed_manifest(root, contract, "# x\n")
            setup(root)
            if not _assert_fatal_materialize_cli(root, design):
                print(f"FAIL: materialize scenario {label}", file=sys.stderr)
                return False
    return True


def required_forbidden_disjoint_required() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        contract = base_contract(fp, with_file_action=False)
        contract["runtime_materialization"]["reality"] = {
            "required_packages": ["pkg-x"],
            "forbidden_packages": ["pkg-x"],
        }
        contract["provisioning"]["preflight_checks"] = [
            installed_marker("markers/pkg-x.json", "pkg-x", json_field_validation("name", "pkg-x")),
            absent_marker("markers/forbidden-pkg-x", "pkg-x"),
        ]
        try:
            tc.validate(contract, doc, require_approval=False)
        except tc.SchemaError as exc:
            if "交差" not in str(exc):
                print("FAIL: unexpected schema error", exc, file=sys.stderr)
                return False
        else:
            print("FAIL: overlapping required/forbidden accepted", file=sys.stderr)
            return False
        try:
            tc.validate(contract, doc, require_approval=False, check=True)
        except tc.SchemaError as exc:
            if "交差" not in str(exc):
                print("FAIL: apply-path validate error", exc, file=sys.stderr)
                return False
        else:
            print("FAIL: apply-path validate accepted overlap", file=sys.stderr)
            return False
    return True


def main() -> int:
    checks = {
        "json_key_present_scalar_fatal": json_key_present_scalar_fatal,
        "invalid_utf8_state_fatal_all_clis": invalid_utf8_state_fatal_all_clis,
        "required_forbidden_disjoint_required": required_forbidden_disjoint_required,
    }
    for name, fn in checks.items():
        if not fn():
            print(f"FAIL: {name}", file=sys.stderr)
            return 1
        print(f"PASS: {name}")
    print("[test_contract_loop9] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
