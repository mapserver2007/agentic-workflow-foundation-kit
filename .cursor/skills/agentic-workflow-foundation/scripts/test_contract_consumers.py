#!/usr/bin/env python3
"""Web golden と Go fixture の contract consumer 回帰。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tech_contract as tc  # noqa: E402
from test_contract_fixture import consumer_contract, write_consumer_manifest  # noqa: E402

CODERABBIT = HERE / "resolve_coderabbit.py"
DOMAIN = HERE / "resolve_domain_docs.py"
QUALITY = HERE / "resolve_quality_gate.py"


def project(manifest: Path) -> int:
    for script in (CODERABBIT, DOMAIN, QUALITY):
        result = subprocess.run([sys.executable, str(script), "--manifest", str(manifest)], capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout, result.stderr)
            return 1
    return 0


def domain_docs_escaped_scalar_roundtrip() -> bool:
    scalar = r'TypeScript "strict" C:\\toolchains\\\\node\\bin'
    guidance = r'Use "quoted" paths C:\\docs\\\\specs\\current'
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_text = "# fixture\nTypeScript\n"
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text(design_text, encoding="utf-8")
        contract = consumer_contract(tc.source_fingerprint(design), "TypeScript", "pnpm")
        resolved = contract["domain_docs"]["resolved"]
        resolved["primary_language"] = scalar
        resolved["spec_sections"][0]["title"] = scalar
        resolved["spec_sections"][0]["guidance"] = guidance
        manifest, design = write_consumer_manifest(root, contract, design_text)

        result = subprocess.run(
            [sys.executable, str(DOMAIN), "--manifest", str(manifest)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("FAIL: escaped domain docs projection", result.stdout, result.stderr)
            return False

        tc.load_approved(manifest, design)
        projected = tc.load_yaml(manifest)["domain_docs"]
        if projected["primary_language"] != scalar:
            print("FAIL: projected scalar escape round-trip")
            return False
        section = projected["spec_sections"][0]
        if section["title"] != scalar or section["guidance"] != guidance:
            print("FAIL: projected section escape round-trip")
            return False
    return True


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_text = "# fixture\nGo\n"
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text(design_text, encoding="utf-8")
        fp = tc.source_fingerprint(design)

        web_root = root / "web"
        web_root.mkdir()
        web_manifest, _ = write_consumer_manifest(web_root, consumer_contract(fp, "TypeScript", "pnpm"), design_text)

        go_root = root / "go"
        go_root.mkdir()
        go_manifest, _ = write_consumer_manifest(go_root, consumer_contract(fp, "Go", "go"), design_text)

        if project(web_manifest) or project(go_manifest):
            return 1
        web_output, go_output = web_manifest.read_text(encoding="utf-8"), go_manifest.read_text(encoding="utf-8")
        for needle in ('gen_cmd: "pnpm gen"', 'name: "TypeScript-lint"', 'primary_language: "TypeScript"'):
            if needle not in web_output:
                print(f"FAIL: Web golden missing {needle}")
                return 1
        for needle in ('gen_cmd: "go gen"', 'name: "Go-lint"', 'primary_language: "Go"', 'content: |'):
            if needle not in go_output:
                print(f"FAIL: Go contract projection missing {needle}")
                return 1
    if not domain_docs_escaped_scalar_roundtrip():
        return 1
    print("[test_contract_consumers] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
