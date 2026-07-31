#!/usr/bin/env python3
"""resolved engine の contract 投影が旧 root overlay を上書き不能にすることを検証。"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract_projection as cp  # noqa: E402
import run_resolved_engine as rre  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import MINIMAL_SEED, web_lifecycle_contract, write_sealed_manifest  # noqa: E402


def coderabbit_equals_contract(resolved: dict, contract: dict) -> bool:
    return resolved.get("coderabbit") == cp.coderabbit_from_contract(contract)


def domain_docs_equals_contract(resolved: dict, contract: dict) -> bool:
    return resolved.get("domain_docs") == cp.domain_docs_from_contract(contract)


def quality_paths_equal(resolved: dict, contract: dict) -> bool:
    pq = (resolved.get("project") or {}).get("quality_gate") or {}
    expected = cp.project_quality_gate(contract)
    return pq.get("gen_cmd") == expected["gen_cmd"] and pq.get("gen_artifact_paths") == expected["gen_artifact_paths"]


def main() -> int:
    design_text = "# fixture\nTypeScript\n"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        seed = root / "seed.yaml"
        seed.write_text(MINIMAL_SEED, encoding="utf-8")
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text(design_text, encoding="utf-8")
        fixture_contract = web_lifecycle_contract(tc.source_fingerprint(design))
        fixture_contract["quality_gate"]["gen"]["argv"] = [
            "pnpm",
            "run",
            "generate api",
            "--output=generated/api bundle.yaml",
        ]
        manifest, design = write_sealed_manifest(
            root,
            fixture_contract,
            design_text,
        )
        contract = tc.load_approved(manifest, design)

        text = manifest.read_text(encoding="utf-8")
        stale_block = (
            "coderabbit:\n"
            "  enabled: false\n"
            "  language: en-US\n"
            "  tools_enabled: []\n"
            "  tools_disabled: []\n"
            "  path_filters: []\n"
            "  path_instructions: []\n"
            "domain_docs:\n"
            "  primary_language: StaleLang\n"
            "  api_style: stale\n"
            "  database: none\n"
            "  architecture: layered\n"
            "  framework: stale\n"
            "  test_framework: stale\n"
            "  package_manager: stale\n"
            "  spec_sections: []\n"
            "  architecture_sections: []\n"
            "  api_sections: []\n"
            "  data_model_sections: []\n"
            "  coding_standards_sections: []\n"
            "  workflow_sections: []\n"
        )
        manifest.write_text(stale_block + text, encoding="utf-8")

        resolved = rre.resolved_manifest(str(seed), str(manifest))
        if not coderabbit_equals_contract(resolved, contract):
            print("FAIL: stale coderabbit not overwritten by contract")
            return 1
        if not domain_docs_equals_contract(resolved, contract):
            print("FAIL: stale domain_docs not overwritten by contract")
            return 1
        expected_gen_cmd = "pnpm run 'generate api' '--output=generated/api bundle.yaml'"
        if resolved["project"]["quality_gate"]["gen_cmd"] != expected_gen_cmd:
            print("FAIL: gen_cmd not shell-quoted from contract argv")
            return 1
        if resolved["session"]["verification"]["gate_command"] != "bin/quality-gate verify":
            print("FAIL: gate_command not derived from profile")
            return 1

        design.write_text(design_text + "\n# stale change\n", encoding="utf-8")
        try:
            rre.resolved_manifest(str(seed), str(manifest))
        except tc.ContractError:
            pass
        else:
            print("FAIL: stale design doc did not block generate")
            return 1

        bad = manifest.read_text(encoding="utf-8").replace(contract["contract_digest"], "0" * 64, 1)
        manifest.write_text(bad, encoding="utf-8")
        design.write_text(design_text, encoding="utf-8")
        try:
            rre.resolved_manifest(str(seed), str(manifest))
        except tc.ContractError:
            pass
        else:
            print("FAIL: tampered digest did not block generate")
            return 1

    print("[test_resolved_contract_projection] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
