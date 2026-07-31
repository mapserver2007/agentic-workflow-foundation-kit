#!/usr/bin/env python3
"""Web/Go fixture の subprocess CLI validate/apply + isolated engine E2E。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_tech_stack_conformance as conf  # noqa: E402
import provision_runtime as prov  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import (  # noqa: E402
    go_lifecycle_contract,
    web_lifecycle_contract,
)

TECH_SCRIPT = HERE / "tech_contract.py"


def _cli(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, str(TECH_SCRIPT), *args],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def run_stack(label: str, contract_builder, design_text: str, expected_file: str, expected_bytes: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_path = root / "docs" / "TECH.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(design_text, encoding="utf-8")
        fp = tc.source_fingerprint(design_path)
        draft = contract_builder(fp)
        draft_path = root / "draft.yaml"
        draft_path.write_text("\n".join(tc._dump_yaml({"tech_contract": draft})) + "\n", encoding="utf-8")

        manifest = root / "manifest.yaml"
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
        code, _, err = _cli([
            "validate", "--design-doc", str(design_path), "--draft", str(draft_path), "--check",
        ])
        if code != 0:
            print(f"FAIL {label}: CLI validate --check", err)
            return 1
        code, _, err = _cli([
            "apply", "--design-doc", str(design_path), "--draft", str(draft_path),
            "--manifest", str(manifest), "--preimage", preimage,
        ])
        if code != 0:
            print(f"FAIL {label}: CLI apply", err)
            return 1
        tc.load_approved(manifest, design_path)

        code, out, err = _cli(["status", "--manifest", str(manifest), "--design-doc", str(design_path)])
        if code != 0:
            print(f"FAIL {label}: CLI status", err)
            return 1

        plan_result = subprocess.run(
            [sys.executable, str(HERE / "provision_runtime.py"),
             "--plan", "--manifest", str(manifest), "--design-doc", str(design_path)],
            capture_output=True,
            text=True,
        )
        if plan_result.returncode != 0:
            print(f"FAIL {label}: plan", plan_result.stderr)
            return 1
        plan = json.loads(plan_result.stdout)
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        apply_result = subprocess.run(
            [sys.executable, str(HERE / "provision_runtime.py"),
             "--apply", "--manifest", str(manifest), "--design-doc", str(design_path),
             "--plan-file", str(plan_path), "--approve-plan", plan["plan_digest"]],
            capture_output=True,
            text=True,
        )
        if apply_result.returncode != 0:
            print(f"FAIL {label}: apply", apply_result.stdout, apply_result.stderr)
            return 1

        if prov.main(["--preflight", "--manifest", str(manifest), "--design-doc", str(design_path)]) != 0:
            print(f"FAIL {label}: preflight")
            return 1
        if conf.main(["--manifest", str(manifest)]) != 0:
            print(f"FAIL {label}: conformance")
            return 1

        target = root / expected_file
        if not target.is_file() or target.read_text(encoding="utf-8") != expected_bytes:
            print(f"FAIL {label}: expected exact bytes in {expected_file}")
            return 1

    print(f"PASS {label}")
    return 0


def main() -> int:
    web_design = "# Web fixture\nTypeScript\n"
    go_design = "# Go fixture\nGo\n"
    go_bytes = "module example.com/go-fixture\n\ngo 1.22\n"
    web_pkg = json.dumps({"name": "fixture-web", "scripts": {"test": "echo ok"}}, indent=2) + "\n"
    if run_stack("web", web_lifecycle_contract, web_design, "package.json", web_pkg) != 0:
        return 1
    if run_stack("go", go_lifecycle_contract, go_design, "go.mod", go_bytes) != 0:
        return 1
    print("[test_full_lifecycle_e2e] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
