#!/usr/bin/env python3
"""承認済み tech_contract の検証・状態確認・安全な manifest pin を行う。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ENGINE_DIR = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(HERE))
import genlib  # noqa: E402
import runtime_plan as rp  # noqa: E402

SCHEMA_VERSION = 1
REQUIRED_SECTIONS = (
    "classification",
    "quality_gate",
    "runtime_materialization",
    "review",
    "domain_docs",
    "provisioning",
    "source_fingerprint",
)
GATE_PROFILES = frozenset({"foundation", "application"})
FILE_KINDS = rp.FILE_KINDS
COMMAND_EFFECTS = rp.COMMAND_EFFECTS
PREFLIGHT_KINDS = rp.PREFLIGHT_KINDS
SHELL_METACHARACTERS = frozenset("|&;<>()$`\\")
DESTRUCTIVE_ARGV = frozenset({"rm", "rmdir", "mkfs", "dd", "shutdown", "reboot", "touch"})
PROVISIONING_POLICIES = frozenset({"explicit", "none"})

TOP_LEVEL_KEYS = frozenset({
    "schema_version",
    *REQUIRED_SECTIONS,
    "approval",
    "contract_digest",
    "projection_digest",
})
CLASSIFICATION_KEYS = frozenset({"profile", "evidence_ref"})
QUALITY_GATE_KEYS = frozenset({"gen", "build", "lint", "test", "gen_artifact_paths"})
GATE_ITEM_KEYS = frozenset({"argv", "evidence_ref", "contract"})
FILE_ACTION_KEYS = frozenset({
    "kind", "target", "ownership", "conflict_policy", "evidence_ref",
    "content", "values", "owned_keys",
})
COMMAND_ACTION_KEYS = frozenset({"argv", "cwd", "effects", "evidence_ref", "writes", "postconditions"})
POSTCONDITION_KEYS = frozenset({
    "kind", "argv", "marker", "pointer", "pattern", "paths", "evidence_ref",
})
POSTCONDITION_KINDS = frozenset({"capture-toolchain-version", "record-state-digest"})
PREFLIGHT_KEYS = frozenset({
    "kind", "evidence_ref", "guidance", "target", "key",
    "pointer", "pattern", "executable", "marker", "paths", "covers_packages", "validation",
})
VALIDATION_KEYS = frozenset({"kind", "pointer", "expected", "version_pattern"})
JSON_POINTER_LEAF = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
SECTION_ITEM_KEYS = frozenset({"title", "guidance", "content"})
# value は title 以外に許可する本文フィールド。map 対象はちょうど 1 つを必須にする。
SECTION_REQUIRED_FIELDS = {
    "coding_standards_sections": ("content",),
    "api_sections": ("guidance",),
    "data_model_sections": ("guidance",),
    "workflow_sections": ("guidance",),
}
TOOL_ITEM_KEYS = frozenset({"name"})
PATH_INSTRUCTION_KEYS = frozenset({"path", "instructions"})
RUNTIME_MAT_KEYS = frozenset({"actions", "reality"})
REALITY_KEYS = frozenset({"required_packages", "forbidden_packages"})
REVIEW_KEYS = frozenset({"evidence_ref", "coderabbit"})
CODERABBIT_KEYS = frozenset({
    "enabled", "language", "tools_enabled", "tools_disabled", "path_filters", "path_instructions",
})
DOMAIN_DOCS_KEYS = frozenset({"evidence_ref", "resolved"})
RESOLVED_KEYS = frozenset({
    "primary_language", "api_style", "database", "architecture", "framework",
    "test_framework", "package_manager",
    "spec_sections", "architecture_sections", "api_sections",
    "data_model_sections", "coding_standards_sections", "workflow_sections",
})
PROVISIONING_KEYS = frozenset({"policy", "evidence_ref", "preflight_checks", "command_actions"})
APPROVAL_KEYS = frozenset({"status", "digest", "schema_version"})


class ContractError(Exception):
    """stale / approval / digest 等、修正可能な契約不一致（exit 1）。"""


class SchemaError(Exception):
    """schema / render / environment fatal（exit 2）。"""


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bare_contract(contract: dict) -> dict:
    return {k: v for k, v in contract.items() if k not in {"approval", "contract_digest", "projection_digest"}}


def _normalize_multiline_text(value: str) -> str:
    text = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return text


def _normalize_contract_data(contract: dict) -> dict:
    data = copy.deepcopy(_bare_contract(contract))
    for action in rp.collect_file_actions(data):
        if isinstance(action.get("content"), str):
            action["content"] = _normalize_multiline_text(action["content"])
    return data


def contract_digest(contract: dict) -> str:
    return hashlib.sha256(canonical_json(_normalize_contract_data(contract)).encode("utf-8")).hexdigest()


def projection_payload(contract: dict) -> dict:
    prov = contract.get("provisioning") or {}
    return {
        "classification": copy.deepcopy(contract.get("classification")),
        "quality_gate": copy.deepcopy(contract.get("quality_gate")),
        "runtime_materialization": copy.deepcopy(contract.get("runtime_materialization")),
        "review": copy.deepcopy(contract.get("review")),
        "domain_docs": copy.deepcopy(contract.get("domain_docs")),
        "provisioning": {
            "policy": prov.get("policy"),
            "preflight_checks": copy.deepcopy(prov.get("preflight_checks") or []),
            "command_actions": copy.deepcopy(prov.get("command_actions") or []),
        },
    }


def projection_digest(contract: dict) -> str:
    return hashlib.sha256(canonical_json(projection_payload(contract)).encode("utf-8")).hexdigest()


def source_fingerprint(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).rstrip("\n") + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> dict:
    try:
        return genlib.load_manifest(str(path))
    except (OSError, genlib.YamlError) as exc:
        raise SchemaError(f"YAML 読み込み失敗: {exc}") from exc


def load_yaml_text(text: str) -> dict:
    try:
        parsed = genlib.parse_yaml(text)
    except genlib.YamlError as exc:
        raise SchemaError(f"YAML 解析失敗: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SchemaError("manifest root は mapping である必要があります")
    return parsed


def resolve_design_doc(manifest: Path, root: Path | None = None) -> Path:
    base = root or manifest.parent
    project = load_yaml(manifest).get("project") or {}
    filename = project.get("tech_stack_design_filename")
    if not isinstance(filename, str) or not filename.strip():
        raise SchemaError("project.tech_stack_design_filename が必要です")
    candidates = (
        base / ".cursor" / "docs" / filename,
        base / "docs" / filename,
    )
    for path in candidates:
        if path.is_file():
            return path
    raise SchemaError(f"技術設計書が存在しません: {candidates[0]}")


def load_approved(manifest: Path, design_doc: Path) -> dict:
    root = load_yaml(manifest)
    contract = root.get("tech_contract")
    if not isinstance(contract, dict):
        raise ContractError("tech_contract がありません")
    validate(contract, design_doc, require_approval=True, check=False)
    return contract


def _reject_unknown(obj: dict, allowed: frozenset[str], label: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise SchemaError(f"{label} に未知キーがあります: {sorted(unknown)}")


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{label} は非空文字列が必要です")
    return value


def _require_evidence(value: object, label: str) -> None:
    _require_str(value, f"{label}.evidence_ref")


def _validate_relative_path(value: str, label: str) -> None:
    if value.startswith("/") or ".." in Path(value).parts:
        raise SchemaError(f"{label} は root 相対パスである必要があります")


def _validate_argv(argv: object, label: str) -> None:
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise SchemaError(f"{label}.argv は非空の文字列配列が必要です")
    basename = Path(argv[0]).name
    if basename in DESTRUCTIVE_ARGV:
        raise SchemaError(f"{label}.argv は破壊的コマンドを許可しません: {argv[0]}")
    for arg in argv:
        if "\n" in arg or SHELL_METACHARACTERS.intersection(arg):
            raise SchemaError(f"{label}.argv に shell 構文または禁止文字があります: {arg!r}")
        if re.search(r"(?i)(token|secret|password|api[_-]?key)", arg):
            raise SchemaError(f"{label}.argv に secret 参照らしき値があります: {arg!r}")


def _validate_file_action(action: dict, index: int) -> None:
    label = f"runtime_materialization.actions[{index}]"
    if not isinstance(action, dict):
        raise SchemaError(f"{label} はオブジェクトが必要です")
    _reject_unknown(action, FILE_ACTION_KEYS, label)
    kind = _require_str(action.get("kind"), label)
    if kind not in FILE_KINDS:
        raise SchemaError(f"{label}.kind が未知です: {kind}")
    target = _require_str(action.get("target"), label)
    _validate_relative_path(target, f"{label}.target")
    _require_str(action.get("ownership"), label)
    if action["ownership"] not in {"tool", "project"}:
        raise SchemaError(f"{label}.ownership は tool/project です")
    _require_str(action.get("conflict_policy"), label)
    if action["conflict_policy"] not in {"fail", "merge_owned"}:
        raise SchemaError(f"{label}.conflict_policy が不正です")
    _require_evidence(action.get("evidence_ref"), label)
    if "argv" in action or "command" in action:
        raise SchemaError(f"{label} に argv/command は禁止です。provisioning.command_actions を使ってください")
    if kind == "owned-text-render":
        if not isinstance(action.get("content"), str):
            raise SchemaError(f"{label}.content は文字列が必要です")
    elif kind == "json-key-merge":
        values = action.get("values")
        owned = action.get("owned_keys")
        if not isinstance(values, dict) or not values:
            raise SchemaError(f"{label}.values は非空 mapping が必要です")
        if not isinstance(owned, list) or not all(isinstance(k, str) and k for k in owned):
            raise SchemaError(f"{label}.owned_keys は非空文字列配列が必要です")
        for owned_key in owned:
            if not JSON_POINTER_LEAF.fullmatch(owned_key):
                raise SchemaError(f"{label}.owned_keys に不正な JSON pointer があります: {owned_key!r}")
        extra = set(values) - set(owned)
        if extra:
            raise SchemaError(f"{label}.values に owned_keys 外のキーがあります: {sorted(extra)}")
    elif kind == "create-if-missing":
        if "content" not in action and "values" not in action:
            raise SchemaError(f"{label} は content または values が必要です")
        if "content" in action and not isinstance(action["content"], str):
            raise SchemaError(f"{label}.content は文字列が必要です")
        if "values" in action and not isinstance(action["values"], dict):
            raise SchemaError(f"{label}.values は mapping が必要です")


def _validate_postcondition(post: dict, index: int, parent: str) -> None:
    label = f"{parent}.postconditions[{index}]"
    if not isinstance(post, dict):
        raise SchemaError(f"{label} はオブジェクトが必要です")
    _reject_unknown(post, POSTCONDITION_KEYS, label)
    kind = _require_str(post.get("kind"), label)
    if kind not in POSTCONDITION_KINDS:
        raise SchemaError(f"{label}.kind が未知です: {kind}")
    _require_evidence(post.get("evidence_ref"), label)
    if kind == "capture-toolchain-version":
        _validate_argv(post.get("argv"), label)
        try:
            rp.validate_capture_argv(post.get("argv"), label)
        except ValueError as exc:
            raise SchemaError(str(exc)) from exc
        _require_str(post.get("marker"), f"{label}.marker")
        _validate_relative_path(post["marker"], f"{label}.marker")
        _require_str(post.get("pointer"), f"{label}.pointer")
        if not JSON_POINTER_LEAF.fullmatch(post["pointer"]):
            raise SchemaError(f"{label}.pointer が不正です")
        pattern = _require_str(post.get("pattern"), f"{label}.pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise SchemaError(f"{label}.pattern が不正です: {exc}") from exc
    elif kind == "record-state-digest":
        _require_str(post.get("marker"), f"{label}.marker")
        _validate_relative_path(post["marker"], f"{label}.marker")
        paths = post.get("paths")
        if not isinstance(paths, list) or not paths:
            raise SchemaError(f"{label}.paths は非空配列必須です")
        for path_index, rel in enumerate(paths):
            if not isinstance(rel, str) or not rel.strip():
                raise SchemaError(f"{label}.paths[{path_index}] に空要素があります")
            _validate_relative_path(rel, f"{label}.paths")


def _validate_command_action(action: dict, index: int) -> None:
    label = f"provisioning.command_actions[{index}]"
    if not isinstance(action, dict):
        raise SchemaError(f"{label} はオブジェクトが必要です")
    _reject_unknown(action, COMMAND_ACTION_KEYS, label)
    _require_evidence(action.get("evidence_ref"), label)
    _validate_argv(action.get("argv"), label)
    effects = action.get("effects")
    if not isinstance(effects, list) or not effects:
        raise SchemaError(f"{label}.effects は非空配列が必要です")
    unknown = [e for e in effects if e not in COMMAND_EFFECTS]
    if unknown:
        raise SchemaError(f"{label}.effects に未知値があります: {unknown}")
    cwd = action.get("cwd", ".")
    if not isinstance(cwd, str) or not cwd:
        raise SchemaError(f"{label}.cwd は非空文字列が必要です")
    _validate_relative_path(cwd, f"{label}.cwd")
    writes = action.get("writes", [])
    if writes is None:
        writes = []
    if not isinstance(writes, list) or not all(isinstance(w, str) and w for w in writes):
        raise SchemaError(f"{label}.writes は文字列配列である必要があります")
    for rel in writes:
        _validate_relative_path(rel, f"{label}.writes")
    if any(e in effects for e in ("project_write", "lockfile_write")) and not writes:
        raise SchemaError(f"{label}.writes は project_write / lockfile_write 時に非空必須です")
    postconditions = action.get("postconditions", [])
    if postconditions is None:
        postconditions = []
    if not isinstance(postconditions, list):
        raise SchemaError(f"{label}.postconditions は配列である必要があります")
    for pc_index, post in enumerate(postconditions):
        _validate_postcondition(post, pc_index, label)
    write_set = set(writes)
    post_generated = rp._postcondition_generated_paths(action)
    for rel in post_generated:
        if rel not in write_set:
            raise SchemaError(f"{label}.writes に postcondition marker {rel!r} が含まれていません")
    project_effects = {e for e in effects if e in ("project_write", "lockfile_write")}
    host_only = set(effects) == {"host_write"}
    if host_only and not postconditions:
        raise SchemaError(f"{label}.postconditions は host_write-only 時に必須です")


def _validate_validation_object(validation: object, label: str) -> None:
    if not isinstance(validation, dict):
        raise SchemaError(f"{label}.validation は mapping 必須です")
    _reject_unknown(validation, VALIDATION_KEYS, f"{label}.validation")
    kind = _require_str(validation.get("kind"), f"{label}.validation.kind")
    if kind not in rp.MARKER_VALIDATION_KINDS:
        raise SchemaError(f"{label}.validation.kind が未知です: {kind}")
    if kind == "json-field":
        _require_str(validation.get("pointer"), f"{label}.validation.pointer")
        _require_str(validation.get("expected"), f"{label}.validation.expected")
        if "version_pattern" in validation:
            pattern = _require_str(validation["version_pattern"], f"{label}.validation.version_pattern")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise SchemaError(f"{label}.validation.version_pattern が不正です: {exc}") from exc
    elif kind != "executable-file":
        raise SchemaError(f"{label}.validation.kind が未知です: {kind}")


def _validate_preflight_check(check: dict, index: int) -> None:
    label = f"provisioning.preflight_checks[{index}]"
    if not isinstance(check, dict):
        raise SchemaError(f"{label} はオブジェクトが必要です")
    _reject_unknown(check, PREFLIGHT_KEYS, label)
    kind = _require_str(check.get("kind"), label)
    if kind not in PREFLIGHT_KINDS:
        raise SchemaError(f"{label}.kind が未知です: {kind}")
    _require_evidence(check.get("evidence_ref"), label)
    if not isinstance(check.get("guidance"), str) or not check["guidance"]:
        raise SchemaError(f"{label}.guidance は必須です")
    if kind == "executable-exists":
        _require_str(check.get("executable"), f"{label}.executable")
    elif kind == "path-exists":
        _require_str(check.get("target"), f"{label}.target")
        _validate_relative_path(check["target"], f"{label}.target")
    elif kind == "json-value-pattern":
        _require_str(check.get("target"), f"{label}.target")
        _validate_relative_path(check["target"], f"{label}.target")
        _require_str(check.get("pointer"), f"{label}.pointer")
        pattern = _require_str(check.get("pattern"), f"{label}.pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise SchemaError(f"{label}.pattern が不正です: {exc}") from exc
    elif kind == "json-key-present":
        _require_str(check.get("target"), f"{label}.target")
        _validate_relative_path(check["target"], f"{label}.target")
        _require_str(check.get("key"), f"{label}.key")
    elif kind == "installed-marker":
        _require_str(check.get("target"), f"{label}.target")
        _validate_relative_path(check["target"], f"{label}.target")
        covers = check.get("covers_packages")
        if not isinstance(covers, list) or not covers:
            raise SchemaError(f"{label}.covers_packages は非空配列必須です")
        seen_pkg: set[str] = set()
        for pkg_index, pkg in enumerate(covers):
            if not isinstance(pkg, str) or not pkg.strip():
                raise SchemaError(f"{label}.covers_packages[{pkg_index}] が不正です")
            if pkg in seen_pkg:
                raise SchemaError(f"{label}.covers_packages に重複があります: {pkg}")
            seen_pkg.add(pkg)
        if "validation" not in check:
            raise SchemaError(f"{label}.validation は必須です")
        _validate_validation_object(check["validation"], label)
    elif kind == "absent-marker":
        _require_str(check.get("target"), f"{label}.target")
        _validate_relative_path(check["target"], f"{label}.target")
        covers = check.get("covers_packages")
        if not isinstance(covers, list) or not covers:
            raise SchemaError(f"{label}.covers_packages は非空配列必須です")
        seen_pkg = set()
        for pkg_index, pkg in enumerate(covers):
            if not isinstance(pkg, str) or not pkg.strip():
                raise SchemaError(f"{label}.covers_packages[{pkg_index}] が不正です")
            if pkg in seen_pkg:
                raise SchemaError(f"{label}.covers_packages に重複があります: {pkg}")
            seen_pkg.add(pkg)
    elif kind in ("lockfile-present", "lockfile-absent"):
        _require_str(check.get("target"), f"{label}.target")
        _validate_relative_path(check["target"], f"{label}.target")
    elif kind == "state-digests":
        _require_str(check.get("marker"), f"{label}.marker")
        _validate_relative_path(check["marker"], f"{label}.marker")
        paths = check.get("paths")
        if not isinstance(paths, list) or not paths:
            raise SchemaError(f"{label}.paths は非空配列必須です")
        for path_index, rel in enumerate(paths):
            if not isinstance(rel, str) or not rel.strip():
                raise SchemaError(f"{label}.paths[{path_index}] に空要素があります")
            _validate_relative_path(rel, f"{label}.paths")


def _validate_section_item(item: object, label: str, section_key: str) -> None:
    if not isinstance(item, dict):
        raise SchemaError(f"{label} はオブジェクトが必要です")
    _reject_unknown(item, SECTION_ITEM_KEYS, label)
    _require_str(item.get("title"), f"{label}.title")
    required_fields = SECTION_REQUIRED_FIELDS.get(section_key)
    if required_fields is not None:
        required_field = required_fields[0]
        forbidden_field = "guidance" if required_field == "content" else "content"
        _require_str(item.get(required_field), f"{label}.{required_field}")
        if forbidden_field in item:
            raise SchemaError(
                f"{label}.{forbidden_field} は {section_key} では許可されません"
            )
        return
    has_guidance = "guidance" in item
    has_content = "content" in item
    if not has_guidance and not has_content:
        raise SchemaError(f"{label} は guidance または content が必要です")
    if has_guidance:
        _require_str(item["guidance"], f"{label}.guidance")
    if has_content:
        _require_str(item["content"], f"{label}.content")


def _validate_review(contract: dict) -> None:
    review = contract.get("review")
    if not isinstance(review, dict):
        raise SchemaError("review は mapping である必要があります")
    _reject_unknown(review, REVIEW_KEYS, "review")
    _require_evidence(review.get("evidence_ref"), "review")
    coderabbit = review.get("coderabbit")
    if not isinstance(coderabbit, dict):
        raise SchemaError("review.coderabbit は mapping である必要があります")
    _reject_unknown(coderabbit, CODERABBIT_KEYS, "review.coderabbit")
    if not isinstance(coderabbit.get("enabled"), bool):
        raise SchemaError("review.coderabbit.enabled は bool 必須です")
    _require_str(coderabbit.get("language"), "review.coderabbit.language")
    for key in CODERABBIT_KEYS:
        if key not in coderabbit:
            raise SchemaError(f"review.coderabbit.{key} が欠落しています")
    for tool_key in ("tools_enabled", "tools_disabled"):
        tools = coderabbit[tool_key]
        if not isinstance(tools, list):
            raise SchemaError(f"review.coderabbit.{tool_key} は配列が必要です")
        for index, tool in enumerate(tools):
            tlabel = f"review.coderabbit.{tool_key}[{index}]"
            if not isinstance(tool, dict):
                raise SchemaError(f"{tlabel} はオブジェクトが必要です")
            _reject_unknown(tool, TOOL_ITEM_KEYS, tlabel)
            _require_str(tool.get("name"), f"{tlabel}.name")
    filters = coderabbit["path_filters"]
    if not isinstance(filters, list) or not all(isinstance(f, str) and f for f in filters):
        raise SchemaError("review.coderabbit.path_filters は非空文字列配列が必要です")
    instructions = coderabbit["path_instructions"]
    if not isinstance(instructions, list):
        raise SchemaError("review.coderabbit.path_instructions は配列が必要です")
    for index, instr in enumerate(instructions):
        ilabel = f"review.coderabbit.path_instructions[{index}]"
        if not isinstance(instr, dict):
            raise SchemaError(f"{ilabel} はオブジェクトが必要です")
        _reject_unknown(instr, PATH_INSTRUCTION_KEYS, ilabel)
        _require_str(instr.get("path"), f"{ilabel}.path")
        _require_str(instr.get("instructions"), f"{ilabel}.instructions")


def _validate_domain_docs(contract: dict) -> None:
    domain = contract.get("domain_docs")
    if not isinstance(domain, dict):
        raise SchemaError("domain_docs は mapping である必要があります")
    _reject_unknown(domain, DOMAIN_DOCS_KEYS, "domain_docs")
    _require_evidence(domain.get("evidence_ref"), "domain_docs")
    resolved = domain.get("resolved")
    if not isinstance(resolved, dict):
        raise SchemaError("domain_docs.resolved は mapping である必要があります")
    _reject_unknown(resolved, RESOLVED_KEYS, "domain_docs.resolved")
    for key in RESOLVED_KEYS:
        if key not in resolved:
            raise SchemaError(f"domain_docs.resolved.{key} が欠落しています")
        if key.endswith("_sections"):
            sections = resolved[key]
            if not isinstance(sections, list):
                raise SchemaError(f"domain_docs.resolved.{key} は配列が必要です")
            for index, item in enumerate(sections):
                _validate_section_item(
                    item,
                    f"domain_docs.resolved.{key}[{index}]",
                    section_key=key,
                )
        else:
            _require_str(resolved.get(key), f"domain_docs.resolved.{key}")


def dedupe_preflight_checks(checks: list[dict]) -> list[dict]:
    """canonical payload で preflight_checks を決定論的に dedupe する。"""
    seen: set[str] = set()
    deduped: list[dict] = []
    for check in checks:
        digest = rp.preflight_payload_digest(check)
        if digest in seen:
            continue
        seen.add(digest)
        deduped.append(check)
    return deduped


def _validate_provisioning(contract: dict) -> None:
    prov = contract.get("provisioning")
    if not isinstance(prov, dict):
        raise SchemaError("provisioning は mapping である必要があります")
    _reject_unknown(prov, PROVISIONING_KEYS, "provisioning")
    _require_evidence(prov.get("evidence_ref"), "provisioning")
    policy = _require_str(prov.get("policy"), "provisioning")
    if policy not in PROVISIONING_POLICIES:
        raise SchemaError(f"provisioning.policy が未知です: {policy}")
    checks = prov.get("preflight_checks")
    if not isinstance(checks, list):
        raise SchemaError("provisioning.preflight_checks は配列である必要があります")
    seen_checks: set[str] = set()
    for index, check in enumerate(checks):
        _validate_preflight_check(check, index)
        digest = rp.preflight_payload_digest(check)
        if digest in seen_checks:
            raise SchemaError(f"provisioning.preflight_checks[{index}] が重複 payload です")
        seen_checks.add(digest)
    commands = prov.get("command_actions")
    if not isinstance(commands, list):
        raise SchemaError("provisioning.command_actions は配列である必要があります")
    seen_commands: set[str] = set()
    for index, action in enumerate(commands):
        _validate_command_action(action, index)
        digest = rp.payload_digest(action)
        if digest in seen_commands:
            raise SchemaError(f"provisioning.command_actions[{index}] が重複 payload です")
        seen_commands.add(digest)

    file_actions = rp.collect_file_actions(contract)
    if policy == "none":
        if file_actions or commands:
            raise SchemaError(
                "provisioning.policy=none では runtime_materialization.actions と "
                "provisioning.command_actions は共に空である必要があります"
            )
        if any(check.get("kind") == "non-empty-workspace" for check in checks):
            raise SchemaError(
                "provisioning.policy=none では non-empty-workspace preflight は許可されません"
            )
        # none は変更操作なしを表す。外部で充足済みの runtime を検査する
        # required/forbidden_packages と marker preflight は許容する。foundation kit
        # で reality を空にすることは運用規則であり、schema では強制しない。
    elif not file_actions and not commands:
        raise SchemaError(
            "provisioning.policy=explicit では runtime_materialization.actions または "
            "provisioning.command_actions が1件以上必要です"
        )
    _validate_reality_preflight_coverage(contract)
    _validate_forbidden_preflight_coverage(contract)


def _validate_forbidden_preflight_coverage(contract: dict) -> None:
    runtime = contract.get("runtime_materialization") or {}
    reality = runtime.get("reality")
    if not isinstance(reality, dict):
        return
    forbidden_list = reality.get("forbidden_packages") or []
    if not forbidden_list:
        return
    forbidden = set(forbidden_list)
    checks = (contract.get("provisioning") or {}).get("preflight_checks") or []
    covered: set[str] = set()
    for index, check in enumerate(checks):
        if check.get("kind") != "absent-marker":
            continue
        covers = check.get("covers_packages") or []
        for pkg in covers:
            if not isinstance(pkg, str):
                continue
            if pkg not in forbidden:
                raise SchemaError(
                    f"provisioning.preflight_checks[{index}].covers_packages に "
                    f"forbidden_packages 外の package があります: {pkg}"
                )
            if pkg in covered:
                raise SchemaError(
                    f"provisioning.preflight_checks[{index}].covers_packages に "
                    f"重複カバーがあります: {pkg}"
                )
            covered.add(pkg)
    missing = sorted(forbidden - covered)
    if missing:
        raise SchemaError(
            f"runtime_materialization.reality.forbidden_packages に preflight 未カバーがあります: {missing}"
        )


def _validate_reality_preflight_coverage(contract: dict) -> None:
    runtime = contract.get("runtime_materialization") or {}
    reality = runtime.get("reality")
    if not isinstance(reality, dict):
        return
    required_list = reality.get("required_packages") or []
    if not required_list:
        return
    required = set(required_list)
    checks = (contract.get("provisioning") or {}).get("preflight_checks") or []
    covered: set[str] = set()
    for index, check in enumerate(checks):
        if check.get("kind") != "installed-marker":
            continue
        covers = check.get("covers_packages") or []
        for pkg in covers:
            if not isinstance(pkg, str):
                continue
            if pkg not in required:
                raise SchemaError(
                    f"provisioning.preflight_checks[{index}].covers_packages に "
                    f"required_packages 外の package があります: {pkg}"
                )
            if pkg in covered:
                raise SchemaError(
                    f"provisioning.preflight_checks[{index}].covers_packages に "
                    f"重複カバーがあります: {pkg}"
                )
            covered.add(pkg)
    missing = sorted(required - covered)
    if missing:
        raise SchemaError(
            f"runtime_materialization.reality.required_packages に preflight 未カバーがあります: {missing}"
        )


def _validate_quality_gate(contract: dict) -> None:
    quality = contract.get("quality_gate")
    if not isinstance(quality, dict):
        raise SchemaError("quality_gate は mapping である必要があります")
    _reject_unknown(quality, QUALITY_GATE_KEYS, "quality_gate")
    if "gen_artifact_paths" not in quality:
        raise SchemaError("quality_gate.gen_artifact_paths が必須です")
    paths = quality["gen_artifact_paths"]
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise SchemaError("quality_gate.gen_artifact_paths は文字列配列である必要があります")
    for rel_path in paths:
        if not rel_path.strip():
            raise SchemaError("quality_gate.gen_artifact_paths に空要素があります")
        _validate_relative_path(rel_path, "quality_gate.gen_artifact_paths")
    for gate in ("gen", "build", "lint", "test"):
        value = quality.get(gate)
        if not isinstance(value, dict):
            raise SchemaError(f"quality_gate.{gate} が必要です")
        _reject_unknown(value, GATE_ITEM_KEYS, f"quality_gate.{gate}")
        _validate_argv(value.get("argv"), f"quality_gate.{gate}")
        _require_evidence(value.get("evidence_ref"), f"quality_gate.{gate}")
        contract_lines = value.get("contract")
        if not isinstance(contract_lines, list) or not contract_lines:
            raise SchemaError(f"quality_gate.{gate}.contract は非空配列が必要です")
        if not all(isinstance(line, str) and line.strip() for line in contract_lines):
            raise SchemaError(f"quality_gate.{gate}.contract は非空文字列配列が必要です")


def _validate_runtime_materialization(contract: dict) -> None:
    runtime = contract.get("runtime_materialization")
    if not isinstance(runtime, dict):
        raise SchemaError("runtime_materialization は mapping である必要があります")
    _reject_unknown(runtime, RUNTIME_MAT_KEYS, "runtime_materialization")
    actions = runtime.get("actions")
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        raise SchemaError("runtime_materialization.actions は配列が必要です")
    targets: set[str] = set()
    for index, action in enumerate(actions):
        _validate_file_action(action, index)
        if action["target"] in targets:
            raise SchemaError(f"runtime_materialization.actions[{index}].target が重複しています")
        targets.add(action["target"])
    reality = runtime.get("reality")
    if reality is not None:
        if not isinstance(reality, dict):
            raise SchemaError("runtime_materialization.reality は mapping である必要があります")
        _reject_unknown(reality, REALITY_KEYS, "runtime_materialization.reality")
        for key in REALITY_KEYS:
            if key not in reality:
                raise SchemaError(f"runtime_materialization.reality.{key} が欠落しています")
            if not isinstance(reality[key], list):
                raise SchemaError(f"runtime_materialization.reality.{key} は配列が必要です")
            if not all(isinstance(item, str) and item.strip() for item in reality[key]):
                raise SchemaError(f"runtime_materialization.reality.{key} は非空文字列配列が必要です")
        required = set(reality.get("required_packages") or [])
        forbidden = set(reality.get("forbidden_packages") or [])
        overlap = sorted(required & forbidden)
        if overlap:
            raise SchemaError(
                "runtime_materialization.reality.required_packages と "
                f"forbidden_packages の交差があります: {overlap}"
            )


def validate(contract: dict, design_doc: Path, require_approval: bool, check: bool = False) -> None:
    if not isinstance(contract, dict):
        raise SchemaError("tech_contract は mapping である必要があります")
    _reject_unknown(contract, TOP_LEVEL_KEYS, "tech_contract")
    if contract.get("schema_version") != SCHEMA_VERSION:
        raise SchemaError(f"schema_version は {SCHEMA_VERSION} である必要があります")
    missing = [key for key in REQUIRED_SECTIONS if key not in contract]
    if missing:
        raise SchemaError(f"必須セクションが欠落しています: {', '.join(missing)}")

    classification = contract.get("classification")
    if not isinstance(classification, dict):
        raise SchemaError("classification は mapping である必要があります")
    _reject_unknown(classification, CLASSIFICATION_KEYS, "classification")
    profile = _require_str(classification.get("profile"), "classification.profile")
    if profile not in GATE_PROFILES:
        raise SchemaError(f"classification.profile は {sorted(GATE_PROFILES)} です")
    _require_evidence(classification.get("evidence_ref"), "classification")

    fingerprint = source_fingerprint(design_doc)
    if contract.get("source_fingerprint") != fingerprint:
        raise ContractError("source_fingerprint が現在の技術設計書と一致しません")

    expected_digest = contract_digest(contract)
    expected_projection = projection_digest(contract)
    digest = contract.get("contract_digest")
    proj = contract.get("projection_digest")
    if require_approval:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SchemaError("approved contract では contract_digest が必須です")
        if digest != expected_digest:
            raise ContractError("contract_digest が canonical digest と一致しません")
        if not isinstance(proj, str) or not re.fullmatch(r"[0-9a-f]{64}", proj):
            raise SchemaError("approved contract では projection_digest が必須です")
        if proj != expected_projection:
            raise ContractError("projection_digest が canonical projection と一致しません")
    else:
        if digest is not None and digest != expected_digest:
            raise ContractError("contract_digest が canonical digest と一致しません")
        if proj is not None and proj != expected_projection:
            raise ContractError("projection_digest が canonical projection と一致しません")

    _validate_quality_gate(contract)
    _validate_runtime_materialization(contract)
    _validate_review(contract)
    _validate_domain_docs(contract)
    _validate_provisioning(contract)

    if require_approval:
        approval = contract.get("approval")
        if not isinstance(approval, dict):
            raise SchemaError("approval が必要です")
        _reject_unknown(approval, APPROVAL_KEYS, "approval")
        if approval.get("status") != "approved":
            raise ContractError("approval.status=approved が必要です")
        if approval.get("digest") != expected_digest or approval.get("schema_version") != SCHEMA_VERSION:
            raise ContractError("approval が contract digest / schema version に結合されていません")

    if check:
        root = design_doc.parent if design_doc.parent.name else Path(".")
        _validate_renderability(contract, root)


def _finalize_contract(bare: dict) -> dict:
    finalized = copy.deepcopy(bare)
    digest = contract_digest(finalized)
    proj = projection_digest(finalized)
    finalized["contract_digest"] = digest
    finalized["projection_digest"] = proj
    finalized["approval"] = {
        "status": "approved",
        "digest": digest,
        "schema_version": SCHEMA_VERSION,
    }
    return finalized


def _extract_loaded_contract(manifest_path: Path) -> dict:
    loaded = load_yaml(manifest_path).get("tech_contract")
    if not isinstance(loaded, dict):
        raise SchemaError("tech_contract の load に失敗しました")
    return loaded


def seal_contract(manifest_path: Path, contract: dict, expected_preimage: str | None = None) -> dict:
    """digest / approval を contract 内に確定してから単一 byte-span pin する。"""
    bare = _bare_contract(contract)
    preimage = expected_preimage or file_digest(manifest_path)
    finalized = _finalize_contract(bare)
    pin_contract(manifest_path, finalized, preimage)
    sealed = _extract_loaded_contract(manifest_path)
    if canonical_json(_bare_contract(sealed)) != canonical_json(bare):
        raise SchemaError("pin round-trip で contract data が一致しません")
    if contract_digest(sealed) != finalized["contract_digest"]:
        raise ContractError("seal 後の contract_digest が一致しません")
    if projection_digest(sealed) != finalized["projection_digest"]:
        raise ContractError("seal 後の projection_digest が一致しません")
    return sealed


def _validate_renderability(contract: dict, root: Path) -> None:
    for index, action in enumerate(rp.collect_file_actions(contract)):
        try:
            rp.render_file_bytes(action, root)
        except Exception as exc:
            raise SchemaError(f"runtime_materialization.actions[{index}] は render 不可: {exc}") from exc
    _ = projection_digest(contract)


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_top_level_key_line(line: str) -> bool:
    stripped = line.rstrip("\r\n")
    if not stripped.strip():
        return False
    if _line_indent(stripped) != 0:
        return False
    head = stripped.split("#", 1)[0].rstrip()
    if not head.endswith(":"):
        return False
    key = head[:-1].strip()
    return bool(key) and not key.startswith("- ")


def _find_top_level_block_span(raw: bytes, key: bytes) -> tuple[int, int] | None:
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    offset = 0
    start = None
    for line in lines:
        if line.startswith(f"{key.decode()}:") and _line_indent(line.rstrip("\r\n")) == 0:
            start = offset
            break
        offset += len(line.encode("utf-8"))
    if start is None:
        return None
    offset = 0
    for line in lines:
        line_start = offset
        offset += len(line.encode("utf-8"))
        if line_start <= start:
            continue
        if _is_top_level_key_line(line):
            return start, line_start
    return start, len(raw)


def _dump_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if "\n" not in value and not value.startswith(("@", "|", ">", "*", "&", "!", "%", "`")):
            if re.fullmatch(r"[^\"'\\]*", value):
                return json.dumps(value, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def _dump_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return key
    return _dump_scalar(key)


def _append_scalar_lines(lines: list[str], pad: str, key_text: str, child: object) -> None:
    if isinstance(child, str) and "\n" in child:
        lines.append(f"{pad}{key_text}: |")
        body = child[:-1] if child.endswith("\n") else child
        for part in body.split("\n"):
            lines.append(f"{pad}  {part}")
    else:
        lines.append(f"{pad}{key_text}: {_dump_scalar(child)}")


def _dump_yaml(value: object, indent: int = 0) -> list[str]:
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            key_text = _dump_key(str(key))
            if isinstance(child, list) and not child:
                lines.append(f"{pad}{key_text}: []")
            elif isinstance(child, (dict, list)):
                lines.append(f"{pad}{key_text}:")
                lines.extend(_dump_yaml(child, indent + 2))
            else:
                _append_scalar_lines(lines, pad, key_text, child)
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}[]"]
        lines = []
        for child in value:
            if isinstance(child, dict):
                keys = list(child)
                if not keys:
                    lines.append(f"{pad}- {{}}")
                    continue
                first, *rest = keys
                val = child[first]
                first_key = _dump_key(str(first))
                if isinstance(val, (dict, list)):
                    lines.append(f"{pad}- {first_key}:")
                    lines.extend(_dump_yaml(val, indent + 4))
                elif isinstance(val, str) and "\n" in val:
                    lines.append(f"{pad}- {first_key}: |")
                    body = val[:-1] if val.endswith("\n") else val
                    for part in body.split("\n"):
                        lines.append(f"{pad}    {part}")
                else:
                    lines.append(f"{pad}- {first_key}: {_dump_scalar(val)}")
                for rkey in rest:
                    val2 = child[rkey]
                    key_text = _dump_key(str(rkey))
                    if isinstance(val2, list) and not val2:
                        lines.append(f"{pad}  {key_text}: []")
                    elif isinstance(val2, (dict, list)):
                        lines.append(f"{pad}  {key_text}:")
                        lines.extend(_dump_yaml(val2, indent + 4))
                    else:
                        _append_scalar_lines(lines, pad + "  ", key_text, val2)
            elif isinstance(child, str) and "\n" in child:
                lines.append(f"{pad}- |")
                body = child[:-1] if child.endswith("\n") else child
                for part in body.split("\n"):
                    lines.append(f"{pad}  {part}")
            else:
                lines.append(f"{pad}- {_dump_scalar(child)}")
        return lines
    return [f"{pad}{_dump_scalar(value)}"]


def _verify_pin_roundtrip(new_raw: bytes, finalized: dict) -> None:
    parsed = load_yaml_text(new_raw.decode("utf-8"))
    loaded = parsed.get("tech_contract")
    if not isinstance(loaded, dict):
        raise SchemaError("pin 後 tech_contract が見つかりません")
    bare = _bare_contract(finalized)
    loaded_bare = _bare_contract(loaded)
    if canonical_json(_normalize_contract_data(finalized)) != canonical_json(_normalize_contract_data(loaded)):
        raise SchemaError("pin round-trip: contract data 不一致")
    for key in ("contract_digest", "projection_digest", "approval"):
        if loaded.get(key) != finalized.get(key):
            raise SchemaError(f"pin round-trip: {key} 不一致")
    for action in rp.collect_file_actions(loaded):
        if action.get("kind") == "owned-text-render":
            original = next(
                (a for a in rp.collect_file_actions(finalized) if a.get("target") == action.get("target")),
                None,
            )
            if original and _normalize_multiline_text(action.get("content", "")) != _normalize_multiline_text(original.get("content", "")):
                raise SchemaError(
                    f"pin round-trip: multiline content mismatch for {action.get('target')}"
                )


def pin_contract(manifest_path: Path, contract: dict, expected_preimage: str) -> None:
    current = file_digest(manifest_path)
    if current != expected_preimage:
        raise ContractError("root manifest の preimage が plan 時点から変化しました")
    bare = _bare_contract(contract)
    finalized = contract if "contract_digest" in contract else _finalize_contract(bare)
    raw = manifest_path.read_bytes()
    span = _find_top_level_block_span(raw, b"tech_contract")
    block_lines = _dump_yaml({"tech_contract": finalized})
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    replacement = newline.join(line.encode("utf-8") for line in block_lines) + newline
    if span is None:
        if raw and not raw.endswith((b"\n", b"\r\n")):
            raw += newline
        new_raw = raw + replacement
    else:
        new_raw = raw[: span[0]] + replacement + raw[span[1] :]
    _verify_pin_roundtrip(new_raw, finalized)
    genlib.parse_yaml(new_raw.decode("utf-8"))
    rp._atomic_write_bytes(manifest_path, new_raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="承認済み tech_contract lifecycle")
    parser.add_argument("command", choices=("status", "validate", "apply"))
    parser.add_argument("--manifest", type=Path, default=ROOT / "manifest.yaml")
    parser.add_argument("--design-doc", type=Path, required=True)
    parser.add_argument("--draft", type=Path, default=ROOT / "tmp" / "tech-stack-contract-draft.yaml")
    parser.add_argument("--preimage", help="apply に必要な root manifest 全体 SHA-256")
    parser.add_argument("--check", action="store_true", help="read-only renderability / projection 検査")
    args = parser.parse_args(argv)
    try:
        if not args.manifest.is_file() or not args.design_doc.is_file():
            raise SchemaError("manifest または技術設計書が存在しません")
        if args.command == "status":
            contract = load_approved(args.manifest, args.design_doc)
            print(f"READY: approved tech_contract digest={contract_digest(contract)}")
            return 0
        if not args.draft.is_file():
            raise ContractError(f"draft が見つかりません: {args.draft}")
        draft_root = load_yaml(args.draft)
        draft = draft_root.get("tech_contract") if isinstance(draft_root.get("tech_contract"), dict) else draft_root
        if args.command == "validate":
            validate(draft, args.design_doc, require_approval=False, check=args.check)
            print(
                f"PASS: draft digest={contract_digest(draft)} "
                f"projection={projection_digest(draft)}"
            )
            return 0
        if not args.preimage or not re.fullmatch(r"[0-9a-f]{64}", args.preimage):
            raise SchemaError("apply には --preimage <root manifest sha256> が必要です")
        validate(draft, args.design_doc, require_approval=False, check=True)
        sealed = seal_contract(args.manifest, draft, args.preimage)
        args.draft.unlink(missing_ok=True)
        print(f"PASS: tech_contract pinned digest={sealed['contract_digest']}")
        return 0
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (
        SchemaError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        AttributeError,
        OSError,
        re.error,
        rp.PreflightFatal,
    ) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
