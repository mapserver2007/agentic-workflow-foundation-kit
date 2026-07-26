#!/usr/bin/env python3
"""tech_stack から CodeRabbit 設定を決定する（Phase 1.66 スクリプトステップ）。

tech_stack.items のテクノロジー名をカテゴリ分類し、
- 有効化/無効化する CodeRabbit ツールリスト
- path_filters
を決定論的に導出して root manifest.yaml の coderabbit セクションに書き込む。

path_instructions は AI ステップで生成され manifest に永続化された値を
パススルーする。tech_stack のハッシュが変わった場合は AI 再生成が必要な旨を
警告し、既存値を保持したまま exit 0 する。
"""
from __future__ import annotations

import argparse
import hashlib
import json
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

# ── テクノロジーカテゴリ判定 ──────────────────────────────────
# tech_stack.items[].technology を正規化し、いずれかのキーワードに合致すればカテゴリを付与。
TECH_CATEGORIES: dict[str, list[str]] = {
    "typescript": ["typescript"],
    "javascript": ["javascript", "node.js", "nodejs"],
    "react": ["react", "next.js", "nextjs"],
    "workers": ["cloudflare workers", "cloudflare", "workerd"],
    "openapi": ["openapi"],
    "hono": ["hono"],
    "python": ["python", "django", "flask", "fastapi", "pytest"],
    "go": ["go", "golang"],
    "ruby": ["ruby", "rails"],
    "php": ["php", "laravel", "symfony"],
    "kotlin": ["kotlin"],
    "java": ["java", "spring", "maven", "gradle"],
    "swift": ["swift"],
    "rust": ["rust", "cargo"],
    "c_cpp": ["c++", "cpp", "cmake"],
    "fortran": ["fortran"],
    "lua": ["lua"],
    "pnpm": ["pnpm"],
    "turborepo": ["turborepo", "turbo"],
    "vitest": ["vitest"],
    "docker": ["docker", "dockerfile"],
}

# ── CodeRabbit ツール ↔ カテゴリ対応 ──────────────────────────
# カテゴリが検出されればツールを有効化、どのカテゴリも検出されなければ無効化。
TOOL_TECH_MAP: dict[str, list[str]] = {
    "eslint": ["typescript", "javascript", "react"],
    "biome": ["typescript", "javascript", "react"],
    "oxc": ["typescript", "javascript", "react"],
    "ruff": ["python"],
    "pylint": ["python"],
    "flake8": ["python"],
    "phpstan": ["php"],
    "phpmd": ["php"],
    "phpcs": ["php"],
    "golangci-lint": ["go"],
    "detekt": ["kotlin", "java"],
    "rubocop": ["ruby"],
    "brakeman": ["ruby"],
    "swiftlint": ["swift"],
    "clippy": ["rust"],
    "pmd": ["java", "kotlin"],
    "fbinfer": ["java"],
    "clang": ["c_cpp"],
    "cppcheck": ["c_cpp"],
    "fortitude-lint": ["fortran"],
    "luacheck": ["lua"],
    "oasdiff": ["openapi"],
    "hadolint": ["docker"],
}

ALWAYS_ENABLED_TOOLS = [
    "markdownlint",
    "yamllint",
    "shellcheck",
    "gitleaks",
    "trufflehog",
    "github-checks",
    "ast-grep",
    "skillspector",
    "osv-scanner",
    "actionlint",
    "zizmor",
]

# ── パスフィルタ ──────────────────────────────────────────────
ALWAYS_FILTERS = [
    "!**/*.lock",
    "!**/*.generated.*",
    "!**/dist/**",
    "!**/node_modules/**",
    "!**/*.min.js",
    "!**/*.min.css",
    "!**/coverage/**",
    "!**/__snapshots__/**",
    "!**/.cursor/plans/**",
    "!**/.cursor/.session/**",
    "!**/tmp/**",
    "!**/.DS_Store",
]

CATEGORY_FILTERS: dict[str, list[str]] = {
    "pnpm": ["!**/pnpm-lock.yaml"],
}


def _out(level: str, msg: str) -> None:
    print(f"[resolve_coderabbit] {level}: {msg}")


def _yaml_quote(value: str) -> str:
    s = "" if value is None else str(value)
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


def _normalize(value: str) -> str:
    text = (value or "").replace("`", "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _contains_keyword(text: str, keyword: str) -> bool:
    """単語境界で技術キーワードを判定し、java/javascript などの誤一致を避ける。"""
    if " " in keyword:
        return keyword in text
    return re.search(
        rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])",
        text,
    ) is not None


def _detect_categories(manifest: dict) -> set[str]:
    """tech_stack.items からテクノロジーカテゴリ集合を返す。"""
    items = (manifest.get("tech_stack") or {}).get("items") or []
    detected: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        tech = _normalize(item.get("technology", ""))
        layer = _normalize(item.get("layer", ""))
        combined = f"{layer} {tech}"
        for category, keywords in TECH_CATEGORIES.items():
            for kw in keywords:
                if _contains_keyword(combined, kw):
                    detected.add(category)
    return detected


def _resolve_tools(categories: set[str]):
    """カテゴリ集合から有効/無効ツールリストを返す。

    biome と oxc は JS/TS 解析で責務が重複するため、biome が有効なら oxc を無効化する。
    """
    enabled = []
    disabled = []
    for tool, cats in sorted(TOOL_TECH_MAP.items()):
        if any(cat in categories for cat in cats):
            enabled.append(tool)
        else:
            disabled.append(tool)
    if "biome" in enabled and "oxc" in enabled:
        enabled.remove("oxc")
        disabled.append("oxc")
        disabled.sort()
    return enabled, disabled


def _resolve_path_filters(categories: set[str]) -> list[str]:
    filters = list(ALWAYS_FILTERS)
    for cat, cat_filters in CATEGORY_FILTERS.items():
        if cat in categories:
            filters.extend(cat_filters)
    return filters


def _compute_tech_stack_hash(manifest: dict) -> str:
    """tech_stack.items の安定ハッシュを計算する。

    items をソート済み JSON に正規化してから SHA-256 の先頭 12 文字を返す。
    tech_stack が変更されない限り同一値を返し、パターン B の発火条件判定に使う。
    """
    items = (manifest.get("tech_stack") or {}).get("items") or []
    normalized = json.dumps(items, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def resolve(manifest: dict) -> dict:
    """tech_stack から coderabbit 設定を導出する。

    ツールと path_filters は決定論的に導出する。
    path_instructions は manifest の既存値をパススルーし、tech_stack の
    ハッシュが変わった場合は AI 再生成が必要な旨を警告する。

    coderabbit.enabled は seed default: true。変更は root manifest 直接編集であり、
    本スクリプトでは既存の enabled 値を保持する（未設定時は True をデフォルトとする）。
    """
    existing = manifest.get("coderabbit") or {}
    is_enabled = existing.get("enabled", True)
    if is_enabled is None:
        is_enabled = True

    categories = _detect_categories(manifest)
    if not categories:
        _out("WARN", "tech_stack にテクノロジーが検出されなかったためデフォルト設定を使用")

    enabled, disabled = _resolve_tools(categories)
    path_filters = _resolve_path_filters(categories)

    current_hash = _compute_tech_stack_hash(manifest)
    stored_hash = existing.get("_tech_stack_hash", "")
    existing_instructions = existing.get("path_instructions") or []

    needs_ai_regen = False
    if not existing_instructions:
        _out("WARN", "path_instructions が未設定です。Phase 1.66 AI ステップで生成してください")
        needs_ai_regen = True
    elif current_hash != stored_hash:
        _out("WARN", f"tech_stack が変更されました（hash: {stored_hash} → {current_hash}）。"
             "path_instructions の AI 再生成を推奨します")
        needs_ai_regen = True

    if not needs_ai_regen:
        _out("INFO", f"tech_stack hash 一致（{current_hash}）— path_instructions をパススルー")

    _out("INFO", f"enabled: {is_enabled}")
    _out("INFO", f"検出カテゴリ: {sorted(categories)}")
    _out("INFO", f"有効ツール: {enabled}")
    _out("INFO", f"無効ツール: {disabled}")
    _out("INFO", f"path_instructions: {len(existing_instructions)} 件（パススルー）")

    return {
        "enabled": is_enabled,
        "language": "ja-JP",
        "tools_enabled": [{"name": t} for t in ALWAYS_ENABLED_TOOLS + enabled],
        "tools_disabled": [{"name": t} for t in disabled],
        "path_filters": path_filters,
        "path_instructions": existing_instructions,
        "_tech_stack_hash": current_hash,
        "_needs_ai_regen": needs_ai_regen,
    }


# ── manifest 書き込み ────────────────────────────────────────

def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_top_block(lines, key: str):
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


def _build_coderabbit_block(resolved: dict) -> list[str]:
    lines = ["coderabbit:"]
    enabled_str = "true" if resolved["enabled"] else "false"
    lines.append(f"  enabled: {enabled_str}")
    lines.append(f"  language: {_yaml_quote(resolved['language'])}")
    lines.append(f"  _tech_stack_hash: {_yaml_quote(resolved['_tech_stack_hash'])}")

    lines.append("  tools_enabled:")
    for tool in resolved["tools_enabled"]:
        lines.append(f"    - name: {_yaml_quote(tool['name'])}")

    lines.append("  tools_disabled:")
    for tool in resolved["tools_disabled"]:
        lines.append(f"    - name: {_yaml_quote(tool['name'])}")

    lines.append("  path_filters:")
    for f in resolved["path_filters"]:
        lines.append(f"    - {_yaml_quote(f)}")

    lines.append("  path_instructions:")
    for pi in resolved["path_instructions"]:
        lines.append(f"    - path: {_yaml_quote(pi['path'])}")
        lines.append(f"      instructions: {_yaml_quote(pi['instructions'])}")

    return lines


def _render_manifest(content: str, resolved: dict) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]
    block = _build_coderabbit_block(resolved)

    start, last = _find_top_block(lines, "coderabbit")
    if start is not None:
        new_lines = lines[:start] + block + lines[last + 1:]
    else:
        after_key = "domain_docs"
        a_start, a_last = _find_top_block(lines, after_key)
        if a_start is not None:
            insert_at = a_last + 1
            new_lines = lines[:insert_at] + [""] + block + lines[insert_at:]
        else:
            new_lines = lines + [""] + block

    return newline.join(new_lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="tech_stack から CodeRabbit 設定を決定する"
    )
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        _out("ERROR", f"manifest が見つからない: {args.manifest}")
        return 2
    try:
        manifest = genlib.load_manifest(args.manifest)
    except genlib.YamlError as e:
        _out("ERROR", f"manifest 解析失敗: {e}")
        return 2

    resolved = resolve(manifest)
    needs_ai_regen = resolved.pop("_needs_ai_regen", False)

    with open(args.manifest, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = _render_manifest(content, resolved)
    changed = new_content != content

    if args.check:
        _out("INFO", f"CodeRabbit 設定解決結果: 書き換え{'あり' if changed else 'なし'}（--check）")
        return 0
    if changed:
        with open(args.manifest, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
    _out("PASS", f"CodeRabbit 設定を root manifest へ反映（{'更新あり' if changed else '更新なし=冪等'}）")
    if needs_ai_regen:
        _out("ACTION", "path_instructions の AI 再生成が必要です。"
             "SKILL.md Phase 1.66 AI ステップを実行してください")
    return 0


if __name__ == "__main__":
    sys.exit(main())
