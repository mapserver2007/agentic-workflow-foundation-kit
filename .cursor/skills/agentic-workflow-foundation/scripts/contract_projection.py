"""承認済み tech_contract から resolved manifest への決定論投影。"""
from __future__ import annotations

import shlex
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
        result[f"{gate}_cmd"] = shlex.join(argv)
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


def _dot_dir_from_rel(rel: str) -> str | None:
    """writes/marker 相対 path から ignore 対象ドットディレクトリを導出する。

    ルート直下ファイル（スラッシュ無し）は除外する。先頭セグメントが `.` で
    始まるときだけ `{name}/` を返す。技術名推論は行わない。
    """
    if not isinstance(rel, str) or not rel.strip():
        return None
    normalized = rel.replace("\\", "/").strip()
    if normalized.startswith("/") or ".." in Path(normalized).parts:
        return None
    parts = [p for p in normalized.split("/") if p]
    if not parts:
        return None
    # ルート直下ファイル（例: pnpm-lock.yaml / .env）は除外
    if len(parts) == 1 and not normalized.endswith("/"):
        return None
    first = parts[0]
    if first.startswith(".") and first not in {".", ".."}:
        return f"{first}/"
    return None


def project_ignore_dirs(contract: dict) -> list[str]:
    """tech_contract.provisioning writes + postcondition marker から ignore_dirs を導出。"""
    collected: list[str] = []
    provisioning = contract.get("provisioning") or {}
    actions = provisioning.get("command_actions") or []
    if not isinstance(actions, list):
        return []
    for action in actions:
        if not isinstance(action, dict):
            continue
        writes = action.get("writes") or []
        if isinstance(writes, list):
            for item in writes:
                if isinstance(item, str):
                    collected.append(item)
        posts = action.get("postconditions") or []
        if isinstance(posts, list):
            for post in posts:
                if not isinstance(post, dict):
                    continue
                marker = post.get("marker")
                if isinstance(marker, str):
                    collected.append(marker)
    dirs: set[str] = set()
    for rel in collected:
        derived = _dot_dir_from_rel(rel)
        if derived is not None:
            dirs.add(derived)
    return sorted(dirs)


def apply_contract_projection(manifest: dict, root_manifest_path: str) -> dict:
    """overlay 後の manifest に contract 投影を上書き適用する。"""
    path = Path(root_manifest_path)
    design_doc = tc.resolve_design_doc(path)
    contract = tc.load_approved(path, design_doc)
    merged = dict(manifest)
    project = dict(merged.get("project") or {})
    project["quality_gate"] = project_quality_gate(contract)
    project["ignore_dirs"] = project_ignore_dirs(contract)
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
