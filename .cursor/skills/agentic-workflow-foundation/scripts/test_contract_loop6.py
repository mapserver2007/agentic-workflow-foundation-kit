#!/usr/bin/env python3
"""Step④ loop6: 監査再現テスト（root不変/command/postcondition/schema/isolated E2E）。"""
from __future__ import annotations

import contextlib
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
import provision_runtime as prov  # noqa: E402
import resolve_coderabbit as rc  # noqa: E402
import resolve_domain_docs as rd  # noqa: E402
import resolve_quality_gate as rq  # noqa: E402
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import (  # noqa: E402
    FIXTURE_RUNNER,
    MINIMAL_SEED,
    base_contract,
    fixture_command_action,
    go_lifecycle_contract,
    web_lifecycle_contract,
    write_sealed_manifest,
)
from test_root_snapshot import assert_unchanged, git_tracked_diff, snapshot  # noqa: E402

TECH_SCRIPT = HERE / "tech_contract.py"
ENGINE = HERE / "run_resolved_engine.py"
SKILL_MANIFEST = HERE.parent / "manifest.yaml"


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, str(TECH_SCRIPT), *args],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def _invoke_prov(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = prov.main(args)
    return code, out.getvalue(), err.getvalue()


def runner_root_immutable_twice() -> bool:
    manifest = ROOT / "manifest.yaml"
    design = ROOT / ".cursor" / "docs" / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
    if not manifest.is_file() or not design.is_file():
        print("SKIP runner_root_immutable_twice: root manifest/design absent", file=sys.stderr)
        return True
    before = snapshot()
    git_before = git_tracked_diff()
    for pass_no in (1, 2):
        result = subprocess.run(
            [sys.executable, str(TECH_SCRIPT), "status", "--manifest", str(manifest), "--design-doc", str(design)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"FAIL: root status pass {pass_no}", result.stderr, file=sys.stderr)
            return False
        drift = assert_unchanged(before, snapshot())
        if drift:
            print(f"FAIL: root snapshot drift pass {pass_no}", drift, file=sys.stderr)
            return False
        if git_tracked_diff() != git_before:
            print(f"FAIL: git tracked diff pass {pass_no}", file=sys.stderr)
            return False
    return True


def duplicate_preflight_rejected() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        contract = base_contract(fp, with_file_action=False)
        dup = {
            "kind": "path-exists",
            "target": "go.mod",
            "evidence_ref": "x",
            "guidance": "fixture",
        }
        contract["provisioning"]["preflight_checks"] = [dup, dict(dup)]
        try:
            tc.validate(contract, doc, require_approval=False)
        except tc.SchemaError:
            return True
        print("FAIL: duplicate preflight accepted", file=sys.stderr)
        return False


def command_missing_declared_write_fails() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=False)
        contract["runtime_materialization"]["actions"] = []
        contract["provisioning"]["command_actions"] = [{
            "argv": [sys.executable, str(FIXTURE_RUNNER), "touch", "--root", ".", "--writes", ".provision-marker"],
            "cwd": ".",
            "effects": ["project_write"],
            "writes": [".provision-marker", ".cursor/.runtime/provision-state.json"],
            "postconditions": [{
                "kind": "record-state-digest",
                "marker": ".cursor/.runtime/provision-state.json",
                "paths": [".provision-marker"],
                "evidence_ref": "x",
            }],
            "evidence_ref": "x",
        }]

        def runner_no_write(_argv, _cwd):
            return 0

        manifest, design = write_sealed_manifest(root, contract, "# x\nGo\n")
        approved = tc.load_approved(manifest, design)
        plan = rp.build_plan(approved, root)
        code, report = rp.apply_plan(plan, approved, root, command_runner=runner_no_write)
        if code != 2 or "declared writes missing" not in report.get("recovery", ""):
            print("FAIL: missing declared write", code, report, file=sys.stderr)
            return False
    return True


def command_only_allowed() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        contract = base_contract(fp, with_file_action=False)
        contract["runtime_materialization"]["actions"] = []
        contract["provisioning"]["command_actions"] = [fixture_command_action(".provision-marker")]
        contract["provisioning"]["preflight_checks"] = []
        tc.validate(contract, doc, require_approval=False, check=True)
    return True


def postcondition_marker_reported() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=False)
        contract["runtime_materialization"]["actions"] = []
        contract["provisioning"]["command_actions"] = [fixture_command_action(".provision-marker")]
        contract["provisioning"]["preflight_checks"] = []
        manifest, design = write_sealed_manifest(root, contract, "# x\nGo\n")
        approved = tc.load_approved(manifest, design)
        plan = rp.build_plan(approved, root)
        code, report = rp.apply_plan(plan, approved, root)
        marker = ".cursor/.runtime/provision-state.json"
        if code != 0 or marker not in report.get("changed_targets", []):
            print("FAIL: postcondition marker not reported", report, file=sys.stderr)
            return False
    return True


def marker_version_mismatch() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=True)
        contract["provisioning"]["command_actions"] = []
        contract["provisioning"]["preflight_checks"] = [{
            "kind": "json-value-pattern",
            "target": ".cursor/.runtime/toolchain-state.json",
            "pointer": "pnpm.version",
            "pattern": r"^9\.\d+\.\d+$",
            "evidence_ref": "x",
            "guidance": "version mismatch expected",
        }]
        manifest, design = write_sealed_manifest(root, contract, "# x\n")
        marker = root / ".cursor" / ".runtime" / "toolchain-state.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"pnpm":{"version":"11.0.0"}}\n', encoding="utf-8")
        errors = rp.run_preflight(tc.load_approved(manifest, design), root)
        if not errors or not any("json-value-pattern" in error for error in errors):
            print("FAIL: version mismatch not detected", errors, file=sys.stderr)
            return False
    return True


def all_required_packages_covered() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        contract = base_contract(fp, with_file_action=False)
        contract["runtime_materialization"]["reality"] = {
            "required_packages": ["pkg-a", "pkg-b"],
            "forbidden_packages": [],
        }
        contract["provisioning"]["preflight_checks"] = [{
            "kind": "installed-marker",
            "target": "markers/pkg-a.ok",
            "covers_packages": ["pkg-a"],
            "validation": {"kind": "json-field", "pointer": "name", "expected": "pkg-a"},
            "evidence_ref": "x",
            "guidance": "fixture",
        }]
        try:
            tc.validate(contract, doc, require_approval=False)
        except tc.SchemaError as exc:
            if "preflight 未カバー" in str(exc):
                return True
            print("FAIL: unexpected schema error", exc, file=sys.stderr)
            return False
        print("FAIL: uncovered required_packages accepted", file=sys.stderr)
        return False


def lockfile_state_digest_mismatch() -> bool:
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
            "guidance": "digest mismatch expected",
        }]
        manifest, design = write_sealed_manifest(root, contract, "# x\n")
        marker = root / ".cursor" / ".runtime" / "provision-state.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"digests":{"pnpm-lock.yaml":"deadbeef"}}\n', encoding="utf-8")
        (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        errors = rp.run_preflight(tc.load_approved(manifest, design), root)
        if not errors or not any("state-digests" in error for error in errors):
            print("FAIL: state digest mismatch not detected", errors, file=sys.stderr)
            return False
    return True


def malformed_inputs_no_traceback() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "TECH.md"
        design.write_text("# x\n", encoding="utf-8")
        draft = root / "draft.yaml"
        draft.write_text("tech_contract: [not-a-mapping]\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(TECH_SCRIPT), "validate",
             "--design-doc", str(design), "--draft", str(draft), "--check"],
            capture_output=True,
            text=True,
        )
        combined = result.stdout + result.stderr
        if result.returncode != 2 or "Traceback" in combined:
            print("FAIL: malformed input handling", result.returncode, combined, file=sys.stderr)
            return False
    return True


def _engine_stack(label: str, contract_builder, design_text: str, *, assert_no_package_json: bool) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        isolated = Path(tmp)
        (isolated / ".cursor" / "skills").mkdir(parents=True, exist_ok=True)
        design = isolated / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text(design_text, encoding="utf-8")
        fp = tc.source_fingerprint(design)
        draft = contract_builder(fp)
        draft_path = isolated / "draft.yaml"
        draft_path.write_text("\n".join(tc._dump_yaml({"tech_contract": draft})) + "\n", encoding="utf-8")
        manifest = isolated / "manifest.yaml"
        manifest.write_text(
            "version: 1\n"
            "project:\n"
            "  tech_stack_design_filename: TECH.md\n"
            "  quality_gate:\n"
            "    profile: application\n"
            "    gen_artifact_paths: []\n",
            encoding="utf-8",
        )
        preimage = tc.file_digest(manifest)
        for subcmd, extra in (
            ("validate", ["--check"]),
            ("apply", []),
        ):
            args = [
                subcmd, "--design-doc", str(design), "--draft", str(draft_path),
                "--manifest", str(manifest), "--preimage", preimage,
            ]
            if subcmd == "validate":
                args.extend(extra)
            code, _, err = _run_cli(args)
            if code != 0:
                print(f"FAIL {label} CLI {subcmd}", err, file=sys.stderr)
                return False
            if subcmd == "apply":
                preimage = tc.file_digest(manifest)
        approved = tc.load_approved(manifest, design)
        seed = isolated / "seed.yaml"
        seed.write_text(MINIMAL_SEED, encoding="utf-8")
        for cmd in ("generate", "check"):
            result = subprocess.run(
                [
                    sys.executable, str(ENGINE), cmd,
                    "--seed-manifest", str(SKILL_MANIFEST),
                    "--root-manifest", str(manifest),
                    "--work-root", str(isolated),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"FAIL {label} engine {cmd}", result.stdout, result.stderr, file=sys.stderr)
                return False
        qg = isolated / "bin" / "quality-gate"
        if not qg.is_file():
            print(f"FAIL {label}: bin/quality-gate missing", file=sys.stderr)
            return False
        qg_text = qg.read_text(encoding="utf-8")
        expected_argv = approved["quality_gate"]["test"]["argv"]
        if " ".join(expected_argv) not in qg_text.replace('"', "").replace("'", ""):
            if not all(part in qg_text for part in expected_argv):
                print(f"FAIL {label}: quality-gate argv mismatch", expected_argv, file=sys.stderr)
                return False
        coderabbit = isolated / ".coderabbit.yaml"
        if not coderabbit.is_file():
            print(f"FAIL {label}: .coderabbit.yaml missing", file=sys.stderr)
            return False
        if approved["review"]["coderabbit"]["language"] not in coderabbit.read_text(encoding="utf-8"):
            print(f"FAIL {label}: coderabbit language mismatch", file=sys.stderr)
            return False
        for script in (rd, rc, rq):
            result = subprocess.run(
                [sys.executable, str(script.__file__), "--manifest", str(manifest)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"FAIL {label}: resolver {script.__name__}", result.stderr, file=sys.stderr)
                return False
        lang = approved["domain_docs"]["resolved"]["primary_language"]
        arch = isolated / "docs" / "architecture.md"
        if not arch.is_file() or lang not in arch.read_text(encoding="utf-8"):
            print(f"FAIL {label}: domain docs missing language", file=sys.stderr)
            return False
        if assert_no_package_json and (isolated / "package.json").is_file():
            print(f"FAIL {label}: package.json should be absent", file=sys.stderr)
            return False
    return True


def real_isolated_engine_outputs_web_go() -> bool:
    web_ok = _engine_stack(
        "web",
        web_lifecycle_contract,
        "# Web fixture\nTypeScript\n",
        assert_no_package_json=False,
    )
    go_ok = _engine_stack(
        "go",
        go_lifecycle_contract,
        "# Go fixture\nGo\n",
        assert_no_package_json=True,
    )
    if not web_ok or not go_ok:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# Go fixture\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = go_lifecycle_contract(fp)
        manifest, design = write_sealed_manifest(root, contract, "# Go fixture\nGo\n")
        code, out, _ = _invoke_prov(["--plan", "--manifest", str(manifest), "--design-doc", str(design)])
        if code != 0:
            print("FAIL: isolated provision plan", out, file=sys.stderr)
            return False
        plan = json.loads(out)
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        code, apply_out, _ = _invoke_prov([
            "--apply", "--manifest", str(manifest), "--design-doc", str(design),
            "--plan-file", str(plan_path), "--approve-plan", plan["plan_digest"],
        ])
        if code != 0:
            print("FAIL: isolated provision apply", apply_out, file=sys.stderr)
            return False
        if prov.main(["--preflight", "--manifest", str(manifest), "--design-doc", str(design)]) != 0:
            print("FAIL: isolated provision preflight", file=sys.stderr)
            return False
        if conf.main(["--manifest", str(manifest)]) != 0:
            print("FAIL: isolated provision conformance", file=sys.stderr)
            return False
        go_mod = root / "go.mod"
        expected = "module example.com/go-fixture\n\ngo 1.22\n"
        if not go_mod.is_file() or go_mod.read_text(encoding="utf-8") != expected:
            print("FAIL: go.mod exact bytes", file=sys.stderr)
            return False
        if (root / "package.json").is_file():
            print("FAIL: package.json present in go workspace", file=sys.stderr)
            return False
    return True


def profile_each_line_checked() -> bool:
    result = subprocess.run(
        [sys.executable, str(HERE / "test_profile_selector_static.py")],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout, result.stderr, file=sys.stderr)
        return False
    text = (HERE / "test_profile_selector_static.py").read_text(encoding="utf-8")
    if 'if "{{session.verification.gate_command}}" in text:' in text:
        print("FAIL: profile test still skips whole files", file=sys.stderr)
        return False
    return True


def main() -> int:
    checks = {
        "duplicate_preflight_rejected": duplicate_preflight_rejected,
        "command_missing_declared_write_fails": command_missing_declared_write_fails,
        "command_only_allowed": command_only_allowed,
        "postcondition_marker_reported": postcondition_marker_reported,
        "marker_version_mismatch": marker_version_mismatch,
        "all_required_packages_covered": all_required_packages_covered,
        "lockfile_state_digest_mismatch": lockfile_state_digest_mismatch,
        "malformed_inputs_no_traceback": malformed_inputs_no_traceback,
        "real_isolated_engine_outputs_web_go": real_isolated_engine_outputs_web_go,
        "profile_each_line_checked": profile_each_line_checked,
        "runner_root_immutable_twice": runner_root_immutable_twice,
    }
    for name, fn in checks.items():
        if not fn():
            print(f"FAIL: {name}", file=sys.stderr)
            return 1
        print(f"PASS: {name}")
    print("[test_contract_loop6] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
