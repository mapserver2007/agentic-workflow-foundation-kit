#!/usr/bin/env python3
"""Step④ loop4: pin round-trip / preflight / merge / CLI E2E 回帰。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract  # noqa: E402

TECH_SCRIPT = HERE / "tech_contract.py"


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, str(TECH_SCRIPT), *args],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_multiline_pin_roundtrip(root: Path, design: Path, fp: str) -> bool:
    contract = base_contract(fp, with_file_action=False)
    contract["runtime_materialization"]["actions"] = [{
        "kind": "owned-text-render",
        "target": "pnpm-workspace.yaml",
        "ownership": "project",
        "conflict_policy": "fail",
        "evidence_ref": "design §9",
        "content": "packages:\n  - \"apps/*\"\nallowBuilds:\n  esbuild: true\n",
    }, {
        "kind": "owned-text-render",
        "target": "tsconfig.json",
        "ownership": "project",
        "conflict_policy": "fail",
        "evidence_ref": "design §9",
        "content": '{\n  "compilerOptions": {\n    "strict": true\n  }\n}\n',
    }]
    manifest = root / "manifest.yaml"
    prefix = "# preserved prefix\nproject:\n  name: kit\n\n"
    manifest.write_text(prefix, encoding="utf-8")
    preimage = tc.file_digest(manifest)
    tc.seal_contract(manifest, contract, preimage)
    text = manifest.read_text(encoding="utf-8")
    if not text.startswith(prefix):
        print("FAIL: prefix bytes not preserved", file=sys.stderr)
        return False
    if "packages:\n  - \"apps/*\"" in text and "content: |" not in text:
        print("FAIL: multiline not block literal", file=sys.stderr)
        return False
    loaded = tc.load_approved(manifest, design)
    for action in rp.collect_file_actions(loaded):
        orig = next(a for a in rp.collect_file_actions(contract) if a["target"] == action["target"])
        rendered = rp.render_file_bytes(action, root)
        expected = rp.render_file_bytes(orig, root)
        if rendered != expected:
            print(f"FAIL: byte mismatch for {action['target']}", file=sys.stderr)
            return False
    return True


def test_block_replacement(root: Path, design: Path, fp: str) -> bool:
    old_block = (
        "tech_contract:\n"
        "  schema_version: 1\n"
        "  classification:\n"
        "    profile: application\n"
        "    evidence_ref: old\n"
        "  quality_gate:\n"
        "    gen_artifact_paths: []\n"
        "    gen:\n"
        "      argv: [old]\n"
        "      evidence_ref: old\n"
        "      contract: [old]\n"
        "    build:\n"
        "      argv: [old]\n"
        "      evidence_ref: old\n"
        "      contract: [old]\n"
        "    lint:\n"
        "      argv: [old]\n"
        "      evidence_ref: old\n"
        "      contract: [old]\n"
        "    test:\n"
        "      argv: [old]\n"
        "      evidence_ref: old\n"
        "      contract: [old]\n"
        "  runtime_materialization:\n"
        "    actions: []\n"
        "  review:\n"
        "    evidence_ref: old\n"
        "    coderabbit:\n"
        "      enabled: true\n"
        "      language: ja\n"
        "      tools_enabled: []\n"
        "      tools_disabled: []\n"
        "      path_filters: []\n"
        "      path_instructions: []\n"
        "  domain_docs:\n"
        "    evidence_ref: old\n"
        "    resolved:\n"
        "      primary_language: Old\n"
        "      api_style: old\n"
        "      database: none\n"
        "      architecture: old\n"
        "      framework: old\n"
        "      test_framework: old\n"
        "      package_manager: old\n"
        "      spec_sections: []\n"
        "      architecture_sections: []\n"
        "      api_sections: []\n"
        "      data_model_sections: []\n"
        "      coding_standards_sections: []\n"
        "      workflow_sections: []\n"
        "  provisioning:\n"
        "    policy: explicit\n"
        "    evidence_ref: old\n"
        "    preflight_checks: []\n"
        "    command_actions: []\n"
        "  source_fingerprint: deadbeef\n"
        "  contract_digest: \"0\" * 64\n"
        "  approval:\n"
        "    status: approved\n"
        "    digest: dead\n"
        "    schema_version: 1\n"
    )
    suffix = "\nframework:\n  version: 99\n"
    manifest = root / "manifest.yaml"
    manifest.write_text(old_block + suffix, encoding="utf-8")
    contract = base_contract(fp, with_file_action=False)
    contract["provisioning"]["preflight_checks"] = []
    preimage = tc.file_digest(manifest)
    tc.seal_contract(manifest, contract, preimage)
    text = manifest.read_text(encoding="utf-8")
    if text.count("tech_contract:") != 1:
        print("FAIL: tech_contract block count is not one", file=sys.stderr)
        return False
    if "argv: [old]" in text or "evidence_ref: old" in text:
        print("FAIL: old block remnants", file=sys.stderr)
        return False
    if not text.endswith(suffix.lstrip("\n")):
        print("FAIL: suffix not preserved", file=sys.stderr)
        return False
    return True


def test_preflight_no_side_effects(root: Path, design: Path, fp: str) -> bool:
    contract = base_contract(fp, with_file_action=False)
    contract["provisioning"]["preflight_checks"] = [{
        "kind": "executable-exists",
        "executable": "nonexistent-sentinel-cmd-loop4",
        "evidence_ref": "design §9",
        "guidance": "fixture",
    }]
    contract["provisioning"]["command_actions"] = []
    contract["runtime_materialization"]["actions"] = []
    manifest = root / "manifest.yaml"
    manifest.write_text(
        "version: 1\nproject:\n  tech_stack_design_filename: TECH.md\n",
        encoding="utf-8",
    )
    tc.seal_contract(manifest, contract, tc.file_digest(manifest))
    sentinel = root / "sentinel"
    errors = rp.run_preflight(tc.load_approved(manifest, design), root)
    if sentinel.exists():
        print("FAIL: preflight created sentinel", file=sys.stderr)
        return False
    if not errors:
        print("FAIL: missing executable not reported", file=sys.stderr)
        return False
    return True


def test_nested_merge_preserves(root: Path) -> bool:
    pkg = root / "package.json"
    pkg.write_text(
        '{"name":"old","scripts":{"dev":"keep","test":"old"},"extra":true}\n',
        encoding="utf-8",
    )
    action = {
        "kind": "json-key-merge",
        "target": "package.json",
        "ownership": "project",
        "conflict_policy": "merge_owned",
        "evidence_ref": "x",
        "owned_keys": ["name", "scripts.test"],
        "values": {"name": "new", "scripts.test": "echo ok"},
    }
    rp.apply_file_action(action, root)
    data = json.loads(pkg.read_text())
    if data.get("scripts", {}).get("dev") != "keep" or data.get("extra") is not True:
        print("FAIL: nested keys not preserved", file=sys.stderr)
        return False
    if data.get("name") != "new":
        print("FAIL: owned name not updated", file=sys.stderr)
        return False
    return True


def test_command_writes_on_failure(root: Path, design: Path, fp: str) -> bool:
    contract = base_contract(fp, with_file_action=False)
    contract["runtime_materialization"]["actions"] = [{
        "kind": "create-if-missing",
        "target": "go.mod",
        "ownership": "project",
        "conflict_policy": "fail",
        "evidence_ref": "x",
        "content": "module fail\n",
    }]
    contract["provisioning"]["command_actions"] = [{
        "argv": ["false"],
        "cwd": ".",
        "effects": ["lockfile_write"],
        "writes": ["partial.lock"],
        "evidence_ref": "x",
    }]
    manifest = root / "manifest.yaml"
    manifest.write_text("version: 1\nproject:\n  tech_stack_design_filename: TECH.md\n", encoding="utf-8")
    tc.seal_contract(manifest, contract, tc.file_digest(manifest))
    approved = tc.load_approved(manifest, design)
    plan = rp.build_plan(approved, root)

    def runner(_argv, cwd):
        (cwd / "partial.lock").write_text("partial\n", encoding="utf-8")
        return 1

    code, report = rp.apply_plan(plan, approved, root, command_runner=runner)
    if code != 1:
        print("FAIL: command failure exit", code, report, file=sys.stderr)
        return False
    if "partial.lock" not in report.get("changed_targets", []):
        print("FAIL: partial write not in changed_targets", report, file=sys.stderr)
        return False
    if report.get("completed") != ["go.mod"]:
        print("FAIL: completed order wrong", report, file=sys.stderr)
        return False
    return True


def test_cli_validate_apply(root: Path, design: Path, fp: str) -> bool:
    contract = base_contract(fp, with_file_action=False)
    draft_path = root / "draft.yaml"
    lines = tc._dump_yaml({"tech_contract": contract})
    draft_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = root / "manifest.yaml"
    manifest.write_text("version: 1\nproject:\n  tech_stack_design_filename: TECH.md\n", encoding="utf-8")
    preimage = tc.file_digest(manifest)
    code, out, err = _run_cli([
        "validate", "--design-doc", str(design), "--draft", str(draft_path), "--check",
    ])
    if code != 0:
        print("FAIL: validate --check", err, file=sys.stderr)
        return False
    code, out, err = _run_cli([
        "apply", "--design-doc", str(design), "--draft", str(draft_path),
        "--manifest", str(manifest), "--preimage", preimage,
    ])
    if code != 0:
        print("FAIL: apply CLI", err, file=sys.stderr)
        return False
    if not draft_path.exists():
        pass  # draft removed on success
    tc.load_approved(manifest, design)
    return True


def test_materialize_readonly(root: Path, design: Path, fp: str) -> bool:
    contract = base_contract(fp)
    manifest = root / "manifest.yaml"
    manifest.write_text("version: 1\nproject:\n  tech_stack_design_filename: TECH.md\n", encoding="utf-8")
    tc.seal_contract(manifest, contract, tc.file_digest(manifest))
    result = subprocess.run(
        [sys.executable, str(HERE / "materialize_runtime.py"),
         "--manifest", str(manifest), "--design-doc", str(design)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 2:
        print("FAIL: materialize without --check accepted", result.stderr, file=sys.stderr)
        return False
    return True


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# fixture\nGo\n", encoding="utf-8")
        fp = tc.source_fingerprint(design)
        checks = [
            test_multiline_pin_roundtrip(root, design, fp),
            test_block_replacement(root, design, fp),
            test_preflight_no_side_effects(root, design, fp),
            test_nested_merge_preserves(root),
            test_command_writes_on_failure(root, design, fp),
            test_cli_validate_apply(root, design, fp),
            test_materialize_readonly(root, design, fp),
        ]
        if not all(checks):
            return 1
    print("[test_contract_loop4] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
