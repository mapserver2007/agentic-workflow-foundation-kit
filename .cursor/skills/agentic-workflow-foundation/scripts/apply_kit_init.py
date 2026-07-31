#!/usr/bin/env python3
"""init.yaml から root manifest.yaml の project.* と context_budget を適用する（Phase 1.5）。

init.yaml は生成物ではなく、初回実行前から存在する初期入力 SoT。
workflow_pattern は "開発型" 固定。feature フラグは触らない。
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

ALLOWED_TOP_KEYS = {"version", "project", "context_budget", "tech_stack_design", "tech_contract"}
ALLOWED_PROJECT_KEYS = {"name"}
ALLOWED_CONTEXT_BUDGET_KEYS = {"min_context_window_tokens"}
ALLOWED_TECH_STACK_DESIGN_KEYS = {"filename"}
ALLOWED_TECH_CONTRACT_KEYS = {"auto_approve"}
FORBIDDEN_TOP_KEYS = {"workflow_pattern", "features", "deep_thinking", "cross_repo_knowledge"}

FIXED_WORKFLOW_PATTERN = "開発型"
MIN_CONTEXT_WINDOW = 50000
DEFAULT_CONTEXT_WINDOW = 200000
DEFAULT_TECH_CONTRACT_AUTO_APPROVE = False


def _out(level: str, msg: str) -> None:
    print(f"[apply_kit_init] {level}: {msg}")


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\u3040-\u9fff]+", "-", s)
    return s.strip("-")


def _validate_init(init: dict) -> list[str]:
    """init.yaml のバリデーション。エラーメッセージのリストを返す。"""
    errors: list[str] = []

    version = init.get("version")
    if version != 1:
        errors.append(f"version は 1 必須（実際: {version!r}）")

    for key in init:
        if key in FORBIDDEN_TOP_KEYS:
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

    return errors


def _resolve_values(init: dict, manifest_dir: str) -> dict:
    """init.yaml + 自動導出から apply する値を解決する。"""
    project = init.get("project") or {}
    ctx = init.get("context_budget") or {}
    tsd = init.get("tech_stack_design") or {}
    tc = init.get("tech_contract") or {}

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

    return {
        "name": name,
        "slug": slug,
        "workflow_pattern": FIXED_WORKFLOW_PATTERN,
        "min_context_window_tokens": min_tokens,
        "tech_stack_design_filename": tech_stack_design_filename,
        "tech_contract_auto_approve": auto_approve,
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
    lines = _set_nested_scalar(
        lines, "project", "context_budget",
        "min_context_window_tokens", str(values["min_context_window_tokens"])
    )

    return newline.join(lines)


def _verify_owned_keys(manifest: dict) -> list[str]:
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

    ctx = project.get("context_budget") or {}
    raw = ctx.get("min_context_window_tokens")
    if raw is None or str(raw) == "[要確認]":
        issues.append(f"project.context_budget.min_context_window_tokens が未確定: {raw!r}")

    return issues


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
         f"min_context_window_tokens={values['min_context_window_tokens']}")

    if args.check:
        _out("INFO", "--check モード。書き込みスキップ")
        return 0

    with open(args.manifest, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = _render_manifest(content, values)
    changed = new_content != content

    if changed:
        with open(args.manifest, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)

    # 書き込み後の検証
    updated_manifest = genlib.load_manifest(args.manifest)
    issues = _verify_owned_keys(updated_manifest)
    if issues:
        for issue in issues:
            _out("WARN", issue)
        return 1

    _out("PASS", f"init.yaml → root manifest へ反映（{'更新あり' if changed else '更新なし=冪等'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
