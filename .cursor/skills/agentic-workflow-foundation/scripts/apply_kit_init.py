#!/usr/bin/env python3
"""init.yaml から root manifest.yaml の project.*、context_budget、github_access、
生成 skill の feature フラグ（gen.skills）を適用する（Phase 1.5）。

init.yaml は生成物ではなく、初回実行前から存在する初期入力 SoT。
workflow_pattern は "開発型" 固定。
feature フラグは gen.skills を書いた場合だけ書き換える（省略時は root manifest に触れない）。
tech_stack_design.filename は必須で、project.tech_stack_design_filename に書き込む。

exit code:
  0 — 正常（apply 完了）
  1 — apply 所有キーに不正値が残存
  2 — 致命的エラー（init.yaml 不在・スキーマ違反・manifest 破損）
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
GENLIB_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if GENLIB_DIR not in sys.path:
    sys.path.insert(0, GENLIB_DIR)

import genlib  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")
DEFAULT_INIT = os.path.join(ROOT, "init.yaml")

ALLOWED_TOP_KEYS = {
    "version", "project", "context_budget", "tech_stack_design",
    "tech_contract", "provisioning", "github_access", "gen",
}
ALLOWED_GEN_KEYS = {"skills"}
ALLOWED_PROJECT_KEYS = {"name"}
ALLOWED_CONTEXT_BUDGET_KEYS = {"min_context_window_tokens"}
ALLOWED_TECH_STACK_DESIGN_KEYS = {"filename"}
ALLOWED_TECH_CONTRACT_KEYS = {"auto_approve"}
ALLOWED_PROVISIONING_KEYS = {"auto_approve"}
ALLOWED_GITHUB_ACCESS_KEYS = {"api_credential_provider", "keychain"}
ALLOWED_GITHUB_KEYCHAIN_KEYS = {"service", "account"}
FORBIDDEN_TOP_KEYS = {"workflow_pattern", "features", "deep_thinking", "cross_repo_knowledge"}
# 禁止キーのうち、移行先を案内するもの。
FORBIDDEN_TOP_KEY_HINTS = {
    "skills": "トップレベル skills は不可（gen.skills に書くこと）",
}

# gen.skills のキー（生成される skill のディレクトリ名）→ root manifest.yaml の feature フラグのパス。
# outputs[].feature（run_resolved_engine._filter_outputs_by_features）が参照するキーと一致させる。
SKILL_FEATURE_PATHS = {
    "agent-code-review": ("code_review", "enabled"),
    "agent-github-pr": ("github_pr", "enabled"),
    "agent-github-issue": ("github_issue", "enabled"),
    "workflow-orchestrator": ("agent_workflow", "orchestrator_skill"),
    "maintenance-docs-workflow": ("agent_workflow", "maintenance_docs", "enabled"),
    "maintenance-gotchas-workflow": ("agent_workflow", "maintenance_gotchas", "enabled"),
    "requirement-analysis": ("requirement_analysis", "enabled"),
    "deep-thinking": ("deep_thinking", "enabled"),
    "agent-kaizen": ("agent_kaizen", "enabled"),
    "cross-repository-knowledge-link": ("cross_repo_knowledge", "enabled"),
}
# 常時生成（feature 化しない）skill。gen.skills での指定はエラー。
ALWAYS_ON_SKILLS = (
    "session-planning", "session-handover", "campaign-cleanup", "domain-docs",
)
# agent_workflow の土台（workflow docs と gate スクリプト群）に依存する skill。
# どれかが true なら agent_workflow.enabled を true に導出する。
AGENT_WORKFLOW_PATH = ("agent_workflow", "enabled")
AGENT_WORKFLOW_CHILD_SKILLS = (
    "workflow-orchestrator",
    "maintenance-docs-workflow",
    "maintenance-gotchas-workflow",
    "requirement-analysis",
)

FIXED_WORKFLOW_PATTERN = "開発型"
MIN_CONTEXT_WINDOW = 50000
DEFAULT_CONTEXT_WINDOW = 200000
DEFAULT_TECH_CONTRACT_AUTO_APPROVE = False
DEFAULT_PROVISIONING_AUTO_APPROVE = False
DEFAULT_GITHUB_CREDENTIAL_PROVIDER = "github_app"
DEFAULT_GITHUB_KEYCHAIN_SERVICE = "agentic-workflow-github-api"
GITHUB_CREDENTIAL_PROVIDERS = {"github_app", "keychain"}


def _out(level: str, msg: str) -> None:
    print(f"[apply_kit_init] {level}: {msg}")


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\u3040-\u9fff]+", "-", s)
    return s.strip("-")


def _valid_locator(value: object) -> bool:
    return (
        isinstance(value, str)
        and value != ""
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
        and not any(char in value for char in '"\\$`')
    )


def _validate_init(init: dict) -> list[str]:
    """init.yaml のバリデーション。エラーメッセージのリストを返す。"""
    errors: list[str] = []

    version = init.get("version")
    if version != 1:
        errors.append(f"version は 1 必須（実際: {version!r}）")

    for key in init:
        if key in FORBIDDEN_TOP_KEY_HINTS:
            errors.append(f"禁止キー: {key}（{FORBIDDEN_TOP_KEY_HINTS[key]}）")
        elif key in FORBIDDEN_TOP_KEYS:
            errors.append(f"禁止キー: {key}（init.yaml では設定不可）")
        elif key not in ALLOWED_TOP_KEYS:
            errors.append(f"未知トップレベルキー: {key}")

    project = init.get("project")
    if project is not None:
        if not isinstance(project, dict):
            errors.append(f"project はマッピング必須（実際: {type(project).__name__}）")
        else:
            for key in project:
                if key not in ALLOWED_PROJECT_KEYS:
                    errors.append(f"未知キー project.{key}")
            name = project.get("name")
            if name is not None:
                if not isinstance(name, str):
                    errors.append(f"project.name は文字列または null 必須（実際: {type(name).__name__}）")
                elif name == "":
                    errors.append("project.name に空文字は不可（null を使うこと）")

    ctx = init.get("context_budget")
    if ctx is not None:
        if not isinstance(ctx, dict):
            errors.append(f"context_budget はマッピング必須（実際: {type(ctx).__name__}）")
        else:
            for key in ctx:
                if key not in ALLOWED_CONTEXT_BUDGET_KEYS:
                    errors.append(f"未知キー context_budget.{key}")
            raw = ctx.get("min_context_window_tokens")
            if raw is not None:
                try:
                    val = int(raw)
                except (ValueError, TypeError):
                    errors.append(f"min_context_window_tokens は正の整数必須（実際: {raw!r}）")
                else:
                    if val < MIN_CONTEXT_WINDOW:
                        errors.append(f"min_context_window_tokens が小さすぎる（< {MIN_CONTEXT_WINDOW}）: {val}")

    tsd = init.get("tech_stack_design")
    if tsd is None:
        errors.append("tech_stack_design は必須（省略不可）")
    elif not isinstance(tsd, dict):
        errors.append(f"tech_stack_design はマッピング必須（実際: {type(tsd).__name__}）")
    else:
        for key in tsd:
            if key not in ALLOWED_TECH_STACK_DESIGN_KEYS:
                errors.append(f"未知キー tech_stack_design.{key}")
        fn = tsd.get("filename")
        if fn is None:
            errors.append("tech_stack_design.filename は必須（省略不可）")
        elif not isinstance(fn, str):
            errors.append(f"tech_stack_design.filename は文字列必須（実際: {type(fn).__name__}）")
        elif fn == "":
            errors.append("tech_stack_design.filename に空文字は不可")
        else:
            if "/" in fn or "\\" in fn or ".." in fn:
                errors.append(f"tech_stack_design.filename は basename のみ（パス区切り / .. 禁止）: {fn!r}")
            if not fn.endswith(".md"):
                errors.append(f"tech_stack_design.filename は .md で終わる必要がある: {fn!r}")

    tc = init.get("tech_contract")
    if tc is not None:
        if not isinstance(tc, dict):
            errors.append(f"tech_contract はマッピング必須（実際: {type(tc).__name__}）")
        else:
            for key in tc:
                if key not in ALLOWED_TECH_CONTRACT_KEYS:
                    errors.append(f"未知キー tech_contract.{key}")
            auto = tc.get("auto_approve")
            if auto is not None and not isinstance(auto, bool):
                errors.append(
                    f"tech_contract.auto_approve は bool 必須（実際: {type(auto).__name__}）"
                )

    provisioning = init.get("provisioning")
    if provisioning is not None:
        if not isinstance(provisioning, dict):
            errors.append(
                f"provisioning はマッピング必須（実際: {type(provisioning).__name__}）"
            )
        else:
            for key in provisioning:
                if key not in ALLOWED_PROVISIONING_KEYS:
                    errors.append(f"未知キー provisioning.{key}")
            auto = provisioning.get("auto_approve")
            if "auto_approve" in provisioning and not isinstance(auto, bool):
                errors.append(
                    f"provisioning.auto_approve は bool 必須（実際: {type(auto).__name__}）"
                )

    github_access = init.get("github_access")
    if github_access is not None:
        if not isinstance(github_access, dict):
            errors.append(
                f"github_access はマッピング必須（実際: {type(github_access).__name__}）"
            )
        else:
            for key in github_access:
                if key not in ALLOWED_GITHUB_ACCESS_KEYS:
                    errors.append(f"未知キー github_access.{key}")
            provider = github_access.get(
                "api_credential_provider", DEFAULT_GITHUB_CREDENTIAL_PROVIDER
            )
            if not isinstance(provider, str) or provider not in GITHUB_CREDENTIAL_PROVIDERS:
                errors.append(
                    "github_access.api_credential_provider は "
                    f"{sorted(GITHUB_CREDENTIAL_PROVIDERS)} のいずれか必須（実際: {provider!r}）"
                )
            keychain = github_access.get("keychain")
            if keychain is not None and not isinstance(keychain, dict):
                errors.append(
                    f"github_access.keychain はマッピング必須（実際: {type(keychain).__name__}）"
                )
            else:
                keychain = keychain or {}
                for key in keychain:
                    if key not in ALLOWED_GITHUB_KEYCHAIN_KEYS:
                        errors.append(f"未知キー github_access.keychain.{key}")
                service = keychain.get("service", DEFAULT_GITHUB_KEYCHAIN_SERVICE)
                account = keychain.get("account", "")
                if not _valid_locator(service):
                    errors.append(
                        "github_access.keychain.service は空でない制御文字なし文字列必須"
                    )
                if not isinstance(account, str) or any(
                    ord(char) < 32
                    or ord(char) == 127
                    or char in '"\\$`'
                    for char in account
                ):
                    errors.append(
                        "github_access.keychain.account は制御文字なし文字列必須"
                    )
                elif provider == "keychain" and account == "":
                    errors.append(
                        "provider=keychain では github_access.keychain.account は非空必須"
                    )

    errors.extend(_validate_gen(init))

    return errors


def _validate_gen(init: dict) -> list[str]:
    """gen（生成ファイルの制御）のバリデーション。gen が無ければ検査しない。"""
    errors: list[str] = []
    if "gen" not in init:
        return errors
    gen = init["gen"]
    if not isinstance(gen, dict):
        errors.append(
            f"gen はマッピング必須（実際: {type(gen).__name__}）。使わないなら gen ごと削除すること"
        )
        return errors
    for key in gen:
        if key not in ALLOWED_GEN_KEYS:
            errors.append(f"未知キー gen.{key}")
    if "skills" not in gen:
        return errors
    skills = gen["skills"]
    if not isinstance(skills, dict):
        errors.append(
            f"gen.skills はマッピング必須（実際: {type(skills).__name__}）。"
            "使わないなら gen.skills ごと削除すること"
        )
        return errors
    for name, value in skills.items():
        if name in ALWAYS_ON_SKILLS:
            errors.append(f"gen.skills.{name} は常時生成のため指定不可")
        elif name not in SKILL_FEATURE_PATHS:
            errors.append(
                f"未知キー gen.skills.{name}（指定可能: {sorted(SKILL_FEATURE_PATHS)}）"
            )
        elif not isinstance(value, bool):
            errors.append(
                f"gen.skills.{name} は bool 必須（実際: {type(value).__name__}）"
            )
    if errors:
        return errors
    # skill 間の依存。個別の値が妥当なときだけ評価する。
    resolved = _resolve_skills(init)
    workflow_on, _ = _derive_agent_workflow(resolved)
    if workflow_on and not resolved["requirement-analysis"]:
        errors.append(
            "gen.skills.requirement-analysis: false は、workflow 系 skill "
            f"{list(AGENT_WORKFLOW_CHILD_SKILLS)} のいずれかが true の間は指定不可。"
            "gate-artifact.py が step1 の requirement-analysis 系フィールドを必須とするため、"
            "生成後の audit（test_worker_contract）が失敗する。"
            "requirement-analysis を true にするか、workflow 系 skill をすべて false にすること"
        )
    return errors


def _resolve_skills(init: dict) -> dict | None:
    """gen.skills を全 skill の bool へ解決する。gen.skills が無ければ None（root に触れない）。

    書いた場合は全項目の SoT になり、省略したキーは true（seed 既定）。
    """
    gen = init.get("gen")
    if not isinstance(gen, dict) or "skills" not in gen:
        return None
    given = gen["skills"] or {}
    return {name: bool(given.get(name, True)) for name in SKILL_FEATURE_PATHS}


def _derive_agent_workflow(skills: dict) -> tuple[bool, list[str]]:
    """agent_workflow.enabled を子 skill の OR で導出する。要因（true の子 skill）も返す。"""
    causes = [name for name in AGENT_WORKFLOW_CHILD_SKILLS if skills.get(name)]
    return bool(causes), causes


def _resolve_values(init: dict, manifest_dir: str) -> dict:
    """init.yaml + 自動導出から apply する値を解決する。"""
    project = init.get("project") or {}
    ctx = init.get("context_budget") or {}
    tsd = init.get("tech_stack_design") or {}
    tc = init.get("tech_contract") or {}
    provisioning = init.get("provisioning") or {}
    github_access = init.get("github_access") or {}
    keychain = github_access.get("keychain") or {}

    name = project.get("name")
    if name is None:
        name = os.path.basename(os.path.abspath(manifest_dir))
    slug = _slugify(name)
    if not slug:
        raise ValueError(f"slug が空になる name: {name!r}")

    min_tokens = ctx.get("min_context_window_tokens")
    if min_tokens is None:
        min_tokens = DEFAULT_CONTEXT_WINDOW
    else:
        min_tokens = int(min_tokens)

    tech_stack_design_filename = tsd.get("filename")
    if not tech_stack_design_filename:
        raise ValueError("tech_stack_design.filename が未設定")

    auto_approve = tc.get("auto_approve")
    if auto_approve is None:
        auto_approve = DEFAULT_TECH_CONTRACT_AUTO_APPROVE
    else:
        auto_approve = bool(auto_approve)

    provisioning_auto_approve = provisioning.get("auto_approve")
    if provisioning_auto_approve is None:
        provisioning_auto_approve = DEFAULT_PROVISIONING_AUTO_APPROVE
    else:
        provisioning_auto_approve = bool(provisioning_auto_approve)

    github_credential_provider = github_access.get(
        "api_credential_provider", DEFAULT_GITHUB_CREDENTIAL_PROVIDER
    )
    github_keychain_service = keychain.get(
        "service", DEFAULT_GITHUB_KEYCHAIN_SERVICE
    )
    github_keychain_account = keychain.get("account", "")

    skills = _resolve_skills(init)
    agent_workflow_enabled = None
    agent_workflow_causes: list[str] = []
    if skills is not None:
        agent_workflow_enabled, agent_workflow_causes = _derive_agent_workflow(skills)

    return {
        "skills": skills,
        "agent_workflow_enabled": agent_workflow_enabled,
        "agent_workflow_causes": agent_workflow_causes,
        "name": name,
        "slug": slug,
        "workflow_pattern": FIXED_WORKFLOW_PATTERN,
        "min_context_window_tokens": min_tokens,
        "tech_stack_design_filename": tech_stack_design_filename,
        "tech_contract_auto_approve": auto_approve,
        "provisioning_auto_approve": provisioning_auto_approve,
        "github_credential_provider": github_credential_provider,
        "github_keychain_service": github_keychain_service,
        "github_keychain_account": github_keychain_account,
    }


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _yaml_quote(value: str) -> str:
    s = str(value)
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


def _find_top_block(lines: list[str], key: str):
    start = None
    for idx, line in enumerate(lines):
        if line.rstrip() == f"{key}:" and _indent_of(line) == 0:
            start = idx
            break
    if start is None:
        return None, None
    last = start
    j = start + 1
    while j < len(lines):
        if lines[j].strip() == "":
            j += 1
            continue
        if _indent_of(lines[j]) > 0:
            last = j
            j += 1
            continue
        break
    return start, last


def _set_scalar(lines: list[str], parent: str, key: str, value: str) -> list[str]:
    """parent ブロック内の key: value を更新する。"""
    p_start, p_last = _find_top_block(lines, parent)
    if p_start is None:
        return lines

    pattern = re.compile(rf"^(\s+){re.escape(key)}:\s")
    for idx in range(p_start + 1, p_last + 1):
        m = pattern.match(lines[idx])
        if m:
            indent = m.group(1)
            lines[idx] = f"{indent}{key}: {value}"
            return lines
    return lines


def _set_nested_scalar(lines: list[str], parent: str, child: str, key: str, value: str) -> list[str]:
    """parent > child ブロック内の key: value を更新する。"""
    p_start, p_last = _find_top_block(lines, parent)
    if p_start is None:
        return lines

    child_pattern = re.compile(rf"^(\s+){re.escape(child)}:")
    c_start = None
    for idx in range(p_start + 1, p_last + 1):
        if child_pattern.match(lines[idx]):
            c_start = idx
            break
    if c_start is None:
        return lines

    c_indent = _indent_of(lines[c_start])
    c_last = c_start
    j = c_start + 1
    while j <= p_last:
        if lines[j].strip() == "":
            j += 1
            continue
        if _indent_of(lines[j]) > c_indent:
            c_last = j
            j += 1
            continue
        break

    key_pattern = re.compile(rf"^(\s+){re.escape(key)}:\s")
    for idx in range(c_start + 1, c_last + 1):
        m = key_pattern.match(lines[idx])
        if m:
            indent = m.group(1)
            lines[idx] = f"{indent}{key}: {value}"
            return lines
    return lines


def _set_or_insert_scalar(lines: list[str], parent: str, key: str, value: str,
                          after_key: str | None = None) -> list[str]:
    """parent ブロック内の key: value を更新する。キーが存在しなければ挿入する。"""
    result = _set_scalar(lines, parent, key, value)
    pattern = re.compile(rf"^(\s+){re.escape(key)}:\s")
    p_start, p_last = _find_top_block(lines, parent)
    if p_start is None:
        return result
    for idx in range(p_start + 1, p_last + 1):
        if pattern.match(lines[idx]):
            return result

    indent = "  "
    insert_at = p_last + 1
    if after_key:
        after_pattern = re.compile(rf"^(\s+){re.escape(after_key)}:\s")
        for idx in range(p_start + 1, p_last + 1):
            m = after_pattern.match(lines[idx])
            if m:
                indent = m.group(1)
                insert_at = idx + 1
                break
    lines.insert(insert_at, f"{indent}{key}: {value}")
    return lines


def _set_github_access(lines: list[str], values: dict) -> list[str]:
    block = [
        "github_access:",
        f"  api_credential_provider: {_yaml_quote(values['github_credential_provider'])}",
        "  keychain:",
        f"    service: {_yaml_quote(values['github_keychain_service'])}",
        f"    account: {_yaml_quote(values['github_keychain_account'])}",
    ]
    start, last = _find_top_block(lines, "github_access")
    if start is not None:
        return lines[:start] + block + lines[last + 1:]

    insert_at = len(lines)
    context_start, _ = _find_top_block(lines, "context_budget")
    if context_start is not None:
        insert_at = context_start
    prefix = [] if insert_at == 0 or lines[insert_at - 1].strip() == "" else [""]
    suffix = [] if insert_at >= len(lines) or lines[insert_at].strip() == "" else [""]
    return lines[:insert_at] + prefix + block + suffix + lines[insert_at:]


class ProjectionError(ValueError):
    """root manifest へ投影できない（対象ブロック・キーの欠落や bool 以外の値）。"""


_BOOL_VALUE_LINE = re.compile(r"^(\s*\S+:\s+)(true|false)(\s*(?:#.*)?)$")


def _direct_child_indent(lines: list[str], start: int, last: int) -> int | None:
    """start ブロック直下の子キーのインデント幅（最初の非空・非コメント行）を返す。"""
    for idx in range(start + 1, last + 1):
        stripped = lines[idx].strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        return _indent_of(lines[idx])
    return None


def _find_child_block(lines: list[str], start: int, last: int, key: str):
    """start ブロック直下の key ブロック（値なしの `key:` 行）の (開始, 終了) を返す。"""
    indent = _direct_child_indent(lines, start, last)
    if indent is None:
        return None
    pattern = re.compile(rf"^ {{{indent}}}{re.escape(key)}:\s*(#.*)?$")
    for idx in range(start + 1, last + 1):
        if not pattern.match(lines[idx]):
            continue
        child_last = idx
        j = idx + 1
        while j <= last:
            if lines[j].strip() == "":
                j += 1
                continue
            if _indent_of(lines[j]) > indent:
                child_last = j
                j += 1
                continue
            break
        return idx, child_last
    return None


def _find_direct_child_line(lines: list[str], start: int, last: int, key: str) -> int | None:
    """start ブロック直下（孫は対象外）の `key: value` 行の位置を返す。"""
    indent = _direct_child_indent(lines, start, last)
    if indent is None:
        return None
    pattern = re.compile(rf"^ {{{indent}}}{re.escape(key)}:\s")
    for idx in range(start + 1, last + 1):
        if pattern.match(lines[idx]):
            return idx
    return None


def _set_bool_at_path(lines: list[str], path: tuple, value: bool) -> bool:
    """path（トップレベルキーから葉まで）の bool 行を書き換える。見つからなければ False。

    既存の _set_scalar は対象が無いと何もせず返るため、投影の成否を呼び出し側が判定できるよう
    本関数は書き換えの有無を返す。インラインコメントは保持する。
    """
    start, last = _find_top_block(lines, path[0])
    if start is None:
        return False
    for key in path[1:-1]:
        child = _find_child_block(lines, start, last, key)
        if child is None:
            return False
        start, last = child
    leaf = _find_direct_child_line(lines, start, last, path[-1])
    if leaf is None:
        return False
    match = _BOOL_VALUE_LINE.match(lines[leaf])
    if not match:
        return False
    lines[leaf] = f"{match.group(1)}{'true' if value else 'false'}{match.group(3)}"
    return True


def _set_skill_features(lines: list[str], values: dict) -> list[str]:
    """gen.skills を root manifest の feature フラグへ投影する。投影できなければ ProjectionError。"""
    skills = values.get("skills")
    if skills is None:
        return lines
    missing: list[str] = []
    for name, enabled in skills.items():
        path = SKILL_FEATURE_PATHS[name]
        if not _set_bool_at_path(lines, path, enabled):
            missing.append(f"{name} -> {'.'.join(path)}")
    if not _set_bool_at_path(lines, AGENT_WORKFLOW_PATH, values["agent_workflow_enabled"]):
        missing.append(f"(導出) -> {'.'.join(AGENT_WORKFLOW_PATH)}")
    if missing:
        raise ProjectionError(
            "root manifest に投影先の bool キーが無い、または bool 以外の値: " + ", ".join(missing)
        )
    return lines


def _render_manifest(content: str, values: dict) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]

    lines = _set_scalar(lines, "project", "name", _yaml_quote(values["name"]))
    lines = _set_scalar(lines, "project", "slug", _yaml_quote(values["slug"]))
    lines = _set_scalar(lines, "project", "workflow_pattern", _yaml_quote(values["workflow_pattern"]))
    lines = _set_or_insert_scalar(
        lines, "project", "tech_stack_design_filename",
        _yaml_quote(values["tech_stack_design_filename"]),
        after_key="workflow_pattern",
    )
    lines = _set_or_insert_scalar(
        lines, "project", "tech_contract_auto_approve",
        "true" if values["tech_contract_auto_approve"] else "false",
        after_key="tech_stack_design_filename",
    )
    lines = _set_or_insert_scalar(
        lines, "project", "provisioning_auto_approve",
        "true" if values["provisioning_auto_approve"] else "false",
        after_key="tech_contract_auto_approve",
    )
    lines = _set_nested_scalar(
        lines, "project", "context_budget",
        "min_context_window_tokens", str(values["min_context_window_tokens"])
    )
    lines = _set_github_access(lines, values)
    lines = _set_skill_features(lines, values)

    return newline.join(lines)


def _verify_owned_keys(manifest: dict, expected: dict | None = None) -> list[str]:
    """apply 所有キーが正しく設定されているか検証する。"""
    issues: list[str] = []
    project = manifest.get("project") or {}

    wp = project.get("workflow_pattern")
    if wp != FIXED_WORKFLOW_PATTERN:
        issues.append(f"project.workflow_pattern が {FIXED_WORKFLOW_PATTERN!r} でない: {wp!r}")

    for key in ("name", "slug"):
        val = project.get(key)
        if val is None or val == "[要確認]":
            issues.append(f"project.{key} が未確定: {val!r}")

    tsd_fn = project.get("tech_stack_design_filename")
    if tsd_fn is None or tsd_fn == "[要確認]":
        issues.append(f"project.tech_stack_design_filename が未確定: {tsd_fn!r}")

    auto = project.get("tech_contract_auto_approve")
    if auto is not None and not isinstance(auto, bool):
        issues.append(f"project.tech_contract_auto_approve は bool 必須: {auto!r}")

    provisioning_auto = project.get("provisioning_auto_approve")
    if provisioning_auto is not None and not isinstance(provisioning_auto, bool):
        issues.append(
            f"project.provisioning_auto_approve は bool 必須: {provisioning_auto!r}"
        )

    ctx = project.get("context_budget") or {}
    raw = ctx.get("min_context_window_tokens")
    if raw is None or str(raw) == "[要確認]":
        issues.append(f"project.context_budget.min_context_window_tokens が未確定: {raw!r}")

    github_access = manifest.get("github_access") or {}
    keychain = github_access.get("keychain") or {}
    actual = {
        "github_credential_provider": github_access.get("api_credential_provider"),
        "github_keychain_service": keychain.get("service"),
        "github_keychain_account": keychain.get("account"),
    }
    if actual["github_credential_provider"] not in GITHUB_CREDENTIAL_PROVIDERS:
        issues.append(
            "github_access.api_credential_provider が不正: "
            f"{actual['github_credential_provider']!r}"
        )
    if not _valid_locator(actual["github_keychain_service"]):
        issues.append("github_access.keychain.service が未確定または不正")
    account = actual["github_keychain_account"]
    if not isinstance(account, str) or any(
        ord(char) < 32 or ord(char) == 127 or char in '"\\$`'
        for char in account
    ):
        issues.append("github_access.keychain.account が不正")
    if actual["github_credential_provider"] == "keychain" and account == "":
        issues.append("provider=keychain で github_access.keychain.account が空")
    if expected is not None:
        for key, actual_value in actual.items():
            if actual_value != expected[key]:
                issues.append(
                    f"{key} の投影不一致: expected={expected[key]!r}, actual={actual_value!r}"
                )
        issues.extend(_verify_skill_features(manifest, expected))

    return issues


def _manifest_value_at(manifest: dict, path: tuple):
    node: object = manifest
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _verify_skill_features(manifest: dict, expected: dict) -> list[str]:
    """gen.skills の投影結果（10 項目 + 導出した agent_workflow.enabled）が root と一致するか検査する。"""
    skills = expected.get("skills")
    if skills is None:
        return []
    issues: list[str] = []
    checks = [(name, SKILL_FEATURE_PATHS[name], enabled) for name, enabled in skills.items()]
    checks.append(("(導出)", AGENT_WORKFLOW_PATH, expected["agent_workflow_enabled"]))
    for name, path, enabled in checks:
        actual = _manifest_value_at(manifest, path)
        if actual is not enabled:
            issues.append(
                f"{'.'.join(path)} の投影不一致（{name}）: expected={enabled!r}, actual={actual!r}"
            )
    return issues


def _report_skills(values: dict) -> None:
    """gen.skills の解決結果と、導出した agent_workflow の土台を表示する。"""
    skills = values.get("skills")
    if skills is None:
        _out("INFO", "gen.skills 未指定。feature フラグ（root manifest）には触れない")
        return
    enabled = [name for name, flag in skills.items() if flag]
    disabled = [name for name, flag in skills.items() if not flag]
    _out("INFO", f"gen.skills: 有効={enabled} 無効={disabled}")
    if values["agent_workflow_enabled"]:
        _out(
            "INFO",
            "agent_workflow.enabled=true を導出（要因: "
            f"{values['agent_workflow_causes']}）。workflow docs と gate スクリプト群が生成対象になる",
        )
    else:
        _out(
            "INFO",
            "agent_workflow.enabled=false を導出（workflow 系 skill がすべて無効）。"
            "workflow docs と gate スクリプト群は生成対象から外れる",
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="init.yaml → root manifest.yaml の project 適用")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--init", default=DEFAULT_INIT)
    parser.add_argument("--check", action="store_true", help="dry-run: 解決結果を表示するが書き込まない")
    args = parser.parse_args(argv)

    if not os.path.exists(args.init):
        _out("ERROR", f"init.yaml が見つからない: {args.init}")
        return 2

    try:
        init = genlib.load_manifest(args.init)
    except genlib.YamlError as e:
        _out("ERROR", f"init.yaml 解析失敗: {e}")
        return 2

    errors = _validate_init(init)
    if errors:
        for err in errors:
            _out("ERROR", err)
        return 2

    if not os.path.exists(args.manifest):
        _out("ERROR", f"root manifest が見つからない: {args.manifest}")
        return 2
    try:
        manifest = genlib.load_manifest(args.manifest)
    except genlib.YamlError as e:
        _out("ERROR", f"manifest 解析失敗: {e}")
        return 2

    manifest_dir = os.path.dirname(os.path.abspath(args.manifest))
    try:
        values = _resolve_values(init, manifest_dir)
    except ValueError as e:
        _out("ERROR", str(e))
        return 2

    _out("INFO", f"name={values['name']!r} slug={values['slug']!r} "
         f"workflow_pattern={values['workflow_pattern']!r} "
         f"tech_stack_design_filename={values['tech_stack_design_filename']!r} "
         f"tech_contract_auto_approve={values['tech_contract_auto_approve']} "
         f"provisioning_auto_approve={values['provisioning_auto_approve']} "
         f"github_provider={values['github_credential_provider']!r} "
         f"github_keychain_service={values['github_keychain_service']!r} "
         f"github_keychain_account={values['github_keychain_account']!r} "
         f"min_context_window_tokens={values['min_context_window_tokens']}")
    _report_skills(values)

    if args.check:
        _out("INFO", "--check モード。書き込みスキップ")
        return 0

    with open(args.manifest, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        new_content = _render_manifest(content, values)
    except ProjectionError as e:
        _out("ERROR", str(e))
        return 2
    changed = new_content != content

    if changed:
        with open(args.manifest, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)

    # 書き込み後の検証
    updated_manifest = genlib.load_manifest(args.manifest)
    issues = _verify_owned_keys(updated_manifest, values)
    if issues:
        for issue in issues:
            _out("WARN", issue)
        return 1

    _out("PASS", f"init.yaml → root manifest へ反映（{'更新あり' if changed else '更新なし=冪等'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
