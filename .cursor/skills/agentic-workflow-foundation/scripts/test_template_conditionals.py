#!/usr/bin/env python3
"""foundation / github_pr / AGENTS 任意ブロックの生成条件回帰。"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
ROOT = SKILL_DIR.parents[2]
ENGINE_SCRIPTS = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
if str(ENGINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ENGINE_SCRIPTS))

import genlib  # noqa: E402


def _manifest() -> dict:
    return genlib.load_manifest(str(SKILL_DIR / "manifest.yaml"))


def _conditionals(template: Path, manifest: dict) -> str:
    return genlib._process_ifs(
        template.read_text(encoding="utf-8"),
        manifest,
    )


def test_foundation_false_removes_self_validation_references() -> None:
    manifest = _manifest()
    manifest["foundation"]["enabled"] = False
    quality_gate = _conditionals(
        SKILL_DIR / "templates" / "docs" / "QUALITY_GATE.md.template",
        manifest,
    )
    assert "基盤ジェネレータ" not in quality_gate
    assert "§4" not in quality_gate

    deep_thinking = _conditionals(
        SKILL_DIR / "templates" / "skills" / "deep-thinking" / "SKILL.md.template",
        manifest,
    )
    assert "QUALITY_GATE.md §4.1" not in deep_thinking


def test_github_pr_false_removes_wrapper_guidance() -> None:
    manifest = _manifest()
    manifest["github_pr"]["enabled"] = False
    guard = _conditionals(
        SKILL_DIR / "templates" / "hooks" / "guard-git-write.sh.template",
        manifest,
    )
    quality_gate = _conditionals(
        SKILL_DIR / "templates" / "docs" / "QUALITY_GATE.md.template",
        manifest,
    )
    for rendered in (guard, quality_gate):
        assert "github-pr-create-safe" not in rendered
        assert "gh pr create --base" not in rendered


def test_agents_optional_sections_are_empty_or_rendered_as_configured() -> None:
    manifest = _manifest()
    empty = _conditionals(
        SKILL_DIR / "templates" / "AGENTS.md.template",
        manifest,
    )
    for heading in (
        "## Architecture",
        "### 主要ディレクトリ",
        "## Domain Knowledge",
        "## Working with This Codebase",
        "### ユーザーとの協働",
        "### Code Patterns",
        "### Critical Files",
    ):
        assert heading not in empty

    configured = copy.deepcopy(manifest)
    configured["project"]["agents_optional"] = {
        "architecture": "構成本文",
        "architecture_dirs": "主要ディレクトリ本文",
        "domain_knowledge": "ドメイン知識本文",
        "working_with_codebase": "作業規約本文",
        "collaboration": "協働本文",
        "code_patterns": "パターン本文",
        "critical_files": "重要ファイル本文",
    }
    rendered = genlib.render(
        (SKILL_DIR / "templates" / "AGENTS.md.template").read_text(encoding="utf-8"),
        configured,
    )
    for text in configured["project"]["agents_optional"].values():
        assert text in rendered
    assert "## Architecture" in rendered
    assert "### 主要ディレクトリ" in rendered
    assert "## Domain Knowledge" in rendered
    assert "## Working with This Codebase" in rendered
    assert "### ユーザーとの協働" in rendered
    assert "### Code Patterns" in rendered
    assert "### Critical Files" in rendered
    assert "NECPF" not in rendered


def main() -> int:
    tests = (
        test_foundation_false_removes_self_validation_references,
        test_github_pr_false_removes_wrapper_guidance,
        test_agents_optional_sections_are_empty_or_rendered_as_configured,
    )
    for test in tests:
        test()
    print("[test_template_conditionals] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
