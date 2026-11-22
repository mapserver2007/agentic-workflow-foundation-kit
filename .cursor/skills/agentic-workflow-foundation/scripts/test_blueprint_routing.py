#!/usr/bin/env python3
"""技術ブループリントを実装経路へ接続する契約（Step ①②③、AGENTS.md、domain-docs）を検査する。

テンプレートと生成物の両方で、契約マーカーの存在・順序・範囲を確認する。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TEMPLATES = HERE.parent / "templates"
sys.path.insert(0, str(HERE))
import _contract_markers as cm  # noqa: E402


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _both(template_rel: str, generated_rel: str):
    """(ラベル, テキスト) を、テンプレートと生成物の順に返す。"""
    return (
        ("template", _read(TEMPLATES / template_rel)),
        ("generated", _read(ROOT / generated_rel)),
    )


def _between(text: str, start_id: str, end_token: str) -> str:
    start = cm.require(text, start_id).end
    end = text.index(end_token, start)
    return text[start:end]


def test_agents_tech_stack_routes_to_index() -> None:
    for label, text in _both("AGENTS.md.template", "AGENTS.md"):
        cm.require(text, "agents-tech-stack-index-route", label=label)
        cm.require_tokens_on_line(
            text,
            "agents-tech-stack-index-route",
            ("docs/tech-stack.md", "docs/tech-stack/", "タスク別の必読節", "生成物"),
        )


def test_implementation_placement_order() -> None:
    for label, text in _both(
        "docs/agent-tasks/agent-workflow/03-implementation.md.template",
        "docs/agent-tasks/agent-workflow/03-implementation.md",
    ):
        cm.require(text, "impl-placement-order", label=label)
        body = _between(text, "impl-placement-order", "- **アーキテクチャの原則**")
        positions = [body.find(token) for token in ("同種の既存実装", "タスク別の必読節", "技術ブループリントの適用")]
        assert all(p >= 0 for p in positions), f"{label}: 配置と命名の3段階が揃っていない: {positions}"
        assert positions == sorted(positions), f"{label}: 配置と命名の順序（既存実装、ブループリント、束縛節）が崩れている"
        assert "別タスク" in body, f"{label}: 既存の外れの是正を別タスクにする旨がない"
        assert "→ `docs/tech-stack.md`" not in text, f"{label}: 生成物への起票を促す旧記述が残っている"


def test_report_placement_basis() -> None:
    for label, text in _both(
        "docs/agent-tasks/agent-workflow/02-report-creation.md.template",
        "docs/agent-tasks/agent-workflow/02-report-creation.md",
    ):
        cm.require(text, "report-placement-basis", label=label)
        start = cm.require(text, "report-placement-basis").end
        section = text[start:start + 1500]
        for token in ("既存踏襲", "ブループリント", "既存ファイルの修正", "助言（Advisory）", "先頭列", "末尾列"):
            assert token in section, f"{label}: 配置根拠の記述に {token!r} がない"
        assert "| 変更対象ファイル | 配置根拠 | 変更箇所 | 変更内容 |" in text, f"{label}: 表のヘッダに配置根拠の列（2列目）がない"


def test_gate_b_binding_section() -> None:
    for label, text in _both(
        "skills/requirement-analysis/references/requirement-contract.md.template",
        ".cursor/skills/requirement-analysis/references/requirement-contract.md",
    ):
        cm.require_order(
            text,
            ("gate-b-binding-section", "gate-b-binding-incomplete-for-placement", "gate-b-binding-warning-otherwise"),
            label=label,
        )
        cm.require_tokens_on_line(
            text,
            "gate-b-binding-incomplete-for-placement",
            ("INCOMPLETE", "新規ファイル", "blocking: true", "gate: B"),
            forbidden=("non-blocking",),
        )
        cm.require_tokens_on_line(
            text,
            "gate-b-binding-warning-otherwise",
            ("INCOMPLETE", "にしない", "non-blocking warning"),
        )
        heading = _between(text, "gate-b-binding-section", "判定は、タスクが配置の判断を要するか")
        for token in ("未記入", "プレースホルダ", "記入欄"):
            assert token in heading, f"{label}: 束縛節の検査対象に {token!r} がない"


def test_domain_docs_generation_scope_contract() -> None:
    for label, text in _both(
        "skills/domain-docs/SKILL.md.template", ".cursor/skills/domain-docs/SKILL.md"
    ):
        assert "\n## 生成範囲\n" in text, f"{label}: 生成範囲の節がない"
        assert "PO には聞かない" in text, f"{label}: 範囲を PO に聞かない旨がない"
        assert "--scope-heading" not in text, f"{label}: PO による範囲の選択が復活している"
        section = text[text.index("\n## 生成範囲\n") + 1:]
        section = section[: section.index("\n## ", 5)]
        for token in ("対象範囲", "evidence", "リポジトリの担当範囲", "docs/tech-stack.md", "複製"):
            assert token in section, f"{label}: 生成範囲の節に {token!r} がない"


def main() -> int:
    tests = [
        test_agents_tech_stack_routes_to_index,
        test_implementation_placement_order,
        test_report_placement_basis,
        test_gate_b_binding_section,
        test_domain_docs_generation_scope_contract,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            print(f"[test_blueprint_routing] FAIL: {test.__name__}: {exc}", file=sys.stderr)
            failed += 1
        else:
            print(f"[test_blueprint_routing] PASS: {test.__name__}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
