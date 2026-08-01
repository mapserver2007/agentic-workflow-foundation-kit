#!/usr/bin/env python3
"""Step④ loop5: 監査再現テスト（pin/schema/path/preflight/E2E/profile）。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
import provision_runtime as prov  # noqa: E402
import resolve_coderabbit as rc  # noqa: E402
import resolve_domain_docs as rd  # noqa: E402
import resolve_quality_gate as rq  # noqa: E402
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import (  # noqa: E402
    WEB_PNPM_WS,
    WEB_TSCONFIG,
    base_contract,
    consumer_contract,
    go_lifecycle_contract,
    web_lifecycle_contract,
    write_sealed_manifest,
)

TECH_SCRIPT = HERE / "tech_contract.py"
ENGINE = HERE / "run_resolved_engine.py"
SKILL_MANIFEST = HERE.parent / "manifest.yaml"

PNPM_WS = WEB_PNPM_WS
TSCONFIG = WEB_TSCONFIG


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


def root_multiline_exact_bytes() -> bool:
    manifest = ROOT / "manifest.yaml"
    design = ROOT / ".cursor" / "docs" / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
    if not manifest.is_file():
        print("SKIP root_multiline_exact_bytes: no root manifest", file=sys.stderr)
        return True
    contract = tc.load_approved(manifest, design)
    for action in rp.collect_file_actions(contract):
        if action["target"] == "pnpm-workspace.yaml":
            if action["content"] != PNPM_WS:
                print("FAIL: pnpm-workspace content not real newlines", file=sys.stderr)
                return False
            if "\\n" in manifest.read_text(encoding="utf-8").split("pnpm-workspace.yaml", 1)[-1][:200]:
                print("FAIL: manifest still has literal \\\\n", file=sys.stderr)
                return False
        if action["target"] == "tsconfig.json" and action["content"] != TSCONFIG:
            print("FAIL: tsconfig content mismatch", file=sys.stderr)
            return False
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_path = root / "docs" / "TECH.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text("# Web\nTypeScript\n", encoding="utf-8")
        fp = tc.source_fingerprint(design_path)
        draft = web_lifecycle_contract(fp)
        draft["runtime_materialization"]["actions"] = contract["runtime_materialization"]["actions"]
        draft["provisioning"]["preflight_checks"] = []
        draft["provisioning"]["command_actions"] = []
        write_sealed_manifest(root, draft, "# Web\nTypeScript\n")
        approved = tc.load_approved(root / "manifest.yaml", design_path)
        plan = rp.build_plan(approved, root)
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        code, apply_out, _ = _invoke_prov([
            "--apply", "--manifest", str(root / "manifest.yaml"), "--design-doc", str(design_path),
            "--plan-file", str(plan_path), "--approve-plan", plan["plan_digest"],
        ])
        if code != 0:
            print("FAIL: provision apply", apply_out, file=sys.stderr)
            return False
        ws = root / "pnpm-workspace.yaml"
        ts = root / "tsconfig.json"
        if ws.read_bytes() != PNPM_WS.encode("utf-8"):
            print("FAIL: pnpm-workspace exact bytes", file=sys.stderr)
            return False
        if ts.read_bytes() != TSCONFIG.encode("utf-8"):
            print("FAIL: tsconfig exact bytes", file=sys.stderr)
            return False
        json.loads(ts.read_text(encoding="utf-8"))
        if "packages:" not in ws.read_text(encoding="utf-8"):
            print("FAIL: pnpm-workspace parse", file=sys.stderr)
            return False
    return True


def mixed_newline_existing_block_sealed() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=False)
        contract["provisioning"]["policy"] = "explicit"
        contract["runtime_materialization"]["actions"] = [{
            "kind": "owned-text-render",
            "target": "mixed.txt",
            "ownership": "project",
            "conflict_policy": "fail",
            "evidence_ref": "x",
            "content": "line1\nline2\nline3\n",
        }]
        prefix = "# head\r\nproject:\r\n  n: 1\r\n\r\n"
        suffix = "\r\nframework:\r\n  v: 2\r\n"
        manifest = root / "manifest.yaml"
        manifest.write_bytes(prefix.encode("utf-8") + b"tech_contract:\n  schema_version: 0\n" + suffix.encode("utf-8"))
        preimage = tc.file_digest(manifest)
        before = manifest.read_bytes()
        tc.seal_contract(manifest, contract, preimage)
        after = manifest.read_bytes()
        if not after.startswith(prefix.encode("utf-8")):
            print("FAIL: CRLF prefix bytes", file=sys.stderr)
            return False
        if not after.endswith(suffix.encode("utf-8")):
            print("FAIL: CRLF suffix bytes", file=sys.stderr)
            return False
        if b"schema_version: 0" in after:
            print("FAIL: old block remnant", file=sys.stderr)
            return False
        tc.load_approved(manifest, design)
        loaded = rp.collect_file_actions(tc.load_approved(manifest, design))[0]
        if loaded["content"] != contract["runtime_materialization"]["actions"][0]["content"]:
            print("FAIL: mixed newline round-trip", file=sys.stderr)
            return False
    return True


def nested_schema_rejection() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        doc = root / "TECH.md"
        doc.write_text("# x\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        bad = base_contract(fp, with_file_action=False)
        bad["review"]["coderabbit"]["unknown_key"] = True
        try:
            tc.validate(bad, doc, require_approval=False)
        except tc.SchemaError:
            pass
        else:
            print("FAIL: unknown coderabbit key accepted", file=sys.stderr)
            return False
        bad2 = base_contract(fp, with_file_action=False)
        bad2["quality_gate"]["gen_artifact_paths"] = ["../escape"]
        try:
            tc.validate(bad2, doc, require_approval=False)
        except tc.SchemaError:
            pass
        else:
            print("FAIL: gen path traversal accepted", file=sys.stderr)
            return False
        bad3 = base_contract(fp, with_file_action=False)
        bad3["provisioning"]["policy"] = "explicit"
        bad3["provisioning"]["command_actions"] = [{
            "argv": ["true"], "cwd": ".", "effects": ["project_write"], "evidence_ref": "x",
        }]
        try:
            tc.validate(bad3, doc, require_approval=False)
        except tc.SchemaError:
            pass
        else:
            print("FAIL: undeclared writes accepted", file=sys.stderr)
            return False
        c1 = base_contract(fp, with_file_action=False)
        c1["provisioning"]["policy"] = "explicit"
        d1 = tc.projection_digest(c1)
        c1["runtime_materialization"]["actions"] = [{
            "kind": "create-if-missing", "target": "x.txt", "ownership": "project",
            "conflict_policy": "fail", "evidence_ref": "x", "content": "a\n",
        }]
        if tc.projection_digest(c1) == d1:
            print("FAIL: projection_digest unchanged on file payload", file=sys.stderr)
            return False
    return True


def symlink_escape_rejection() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        with tempfile.TemporaryDirectory() as outside_tmp:
            outside = Path(outside_tmp)
            (outside / "secret.txt").write_text("secret\n", encoding="utf-8")
            link = root / "escape-link"
            link.symlink_to(outside)
            action = {
                "kind": "owned-text-render",
                "target": "escape-link/secret.txt",
                "ownership": "project",
                "conflict_policy": "fail",
                "evidence_ref": "x",
                "content": "hack\n",
            }
            try:
                rp.apply_file_action(action, root)
            except rp.PathSafetyError:
                return True
            print("FAIL: symlink escape allowed", file=sys.stderr)
            return False


def preflight_no_subprocess_and_version_marker() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp, with_file_action=False)
        contract["provisioning"]["policy"] = "explicit"
        contract["runtime_materialization"]["actions"] = [{
            "kind": "create-if-missing", "target": "package.json", "ownership": "project",
            "conflict_policy": "fail", "evidence_ref": "x",
            "content": '{"name":"x","packageManager":"pnpm@9.0.0"}\n',
        }]
        contract["provisioning"]["preflight_checks"] = [
            {
                "kind": "json-value-pattern",
                "target": ".cursor/.runtime/toolchain-state.json",
                "pointer": "pnpm.version",
                "pattern": r"\d+\.\d+\.\d+",
                "evidence_ref": "x",
                "guidance": "apply first",
            },
            {
                "kind": "lockfile-present",
                "target": "pnpm-lock.yaml",
                "evidence_ref": "x",
                "guidance": "apply first",
            },
        ]
        contract["provisioning"]["command_actions"] = []
        manifest, design = write_sealed_manifest(root, contract, "# x\n")
        errors = rp.run_preflight(tc.load_approved(manifest, design), root)
        if not errors:
            print("FAIL: preflight should fail before marker", file=sys.stderr)
            return False
        marker = root / ".cursor" / ".runtime" / "toolchain-state.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"pnpm":{"version":"9.1.0"}}\n', encoding="utf-8")
        (root / "pnpm-lock.yaml").write_text("lock:\n", encoding="utf-8")
        errors2 = rp.run_preflight(tc.load_approved(manifest, design), root)
        if errors2:
            print("FAIL: preflight should pass with marker", errors2, file=sys.stderr)
            return False
    return True


def missing_executable_no_traceback_exit2() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp)
        contract["provisioning"]["command_actions"] = [{
            "argv": ["nonexistent-loop5-cmd-xyz"],
            "cwd": ".",
            "effects": ["host_write"],
            "writes": [".cursor/.runtime/host-marker.json"],
            "postconditions": [{
                "kind": "record-state-digest",
                "marker": ".cursor/.runtime/host-marker.json",
                "paths": ["package.json"],
                "evidence_ref": "x",
            }],
            "evidence_ref": "x",
        }]
        manifest, design = write_sealed_manifest(root, contract, "# x\nGo\n")
        approved = tc.load_approved(manifest, design)
        plan = rp.build_plan(approved, root)
        code, report = rp.apply_plan(plan, approved, root)
        if code != 2 or "Traceback" in str(report):
            print("FAIL: missing executable handling", code, report, file=sys.stderr)
            return False
        result = subprocess.run(
            [sys.executable, str(HERE / "provision_runtime.py"),
             "--preflight", "--manifest", str(manifest), "--design-doc", str(design)],
            capture_output=True, text=True,
        )
        if "Traceback" in result.stderr + result.stdout:
            print("FAIL: preflight traceback", file=sys.stderr)
            return False
    return True


def undeclared_writes_schema_rejection() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "TECH.md"
        doc.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(doc)
        bad = base_contract(fp, with_file_action=False)
        bad["provisioning"]["policy"] = "explicit"
        bad["provisioning"]["command_actions"] = [{
            "argv": ["true"], "cwd": ".", "effects": ["lockfile_write"], "evidence_ref": "x",
        }]
        try:
            tc.validate(bad, doc, require_approval=False)
        except tc.SchemaError:
            return True
        print("FAIL: schema accepted missing writes", file=sys.stderr)
        return False


def declared_partial_write_report() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp)
        contract["provisioning"]["command_actions"] = [{
            "argv": ["false"],
            "cwd": ".",
            "effects": ["lockfile_write"],
            "writes": ["partial.lock"],
            "evidence_ref": "x",
        }]

        def runner(_argv, cwd):
            (cwd / "partial.lock").write_text("x\n", encoding="utf-8")
            return 1

        manifest, design = write_sealed_manifest(root, contract, "# x\nGo\n")
        approved = tc.load_approved(manifest, design)
        plan = rp.build_plan(approved, root)
        code, report = rp.apply_plan(plan, approved, root, command_runner=runner)
        if code != 1 or "partial.lock" not in report.get("changed_targets", []):
            print("FAIL: partial write report", report, file=sys.stderr)
            return False
    return True


def real_cli_yaml_roundtrip_web_go() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for label, builder, design_text in (
            ("web", web_lifecycle_contract, "# Web\nTypeScript\n"),
            ("go", go_lifecycle_contract, "# Go\nGo\n"),
        ):
            design = root / f"{label}-TECH.md"
            design.write_text(design_text, encoding="utf-8")
            fp = tc.source_fingerprint(design)
            draft = builder(fp)
            draft_path = root / f"{label}-draft.yaml"
            draft_path.write_text("\n".join(tc._dump_yaml({"tech_contract": draft})) + "\n", encoding="utf-8")
            manifest = root / f"{label}-manifest.yaml"
            manifest.write_text(
                "version: 1\nproject:\n  tech_stack_design_filename: TECH.md\n", encoding="utf-8"
            )
            preimage = tc.file_digest(manifest)
            code, _, err = _run_cli([
                "validate", "--design-doc", str(design), "--draft", str(draft_path), "--check",
            ])
            if code != 0:
                print(f"FAIL {label} validate", err, file=sys.stderr)
                return False
            code, _, err = _run_cli([
                "apply", "--design-doc", str(design), "--draft", str(draft_path),
                "--manifest", str(manifest), "--preimage", preimage,
            ])
            if code != 0:
                print(f"FAIL {label} apply", err, file=sys.stderr)
                return False
            tc.load_approved(manifest, design)
    return True


def isolated_engine_generated_outputs() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# fixture\nTypeScript\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = consumer_contract(fp, "TypeScript", "pnpm")
        manifest, design = write_sealed_manifest(root, contract, "# fixture\nTypeScript\n")
        for script in (rc, rd, rq):
            result = subprocess.run(
                [sys.executable, str(script.__file__), "--manifest", str(manifest)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print("FAIL: resolver", script.__name__, result.stderr, file=sys.stderr)
                return False
        out = manifest.read_text(encoding="utf-8")
        if 'gate_command: "bin/quality-gate verify"' not in out:
            print("FAIL: quality gate projection", file=sys.stderr)
            return False
        if 'primary_language: "TypeScript"' not in out:
            print("FAIL: domain projection missing", file=sys.stderr)
            return False
    return True


def regenerate_drift_check() -> bool:
    gen = subprocess.run(
        [sys.executable, str(ENGINE), "generate"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if gen.returncode != 0:
        print("FAIL: run_resolved_engine generate", gen.stderr, file=sys.stderr)
        return False
    check = subprocess.run(
        [sys.executable, str(ENGINE), "check"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if check.returncode != 0:
        print("FAIL: run_resolved_engine check after generate", check.stdout, check.stderr, file=sys.stderr)
        return False
    qg = ROOT / "bin" / "quality-gate"
    if not qg.is_file() or "pnpm" not in qg.read_text(encoding="utf-8"):
        print("FAIL: bin/quality-gate missing contract argv", file=sys.stderr)
        return False
    coderabbit = ROOT / ".coderabbit.yaml"
    if not coderabbit.is_file():
        print("FAIL: .coderabbit.yaml missing", file=sys.stderr)
        return False
    return True


def profile_line_level_hardcode() -> bool:
    result = subprocess.run(
        [sys.executable, str(HERE / "test_profile_selector_static.py")],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout, result.stderr, file=sys.stderr)
        return False
    return True


def gen_paths_missing_empty_nonempty() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# x\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        doc = design
        missing = base_contract(fp, with_file_action=False)
        del missing["quality_gate"]["gen_artifact_paths"]
        try:
            tc.validate(missing, doc, require_approval=False)
        except tc.SchemaError:
            pass
        else:
            print("FAIL: missing gen_artifact_paths accepted", file=sys.stderr)
            return False
        empty = base_contract(fp, with_file_action=False)
        empty["quality_gate"]["gen_artifact_paths"] = []
        tc.validate(empty, doc, require_approval=False)
        manifest, _ = write_sealed_manifest(root, empty, "# x\n")
        result = subprocess.run(
            [sys.executable, str(rq.__file__), "--manifest", str(manifest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print("FAIL: empty gen paths resolve", result.stderr, file=sys.stderr)
            return False
        nonempty = base_contract(fp, with_file_action=False)
        nonempty["quality_gate"]["gen_artifact_paths"] = ["generated/a.ts", "generated/b.ts"]
        tc.validate(nonempty, doc, require_approval=False)
        manifest2 = root / "manifest2.yaml"
        manifest2.write_text(manifest.read_text(), encoding="utf-8")
        tc.seal_contract(manifest2, nonempty, tc.file_digest(manifest2))
        result2 = subprocess.run(
            [sys.executable, str(rq.__file__), "--manifest", str(manifest2)],
            capture_output=True, text=True,
        )
        if result2.returncode != 0 or "generated/a.ts" not in manifest2.read_text():
            print("FAIL: nonempty gen paths resolve", result2.stderr, file=sys.stderr)
            return False
    return True


def main() -> int:
    checks = {
        "root_multiline_exact_bytes": root_multiline_exact_bytes,
        "mixed_newline_existing_block_sealed": mixed_newline_existing_block_sealed,
        "nested_schema_rejection": nested_schema_rejection,
        "symlink_escape_rejection": symlink_escape_rejection,
        "preflight_no_subprocess_and_version_marker": preflight_no_subprocess_and_version_marker,
        "missing_executable_no_traceback_exit2": missing_executable_no_traceback_exit2,
        "undeclared_writes_schema_rejection": undeclared_writes_schema_rejection,
        "declared_partial_write_report": declared_partial_write_report,
        "real_cli_yaml_roundtrip_web_go": real_cli_yaml_roundtrip_web_go,
        "isolated_engine_generated_outputs": isolated_engine_generated_outputs,
        "profile_line_level_hardcode": profile_line_level_hardcode,
        "gen_paths_missing_empty_nonempty": gen_paths_missing_empty_nonempty,
        "regenerate_drift_check": regenerate_drift_check,
    }
    for name, fn in checks.items():
        if not fn():
            print(f"FAIL: {name}", file=sys.stderr)
            return 1
        print(f"PASS: {name}")
    print("[test_contract_loop5] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
