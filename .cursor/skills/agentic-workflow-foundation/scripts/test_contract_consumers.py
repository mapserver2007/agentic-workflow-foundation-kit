#!/usr/bin/env python3
"""Web golden と Go fixture の contract consumer 回帰。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tech_contract as tc  # noqa: E402
import genlib  # noqa: E402
import resolve_coderabbit as rc  # noqa: E402
import resolve_domain_docs as rd  # noqa: E402
from test_contract_fixture import consumer_contract, write_consumer_manifest  # noqa: E402
from yaml_emitter import dump_yaml_text  # noqa: E402

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


def multiline_projection_roundtrip() -> bool:
    instructions = (
        "Use {{variable}} as a literal placeholder.\n"
        "Keep {{#each items}}...{{/each}} unchanged.\n"
    )
    guidance = "First guidance line.\nSecond guidance line.\n"
    content = "First content line.\nSecond content line.\n"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design_text = "# fixture\nTypeScript\n"
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text(design_text, encoding="utf-8")
        contract = consumer_contract(tc.source_fingerprint(design), "TypeScript", "pnpm")
        contract["review"]["coderabbit"]["path_instructions"][0]["instructions"] = instructions
        resolved = contract["domain_docs"]["resolved"]
        resolved["spec_sections"][0]["guidance"] = guidance
        resolved["coding_standards_sections"][0]["content"] = content
        manifest, _ = write_consumer_manifest(root, contract, design_text)

        if rc.main(["--manifest", str(manifest)]) != 0:
            print("FAIL: multiline CodeRabbit projection")
            return False
        if rd.main(["--manifest", str(manifest)]) != 0:
            print("FAIL: multiline Domain docs projection")
            return False

        projected = genlib.load_manifest(str(manifest))
        projected_instructions = projected["coderabbit"]["path_instructions"][0]["instructions"]
        projected_guidance = projected["domain_docs"]["spec_sections"][0]["guidance"]
        projected_content = projected["domain_docs"]["coding_standards_sections"][0]["content"]
        if (projected_instructions, projected_guidance, projected_content) != (
            instructions,
            guidance,
            content,
        ):
            print("FAIL: multiline projection round-trip mismatch")
            return False

        text = manifest.read_text(encoding="utf-8")
        for needle in ("instructions: |", "guidance: |", "content: |"):
            if needle not in text:
                print(f"FAIL: multiline projection missing block literal: {needle}")
                return False

        before = manifest.read_bytes()
        if rc.main(["--manifest", str(manifest)]) != 0:
            return False
        if rd.main(["--manifest", str(manifest)]) != 0:
            return False
        if manifest.read_bytes() != before:
            print("FAIL: multiline projection is not idempotent")
            return False
    return True


def yaml_emitter_edge_case_roundtrip() -> bool:
    cases = (
        {},
        {"value": {}},
        {"items": [{"value": {}}, {}]},
        {"value": "first\nsecond"},
        {"value": "first\nsecond\n"},
        {"value": "first\nsecond\n\n"},
        {"items": ["first\nsecond", "first\nsecond\n", "first\nsecond\n\n"]},
        {"items": [{"value": "first\nsecond\n\n", "empty": {}}]},
    )
    for value in cases:
        rendered = dump_yaml_text(value)
        projected = genlib.parse_yaml(rendered)
        if projected != value:
            print(
                "FAIL: YAML emitter edge-case round-trip mismatch: "
                f"{value!r} -> {rendered!r} -> {projected!r}"
            )
            return False

    if dump_yaml_text({}) != "{}\n":
        print("FAIL: empty root mapping must be an explicit YAML document")
        return False

    for value, indicator in (
        ("first\nsecond", "|-"),
        ("first\nsecond\n", "|"),
        ("first\nsecond\n\n", "|+"),
    ):
        if f"value: {indicator}\n" not in dump_yaml_text({"value": value}):
            print(f"FAIL: multiline value missing {indicator} chomping indicator")
            return False
    return True


def resolver_write_failure_does_not_corrupt() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, resolver in (("coderabbit", rc), ("domain", rd)):
            fixture_root = root / name
            fixture_root.mkdir()
            design_text = "# fixture\nGo\n"
            design = fixture_root / "docs" / "TECH.md"
            design.parent.mkdir(parents=True, exist_ok=True)
            design.write_text(design_text, encoding="utf-8")
            contract = consumer_contract(tc.source_fingerprint(design), "Go", "go")
            manifest, _ = write_consumer_manifest(fixture_root, contract, design_text)
            before = manifest.read_bytes()
            with patch.object(
                resolver.rp,
                "_atomic_write_bytes",
                side_effect=OSError("injected write failure"),
            ):
                code = resolver.main(["--manifest", str(manifest)])
            if code != 2:
                print(f"FAIL: {name} write failure must return exit 2")
                return False
            if manifest.read_bytes() != before:
                print(f"FAIL: {name} write failure corrupted manifest")
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
        for needle in (
            'gen_cmd: "go gen"',
            'name: "Go-lint"',
            'primary_language: "Go"',
            'content: "Go rules"',
        ):
            if needle not in go_output:
                print(f"FAIL: Go contract projection missing {needle}")
                return 1
    if not domain_docs_escaped_scalar_roundtrip():
        return 1
    if not multiline_projection_roundtrip():
        return 1
    if not yaml_emitter_edge_case_roundtrip():
        return 1
    if not resolver_write_failure_does_not_corrupt():
        return 1
    print("[test_contract_consumers] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
