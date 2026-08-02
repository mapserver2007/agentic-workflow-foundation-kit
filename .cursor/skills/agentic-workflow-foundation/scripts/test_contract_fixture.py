#!/usr/bin/env python3
"""tech_contract テスト用の完全 fixture 生成。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tech_contract as tc  # noqa: E402

FIXTURE_RUNNER = HERE / "provision_fixture_runner.py"


def json_field_validation(pointer: str, expected: str, version_pattern: str | None = None) -> dict:
    validation: dict = {"kind": "json-field", "pointer": pointer, "expected": expected}
    if version_pattern is not None:
        validation["version_pattern"] = version_pattern
    return validation


def executable_validation() -> dict:
    return {"kind": "executable-file"}


def installed_marker(target: str, package: str, validation: dict) -> dict:
    return {
        "kind": "installed-marker",
        "target": target,
        "covers_packages": [package],
        "validation": validation,
        "evidence_ref": "design §9",
        "guidance": "fixture installed marker",
    }


def absent_marker(target: str, package: str) -> dict:
    return {
        "kind": "absent-marker",
        "target": target,
        "covers_packages": [package],
        "evidence_ref": "design §9",
        "guidance": "fixture absent marker",
    }


WEB_PNPM_WS = (
    "packages:\n"
    "  - \"apps/*\"\n"
    "  - \"packages/*\"\n"
    "allowBuilds:\n"
    "  '@scarf/scarf': set this to true or false\n"
    "  core-js: set this to true or false\n"
    "  esbuild: set this to true or false\n"
    "  protobufjs: set this to true or false\n"
    "  workerd: set this to true or false\n"
)
WEB_TSCONFIG = (
    "{\n"
    "  \"compilerOptions\": {\n"
    "    \"strict\": true,\n"
    "    \"target\": \"ES2022\",\n"
    "    \"module\": \"ESNext\",\n"
    "    \"moduleResolution\": \"bundler\",\n"
    "    \"esModuleInterop\": true,\n"
    "    \"skipLibCheck\": true,\n"
    "    \"noEmit\": true\n"
    "  }\n"
    "}\n"
)


def fixture_command_action(*writes: str) -> dict:
    command_writes = list(writes) if writes else [".provision-marker"]
    marker = ".state/provision-state.json"
    all_writes = list(command_writes)
    if marker not in all_writes:
        all_writes.append(marker)
    digest_paths = list(command_writes)
    return {
        "argv": [sys.executable, str(FIXTURE_RUNNER), "touch", "--root", ".", "--writes", *command_writes],
        "cwd": ".",
        "effects": ["project_write"],
        "writes": all_writes,
        "postconditions": [{
            "kind": "record-state-digest",
            "marker": marker,
            "paths": digest_paths,
            "evidence_ref": "design §9",
        }],
        "evidence_ref": "design §9",
    }

_DOMAIN_SECTIONS = {
    "spec_sections": [{"title": "Purpose", "guidance": "fixture"}],
    "architecture_sections": [{"title": "Architecture", "guidance": "fixture"}],
    "api_sections": [{"title": "API", "guidance": "fixture"}],
    "data_model_sections": [{"title": "Data", "guidance": "fixture"}],
    "coding_standards_sections": [{"title": "Style", "content": "Go rules"}],
    "workflow_sections": [{"title": "Flow", "guidance": "fixture"}],
}


def _gate_item(argv: list[str]) -> dict:
    return {"argv": argv, "evidence_ref": "design §9", "contract": ["fixture gate"]}


def base_contract(fingerprint: str, *, with_file_action: bool = True, profile: str = "application") -> dict:
    actions = []
    if with_file_action:
        actions.append({
            "kind": "create-if-missing",
            "target": "go.mod",
            "ownership": "project",
            "conflict_policy": "fail",
            "evidence_ref": "design §9",
            "content": "module example.com/fixture\n",
        })
    return {
        "schema_version": 1,
        "classification": {"profile": profile, "evidence_ref": "design §9"},
        "quality_gate": {
            "gen_artifact_paths": [],
            "gen": _gate_item(["tool", "gen"]),
            "build": _gate_item(["tool", "build"]),
            "lint": _gate_item(["tool", "lint"]),
            "test": _gate_item(["tool", "test"]),
        },
        "runtime_materialization": {"actions": actions},
        "review": {
            "evidence_ref": "design §9",
            "coderabbit": {
                "enabled": True,
                "language": "ja-JP",
                "tools_enabled": [{"name": "fixture-lint"}],
                "tools_disabled": [{"name": "unused"}],
                "path_filters": ["!**/*.lock"],
                "path_instructions": [{"path": "**/*", "instructions": "fixture review"}],
            },
        },
        "domain_docs": {
            "evidence_ref": "design §9",
            "resolved": {
                "primary_language": "Go",
                "api_style": "fixture",
                "database": "none",
                "architecture": "layered",
                "framework": "fixture",
                "test_framework": "testing",
                "package_manager": "go",
                **_DOMAIN_SECTIONS,
            },
        },
        "provisioning": {
            "policy": "explicit" if with_file_action else "none",
            "evidence_ref": "design §9",
            "preflight_checks": [{
                "kind": "non-empty-workspace",
                "evidence_ref": "design §9",
                "guidance": "bin/project-setup --plan を確認してください",
            }] if with_file_action else [],
            "command_actions": [],
        },
        "source_fingerprint": fingerprint,
    }


def bootstrap_root(root: Path, design_text: str = "# fixture\nGo\n", *, profile: str = "application") -> tuple[Path, Path]:
    design = root / "docs" / "TECH.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text(design_text, encoding="utf-8")
    manifest = root / "manifest.yaml"
    manifest.write_text(
        "version: 1\n"
        "project:\n"
        "  tech_stack_design_filename: TECH.md\n"
        "  quality_gate:\n"
        f"    profile: {profile}\n"
        "    gen_artifact_paths: []\n",
        encoding="utf-8",
    )
    return manifest, design


def consumer_contract(fingerprint: str, language: str, command: str, *, profile: str = "application") -> dict:
    contract = base_contract(fingerprint, with_file_action=False, profile=profile)
    for gate in ("gen", "build", "lint", "test"):
        contract["quality_gate"][gate]["argv"] = [command, gate]
        contract["quality_gate"][gate]["contract"] = [gate]
    review = contract["review"]["coderabbit"]
    review["tools_enabled"] = [{"name": f"{language}-lint"}]
    resolved = contract["domain_docs"]["resolved"]
    resolved["primary_language"] = language
    resolved["test_framework"] = command
    resolved["package_manager"] = command
    contract["provisioning"]["preflight_checks"] = []
    contract["provisioning"]["command_actions"] = []
    return contract


def pnpm_quality_contract(fingerprint: str, *, gen_paths: list[str] | None = None) -> dict:
    contract = base_contract(fingerprint, with_file_action=False, profile="application")
    contract["quality_gate"]["gen_artifact_paths"] = gen_paths if gen_paths is not None else [
        "generated/api.ts",
    ]
    lines = {
        "gen": "OpenAPI bundle を生成し、bundle 成功を検証する",
        "build": "TypeScript typecheck を実行する",
        "lint": "Redocly lint を実行する",
        "test": "Vitest を実行する",
    }
    for gate, line in lines.items():
        contract["quality_gate"][gate]["argv"] = ["pnpm", "run", gate]
        contract["quality_gate"][gate]["contract"] = [line]
    contract["provisioning"]["preflight_checks"] = []
    contract["provisioning"]["command_actions"] = []
    return contract


def conformance_contract(fingerprint: str) -> dict:
    contract = base_contract(fingerprint, with_file_action=False)
    contract["provisioning"]["policy"] = "explicit"
    contract["runtime_materialization"]["actions"] = [{
        "kind": "json-key-merge",
        "target": "package.json",
        "ownership": "project",
        "conflict_policy": "merge_owned",
        "evidence_ref": "design §9",
        "owned_keys": ["name"],
        "values": {"name": "fixture-web"},
    }]
    contract["provisioning"]["preflight_checks"] = [
        {
            "kind": "path-exists",
            "target": "package.json",
            "evidence_ref": "design §9",
            "guidance": "materialize 後に package.json を確認してください",
        },
        {
            "kind": "json-key-present",
            "target": "package.json",
            "key": "name",
            "evidence_ref": "design §9",
            "guidance": "contract values を確認してください",
        },
    ]
    contract["provisioning"]["command_actions"] = []
    return contract


def go_lifecycle_contract(fingerprint: str) -> dict:
    contract = base_contract(fingerprint, with_file_action=False, profile="application")
    contract["provisioning"]["policy"] = "explicit"
    for gate in ("gen", "build", "lint", "test"):
        contract["quality_gate"][gate] = _gate_item(["go", gate])
    contract["runtime_materialization"]["actions"] = [{
        "kind": "create-if-missing",
        "target": "go.mod",
        "ownership": "project",
        "conflict_policy": "fail",
        "evidence_ref": "design §9",
        "content": "module example.com/go-fixture\n\ngo 1.22\n",
    }]
    contract["review"]["coderabbit"]["tools_enabled"] = [{"name": "Go-lint"}]
    resolved = contract["domain_docs"]["resolved"]
    resolved.update({
        "primary_language": "Go",
        "test_framework": "go",
        "package_manager": "go",
    })
    contract["provisioning"]["preflight_checks"] = [{
        "kind": "path-exists",
        "target": "go.mod",
        "evidence_ref": "design §9",
        "guidance": "materialize 後に go.mod を確認してください",
    }]
    contract["provisioning"]["command_actions"] = [fixture_command_action(".provision-marker")]
    return contract


def web_lifecycle_contract(fingerprint: str) -> dict:
    contract = consumer_contract(fingerprint, "TypeScript", "pnpm")
    contract["provisioning"]["policy"] = "explicit"
    contract["runtime_materialization"]["actions"] = [{
        "kind": "json-key-merge",
        "target": "package.json",
        "ownership": "project",
        "conflict_policy": "merge_owned",
        "evidence_ref": "design §9",
        "owned_keys": ["name", "scripts.test"],
        "values": {"name": "fixture-web", "scripts.test": "echo ok"},
    }]
    contract["provisioning"]["preflight_checks"] = [
        {
            "kind": "path-exists",
            "target": "package.json",
            "evidence_ref": "design §9",
            "guidance": "materialize 後に package.json を確認してください",
        },
        {
            "kind": "json-key-present",
            "target": "package.json",
            "key": "name",
            "evidence_ref": "design §9",
            "guidance": "contract values を確認してください",
        },
    ]
    contract["provisioning"]["command_actions"] = [fixture_command_action(".provision-marker")]
    return contract


MINIMAL_SEED = """version: 1
framework:
  version: 1
"""


def write_lifecycle_workspace(root: Path, contract: dict, design_text: str) -> tuple[Path, Path, Path]:
    seed = root / "seed.yaml"
    seed.write_text(MINIMAL_SEED, encoding="utf-8")
    manifest, design = write_sealed_manifest(root, contract, design_text)
    return seed, manifest, design


def write_consumer_manifest(root: Path, contract: dict, design_text: str = "# fixture\nGo\n") -> tuple[Path, Path]:
    manifest, design = bootstrap_root(root, design_text)
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace(
            "    gen_artifact_paths: []\n",
            "    gen_artifact_paths:\n      - \"generated/fixture\"\n"
            "    gen_cmd: \"old\"\n"
            "    build_cmd: \"old\"\n"
            "    lint_cmd: \"old\"\n"
            "    test_cmd: \"old\"\n",
        )
        + "session:\n  verification:\n    gate_command: \"old\"\n",
        encoding="utf-8",
    )
    tc.seal_contract(manifest, contract, tc.file_digest(manifest))
    tc.load_approved(manifest, design)
    return manifest, design


def write_quality_gate_manifest(root: Path, design_text: str = "# fixture\n") -> tuple[Path, Path]:
    design = root / "docs" / "TECH.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text(design_text, encoding="utf-8")
    manifest = root / "manifest.yaml"
    manifest.write_text(
        "version: 1\n"
        "tech_stack:\n"
        "  note: \"fixture\"\n"
        "  items: []\n"
        "session:\n"
        "  verification:\n"
        "    gate_command: \"[要確認]\"\n"
        "project:\n"
        "  tech_stack_design_filename: TECH.md\n"
        "  workflow_pattern: 開発型\n"
        "  quality_gate:\n"
        "    profile: \"application\"\n"
        "    gen_artifact_paths:\n"
        "      - \"generated/api.ts\"\n"
        "    gen_cmd: \"[要確認]\"\n"
        "    build_cmd: \"[要確認]\"\n"
        "    lint_cmd: \"[要確認]\"\n"
        "    test_cmd: \"[要確認]\"\n"
        "quality_gate_contract:\n"
        "  gen:\n"
        "    - \"legacy contract line\"\n"
        "  build:\n"
        "    - \"legacy\"\n"
        "  lint:\n"
        "    - \"legacy\"\n"
        "  test:\n"
        "    - \"legacy\"\n",
        encoding="utf-8",
    )
    contract = pnpm_quality_contract(tc.source_fingerprint(design))
    tc.seal_contract(manifest, contract, tc.file_digest(manifest))
    tc.load_approved(manifest, design)
    return manifest, design


def write_conformance_manifest(root: Path, design_text: str = "# fixture\n") -> tuple[Path, Path]:
    manifest, design = bootstrap_root(root, design_text)
    contract = conformance_contract(tc.source_fingerprint(design))
    tc.seal_contract(manifest, contract, tc.file_digest(manifest))
    tc.load_approved(manifest, design)
    return manifest, design


def write_sealed_manifest(root: Path, contract: dict, design_text: str = "# fixture\nGo\n") -> tuple[Path, Path]:
    manifest, design = bootstrap_root(root, design_text, profile=contract["classification"]["profile"])
    tc.seal_contract(manifest, contract, tc.file_digest(manifest))
    tc.load_approved(manifest, design)
    return manifest, design
