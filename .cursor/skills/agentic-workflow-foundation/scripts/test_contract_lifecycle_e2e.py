#!/usr/bin/env python3
"""contract lifecycle / provisioning / consumer の CLI E2E 回帰（A〜F）。"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import provision_runtime as prov  # noqa: E402
import resolve_coderabbit as rc  # noqa: E402
import resolve_domain_docs as rd  # noqa: E402
import resolve_quality_gate as rq  # noqa: E402
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract, fixture_command_action, write_sealed_manifest  # noqa: E402


def invoke_prov(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = prov.main(args)
    return code, out.getvalue(), err.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_text = "# fixture\nGo\n"
        design_path = root / "docs" / "TECH.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(design_text, encoding="utf-8")
        fp = tc.source_fingerprint(design_path)

        contract = base_contract(fp)
        contract["runtime_materialization"]["actions"] = [
            {
                "kind": "json-key-merge",
                "target": "package.json",
                "ownership": "project",
                "conflict_policy": "merge_owned",
                "evidence_ref": "design §9",
                "owned_keys": ["name", "scripts.test"],
                "values": {"name": "fixture", "scripts.test": "echo ok"},
            },
            {
                "kind": "owned-text-render",
                "target": "extra.txt",
                "ownership": "tool",
                "conflict_policy": "fail",
                "evidence_ref": "design §9",
                "content": "line1\nline2\n",
            },
        ]
        contract["provisioning"]["command_actions"] = [fixture_command_action(".provision-marker")]
        manifest, design = write_sealed_manifest(root, contract, design_text)

        # A — provision apply only (no materialize write path)
        pkg = root / "package.json"
        if pkg.exists():
            pkg.unlink()
        code, out, _ = invoke_prov(["--plan", "--manifest", str(manifest), "--design-doc", str(design)])
        if code != 0:
            print("FAIL A: plan", out)
            return 1
        plan = json.loads(out)
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        code, apply_out, _ = invoke_prov([
            "--apply", "--manifest", str(manifest), "--design-doc", str(design),
            "--plan-file", str(plan_path), "--approve-plan", plan["plan_digest"],
        ])
        if code != 0:
            print("FAIL A: apply exit", apply_out)
            return 1
        if not pkg.is_file():
            print("FAIL A: package.json not created")
            return 1
        pkg_data = json.loads(pkg.read_text())
        if pkg_data.get("name") != "fixture" or pkg_data.get("scripts", {}).get("test") != "echo ok":
            print("FAIL A: package.json merge invalid", pkg_data)
            return 1
        extra = root / "extra.txt"
        if not extra.is_file() or extra.read_text(encoding="utf-8") != "line1\nline2\n":
            print("FAIL A: multiline extra.txt bytes mismatch")
            return 1

        # B — file+command 両方空は拒否
        bare = base_contract(fp, with_file_action=False)
        bare["runtime_materialization"]["actions"] = []
        bare["provisioning"]["command_actions"] = []
        bare_root = Path(tempfile.mkdtemp(dir=tmp))
        bare_manifest, bare_design = write_sealed_manifest(bare_root, bare, design_text)
        plan = rp.build_plan(tc.load_approved(bare_manifest, bare_design), bare_root)
        code, report = rp.apply_plan(
            plan,
            tc.load_approved(bare_manifest, bare_design),
            bare_root,
        )
        if code != 2:
            print("FAIL B: empty file+command actions should exit 2", report)
            return 1

        # C
        invalid = base_contract(fp)
        invalid["runtime_materialization"]["actions"][0]["kind"] = "unknown"
        try:
            tc.validate(invalid, design, require_approval=False, check=True)
        except tc.SchemaError:
            pass
        else:
            print("FAIL C: unknown kind accepted")
            return 1

        # D: tampered digest rejected at consumer
        bad = manifest.read_text(encoding="utf-8").replace(
            tc.load_approved(manifest, design)["contract_digest"],
            "0" * 64,
            1,
        )
        manifest.write_text(bad, encoding="utf-8")
        if rq.main(["--manifest", str(manifest)]) == 0:
            print("FAIL D: tampered digest accepted")
            return 1
        manifest, design = write_sealed_manifest(root, contract, design_text)

        # E
        pkg.write_text('{"name":"drift","scripts":{"test":"x","dev":"keep"},"extra":true}\n', encoding="utf-8")
        drift = base_contract(fp, with_file_action=False)
        drift["runtime_materialization"]["actions"] = [{
            "kind": "json-key-merge", "target": "package.json", "ownership": "project",
            "conflict_policy": "fail", "evidence_ref": "x", "owned_keys": ["name"],
            "values": {"name": "fixture"},
        }]
        write_sealed_manifest(root, drift, design_text)
        plan = rp.build_plan(tc.load_approved(manifest, design), root)
        code, report = rp.apply_plan(plan, tc.load_approved(manifest, design), root)
        if code != 2:
            print("FAIL E: conflict not exit 2")
            return 1

        # F
        pkg.write_text('{"name":"old","scripts":{"test":"x","dev":"keep"},"extra":true}\n', encoding="utf-8")
        merge = base_contract(fp, with_file_action=False)
        merge["runtime_materialization"]["actions"] = [{
            "kind": "json-key-merge", "target": "package.json", "ownership": "project",
            "conflict_policy": "merge_owned", "evidence_ref": "x",
            "owned_keys": ["name", "scripts.test"],
            "values": {"name": "fixture", "scripts.test": "echo ok"},
        }]
        write_sealed_manifest(root, merge, design_text)
        rp.apply_file_action(merge["runtime_materialization"]["actions"][0], root)
        data = json.loads(pkg.read_text())
        if data.get("extra") is not True or data.get("name") != "fixture":
            print("FAIL F: non-owned keys not preserved")
            return 1
        if data.get("scripts", {}).get("dev") != "keep":
            print("FAIL F: nested scripts.dev not preserved")
            return 1

        if rc.main(["--manifest", str(manifest)]) != 0 or rd.main(["--manifest", str(manifest)]) != 0:
            print("FAIL: consumers")
            return 1

    print("[test_contract_lifecycle_e2e] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
