"""承認済み tech_contract から resolved manifest への決定論投影。"""
from __future__ import annotations

from pathlib import Path

import tech_contract as tc  # noqa: E402


def gate_command_for_profile(profile: str) -> str:
    if profile == "foundation":
        return "bin/foundation-gate self"
    if profile == "application":
        return "bin/quality-gate verify"
    raise tc.SchemaError(
        "classification.profile は foundation または application が必要です"
    )


def _require_gen_artifact_paths(contract: dict) -> list[str]:
    quality = contract.get("quality_gate")
    if not isinstance(quality, dict):
        raise tc.SchemaError("tech_contract.quality_gate が不正です")
    if "gen_artifact_paths" not in quality:
        raise tc.SchemaError("tech_contract.quality_gate.gen_artifact_paths が必須です")
    paths = quality["gen_artifact_paths"]
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise tc.SchemaError("tech_contract.quality_gate.gen_artifact_paths は文字列配列が必要です")
    return list(paths)


def project_quality_gate(contract: dict) -> dict:
    classification = contract.get("classification") or {}
    profile = classification.get("profile")
    if profile not in {"foundation", "application"}:
        raise tc.SchemaError(
            "classification.profile は foundation または application が必要です"
        )
    quality = contract.get("quality_gate") or {}
    result = {"profile": profile}
    for gate in ("gen", "build", "lint", "test"):
        item = quality.get(gate) or {}
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv:
            raise tc.SchemaError(f"tech_contract.quality_gate.{gate}.argv が不正です")
        result[f"{gate}_cmd"] = " ".join(argv)
    result["gen_artifact_paths"] = _require_gen_artifact_paths(contract)
    return result


def coderabbit_from_contract(contract: dict) -> dict:
    review = (contract.get("review") or {}).get("coderabbit")
    if not isinstance(review, dict):
        raise tc.SchemaError("tech_contract.review.coderabbit が不正です")
    required = {"enabled", "language", "tools_enabled", "tools_disabled", "path_filters", "path_instructions"}
    if not required.issubset(review):
        raise tc.SchemaError("tech_contract.review.coderabbit が完全ではありません")
    return dict(review)


def domain_docs_from_contract(contract: dict) -> dict:
    resolved = (contract.get("domain_docs") or {}).get("resolved")
    if not isinstance(resolved, dict):
        raise tc.SchemaError("tech_contract.domain_docs.resolved が不正です")
    return dict(resolved)


def quality_gate_contract_from_contract(contract: dict) -> dict:
    quality = contract.get("quality_gate") or {}
    return {
        gate: list((quality.get(gate) or {}).get("contract", []))
        for gate in ("gen", "build", "lint", "test")
    }


def apply_contract_projection(manifest: dict, root_manifest_path: str) -> dict:
    """overlay 後の manifest に contract 投影を上書き適用する。"""
    path = Path(root_manifest_path)
    design_doc = tc.resolve_design_doc(path)
    contract = tc.load_approved(path, design_doc)
    merged = dict(manifest)
    project = dict(merged.get("project") or {})
    project["quality_gate"] = project_quality_gate(contract)
    merged["project"] = project
    merged["coderabbit"] = coderabbit_from_contract(contract)
    merged["domain_docs"] = domain_docs_from_contract(contract)
    merged["quality_gate_contract"] = quality_gate_contract_from_contract(contract)
    session = dict(merged.get("session") or {})
    verification = dict(session.get("verification") or {})
    verification["gate_command"] = gate_command_for_profile(project["quality_gate"]["profile"])
    session["verification"] = verification
    merged["session"] = session
    return merged
