#!/usr/bin/env python3
"""Domain docs section のテンプレート別本文フィールド契約を検証する。"""
from __future__ import annotations

import copy
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract_projection as cp  # noqa: E402
import resolve_domain_docs as rd  # noqa: E402
import run_resolved_engine as rre  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract, write_sealed_manifest  # noqa: E402

SKILL_DIR = HERE.parent
TEMPLATES = {
    "api_sections": "api.md.template",
    "data_model_sections": "data-models.md.template",
    "workflow_sections": "workflows.md.template",
    "coding_standards_sections": "coding-standards.md.template",
}


def _assert_schema_error(contract: dict, design: Path, label: str) -> bool:
    try:
        tc.validate(contract, design, require_approval=False, check=True)
    except tc.SchemaError:
        return True
    print(f"FAIL: {label} を SchemaError として拒否しませんでした", file=sys.stderr)
    return False


def section_required_fields_reject_invalid_shapes() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        design = Path(tmp) / "TECH.md"
        design.write_text("# fixture\n", encoding="utf-8")
        fingerprint = tc.source_fingerprint(design)

        coding_wrong = base_contract(fingerprint, with_file_action=False)
        coding_wrong["domain_docs"]["resolved"]["coding_standards_sections"] = [
            {"title": "Style", "guidance": "wrong"},
        ]
        if not _assert_schema_error(coding_wrong, design, "coding guidance-only"):
            return False

        coding_both = base_contract(fingerprint, with_file_action=False)
        coding_both["domain_docs"]["resolved"]["coding_standards_sections"] = [
            {"title": "Style", "guidance": "wrong", "content": "right"},
        ]
        if not _assert_schema_error(coding_both, design, "coding guidance+content"):
            return False

        for key in ("api_sections", "data_model_sections", "workflow_sections"):
            content_only = base_contract(fingerprint, with_file_action=False)
            content_only["domain_docs"]["resolved"][key] = [
                {"title": "Section", "content": "wrong"},
            ]
            if not _assert_schema_error(content_only, design, f"{key} content-only"):
                return False

            both = base_contract(fingerprint, with_file_action=False)
            both["domain_docs"]["resolved"][key] = [
                {"title": "Section", "guidance": "right", "content": "wrong"},
            ]
            if not _assert_schema_error(both, design, f"{key} guidance+content"):
                return False

        tc.validate(base_contract(fingerprint, with_file_action=False), design, require_approval=False, check=True)
    return True


def templates_match_section_contract() -> bool:
    for section_key, template_name in TEMPLATES.items():
        template = (SKILL_DIR / "templates" / "docs" / template_name).read_text(encoding="utf-8")
        fields = set(re.findall(r"\{\{this\.(content|guidance)\}\}", template))
        expected = set(tc.SECTION_REQUIRED_FIELDS[section_key])
        if fields != expected:
            print(
                f"FAIL: {template_name} の this.*={sorted(fields)} が "
                f"{section_key} の契約={sorted(expected)} と一致しません",
                file=sys.stderr,
            )
            return False
    return True


def valid_fixture_resolves_generates_and_audits() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# fixture\nTypeScript\n", encoding="utf-8")
        contract = base_contract(tc.source_fingerprint(design), with_file_action=False)
        manifest, design = write_sealed_manifest(root, copy.deepcopy(contract), "# fixture\nTypeScript\n")

        resolved = rd._resolve(str(manifest))
        if resolved != contract["domain_docs"]["resolved"]:
            print("FAIL: valid domain docs fixture の resolve 結果が不一致です", file=sys.stderr)
            return False

        (root / ".cursor" / "skills").mkdir(parents=True, exist_ok=True)
        args = [
            "--seed-manifest", str(SKILL_DIR / "manifest.yaml"),
            "--root-manifest", str(manifest),
            "--work-root", str(root),
        ]
        if rre.main(["generate", *args]) != 0:
            print("FAIL: valid fixture の generate が失敗しました", file=sys.stderr)
            return False
        if rre.main(["audit", *args]) != 0:
            print("FAIL: valid fixture の audit が失敗しました", file=sys.stderr)
            return False
    return True


def deprecated_sections_stay_optional_and_unprojected() -> bool:
    """旧必須の spec_sections / architecture_sections は、あっても受理し（封印済みの既存契約を壊さない）、
    無くても受理し、どちらの場合も root manifest の domain_docs へ投影しない。"""
    deprecated = {
        "spec_sections": [{"title": "Purpose", "guidance": "legacy"}],
        "architecture_sections": [{"title": "Architecture", "content": "legacy"}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design.write_text("# fixture\nTypeScript\n", encoding="utf-8")
        fingerprint = tc.source_fingerprint(design)

        current = base_contract(fingerprint, with_file_action=False)
        legacy = copy.deepcopy(current)
        legacy["domain_docs"]["resolved"].update(deprecated)
        for label, contract in (("current", current), ("legacy", legacy)):
            tc.validate(contract, design, require_approval=False, check=True)
            projected = cp.domain_docs_from_contract(contract)
            if set(projected) & tc.DEPRECATED_RESOLVED_KEYS:
                print(f"FAIL: {label} 契約の domain_docs 投影に旧キーが含まれます", file=sys.stderr)
                return False

        manifest, design = write_sealed_manifest(root, copy.deepcopy(legacy), "# fixture\nTypeScript\n")
        if set(rd._resolve(str(manifest))) & tc.DEPRECATED_RESOLVED_KEYS:
            print("FAIL: resolve_domain_docs が旧キーを投影します", file=sys.stderr)
            return False

        missing_required = copy.deepcopy(current)
        del missing_required["domain_docs"]["resolved"]["api_sections"]
        return _assert_schema_error(missing_required, design, "必須セクション api_sections の欠落")


def main() -> int:
    checks = {
        "section_required_fields_reject_invalid_shapes": section_required_fields_reject_invalid_shapes,
        "templates_match_section_contract": templates_match_section_contract,
        "valid_fixture_resolves_generates_and_audits": valid_fixture_resolves_generates_and_audits,
        "deprecated_sections_stay_optional_and_unprojected": deprecated_sections_stay_optional_and_unprojected,
    }
    for name, check in checks.items():
        if not check():
            print(f"FAIL: {name}", file=sys.stderr)
            return 1
        print(f"PASS: {name}")
    print("[test_contract_domain_sections] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
