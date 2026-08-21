#!/usr/bin/env python3
"""manifest 由来の Mustache リテラルを再解釈しない描画回帰。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_SCRIPTS = HERE.parents[1] / "agentic-workflow-engine" / "scripts"
sys.path.insert(0, str(ENGINE_SCRIPTS))

import genlib  # noqa: E402


def main() -> int:
    instructions = "Use {{variable}} and {{#each items}}...{{/each}} literally."
    guidance = "Document {{#each}} as syntax."
    context = {
        "project": {
            "name": "foundation",
            "description": "Keep {{project.name}} literal.",
        },
        "items": [
            {"instructions": instructions, "guidance": guidance},
        ],
    }

    each_rendered = genlib.render(
        "{{#each items}}{{this.instructions}}\n{{this.guidance}}{{/each}}",
        context,
    )
    expected_each = f"{instructions}\n{guidance}"
    if each_rendered != expected_each:
        print(
            f"FAIL: each literal round-trip mismatch: {each_rendered!r}",
            file=sys.stderr,
        )
        return 1

    root_rendered = genlib.render(
        "{{project.name}}: {{project.description}}",
        context,
    )
    if root_rendered != "foundation: Keep {{project.name}} literal.":
        print(
            f"FAIL: root literal round-trip mismatch: {root_rendered!r}",
            file=sys.stderr,
        )
        return 1

    try:
        genlib.render("{{unknown.path}}", context)
    except genlib.RenderError:
        pass
    else:
        print("FAIL: template-side unresolved reference was accepted", file=sys.stderr)
        return 1

    print("[test_genlib_literal_render] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
