#!/usr/bin/env python3
"""Provisioning plan/apply の read-only・承認・drift・部分失敗回帰。"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import provision_runtime as runtime  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract, write_sealed_manifest  # noqa: E402


def invoke(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = runtime.main(args)
    return code, out.getvalue(), err.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_text = "# fixture\nGo\n"
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text(design_text, encoding="utf-8")
        fp = tc.source_fingerprint(design)
        data = base_contract(fp)
        data["runtime_materialization"]["actions"][0] = {
            "kind": "create-if-missing",
            "target": "go.mod",
            "ownership": "project",
            "conflict_policy": "fail",
            "evidence_ref": "design §9",
            "content": "module example.com/fail\n",
        }
        data["provisioning"]["command_actions"] = [{
            "argv": ["false"],
            "cwd": ".",
            "effects": ["project_write"],
            "writes": ["partial.lock"],
            "evidence_ref": "design §9",
        }]
        manifest, design = write_sealed_manifest(root, data, design_text)
        code, plan_output, _ = invoke(["--plan", "--manifest", str(manifest), "--design-doc", str(design)])
        if code != 0:
            print("FAIL: --plan")
            return 1
        plan = json.loads(plan_output)
        artifact = root / "plan.json"
        artifact.write_text(json.dumps(plan), encoding="utf-8")
        code, _, err = invoke(["--apply", "--manifest", str(manifest), "--design-doc", str(design), "--plan-file", str(artifact)])
        if code != 2 or "approve-plan" not in err:
            print("FAIL: unapproved apply was accepted")
            return 1
        code, out, _ = invoke([
            "--apply", "--manifest", str(manifest), "--design-doc", str(design),
            "--plan-file", str(artifact), "--approve-plan", plan["plan_digest"],
        ])
        report = json.loads(out)
        if code != 1 or report.get("completed") != ["go.mod"]:
            print("FAIL: partial failure report is incomplete", code, report)
            return 1
        plan["actions"] = [a for a in plan["actions"] if a.get("phase") == "command" or a.get("target") != "go.mod"]
        if not plan["actions"]:
            plan["actions"] = plan_output and json.loads(plan_output)["actions"]
        tampered = json.loads(json.dumps(plan))
        for action in tampered["actions"]:
            if action.get("phase") == "file":
                action["preimage"] = "drift"
        artifact.write_text(json.dumps(tampered), encoding="utf-8")
        code, _, err = invoke([
            "--apply", "--manifest", str(manifest), "--design-doc", str(design),
            "--plan-file", str(artifact), "--approve-plan", plan["plan_digest"],
        ])
        if code != 1:
            print("FAIL: plan drift was accepted", err)
            return 1

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_text = "# fixture\nGo\n"
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text(design_text, encoding="utf-8")
        fp = tc.source_fingerprint(design)
        data = base_contract(fp, with_file_action=False)
        data["provisioning"]["preflight_checks"] = []
        data["provisioning"]["command_actions"] = []
        manifest, design = write_sealed_manifest(root, data, design_text)
        code, _, err = invoke(["--preflight", "--manifest", str(manifest), "--design-doc", str(design)])
        if code != 0:
            print("FAIL: policy none empty workspace preflight did not exit 0", err)
            return 1

    print("[test_provision_runtime] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
