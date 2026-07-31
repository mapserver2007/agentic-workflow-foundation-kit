#!/usr/bin/env python3
"""resolve_quality_gate.py の最小 fixture テスト。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RESOLVER = HERE / "resolve_quality_gate.py"
GENLIB_DIR = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
if str(GENLIB_DIR) not in sys.path:
    sys.path.insert(0, str(GENLIB_DIR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import genlib  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import write_quality_gate_manifest  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest, _ = write_quality_gate_manifest(root)
        env = dict(os.environ)
        result = subprocess.run(
            [sys.executable, str(RESOLVER), "--manifest", str(manifest)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return result.returncode
        out = manifest.read_text(encoding="utf-8")
        expected = [
            'gen_cmd: "pnpm run gen"',
            'build_cmd: "pnpm run build"',
            'lint_cmd: "pnpm run lint"',
            'test_cmd: "pnpm run test"',
            'profile: "application"',
            'gate_command: "bin/quality-gate verify"',
        ]
        missing = [needle for needle in expected if needle not in out]
        if missing:
            print(f"missing expected content: {missing}", file=sys.stderr)
            return 1
        if "quality_gate_contract:" in out:
            print("quality_gate_contract must not be persisted in root manifest", file=sys.stderr)
            return 1
        if 'gate_command: "pnpm run' in out:
            print("gate_command must use wrapper, not raw pnpm commands", file=sys.stderr)
            return 1

        parsed = genlib.load_manifest(str(manifest))
        contract = parsed["tech_contract"]["quality_gate"]
        contract_lines = sum(
            len(contract[gate]["contract"])
            for gate in ("gen", "build", "lint", "test")
            if isinstance(contract.get(gate), dict)
        )
        if contract_lines != 4:
            print(f"expected 4 contract lines, got {contract_lines}", file=sys.stderr)
            return 1
        if contract["gen"]["contract"][0] != "OpenAPI bundle を生成し、bundle 成功を検証する":
            print("unexpected gen contract content", file=sys.stderr)
            return 1
        if contract["test"]["argv"] != ["pnpm", "run", "test"]:
            print("unexpected test argv", file=sys.stderr)
            return 1
        if parsed["tech_contract"]["quality_gate"].get("gen_artifact_paths") != ["generated/api.ts"]:
            print("tech_contract gen_artifact_paths mismatch", file=sys.stderr)
            return 1
        if 'gen_artifact_paths:\n      - "generated/api.ts"' not in out:
            print("project gen_artifact_paths was not preserved", file=sys.stderr)
            return 1

        check = subprocess.run(
            [sys.executable, str(RESOLVER), "--manifest", str(manifest), "--check"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if check.returncode != 0:
            print(check.stdout)
            print(check.stderr, file=sys.stderr)
            return check.returncode
        loaded = tc.load_approved(manifest, root / "docs" / "TECH.md")
        bare = tc._bare_contract(loaded)
        del bare["quality_gate"]["gen_artifact_paths"]
        try:
            tc.validate(bare, root / "docs" / "TECH.md", require_approval=False)
        except tc.SchemaError:
            pass
        else:
            print("missing contract gen_artifact_paths must fail schema", file=sys.stderr)
            return 1
        manifest, design = write_quality_gate_manifest(root)
        foundation_contract = tc.load_approved(manifest, design)
        bare = tc._bare_contract(foundation_contract)
        bare["classification"]["profile"] = "foundation"
        tc.seal_contract(manifest, bare, tc.file_digest(manifest))
        foundation_result = subprocess.run(
            [sys.executable, str(RESOLVER), "--manifest", str(manifest)],
            capture_output=True,
            text=True,
        )
        if foundation_result.returncode != 0:
            print("foundation profile was rejected", foundation_result.stderr, file=sys.stderr)
            return 1
        if 'gate_command: "bin/foundation-gate self"' not in manifest.read_text(encoding="utf-8"):
            print("foundation profile did not select foundation gate", file=sys.stderr)
            return 1
        bare["quality_gate"]["gen_artifact_paths"] = []
        tc.seal_contract(manifest, bare, tc.file_digest(manifest))
        empty_run = subprocess.run(
            [sys.executable, str(RESOLVER), "--manifest", str(manifest)],
            capture_output=True,
            text=True,
        )
        if empty_run.returncode != 0:
            print("empty gen_artifact_paths must be accepted", empty_run.stderr, file=sys.stderr)
            return 1
    print("[test_resolve_quality_gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
