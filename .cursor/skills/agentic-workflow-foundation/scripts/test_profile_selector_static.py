#!/usr/bin/env python3
"""profile selector 以外の hard-coded 検証コマンドが active template に残っていないことを検査。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"

ACTIVE_CMD_PATTERNS = (
    re.compile(r'bin/quality-gate verify(?!\s*\}\})'),
    re.compile(r'bin/foundation-gate self(?!\s*\}\})'),
)

ALLOWLIST_FILES = frozenset({
    "workflow-gate.sh.template",
    "bin/quality-gate.template",
    "bin/foundation-gate.template",
    "docs/QUALITY_GATE.md.template",
    "AGENTS.md.template",
    "CLAUDE.md.template",
    "docs/AGENT_RUNBOOK.md.template",
    "hooks/README.md.template",
    "skills/session-handover/scripts/workflow-gate.sh.template",
    "skills/session-handover/scripts/verification-gate.sh.template",
})

LINE_ALLOWLIST = (
    "{{session.verification.gate_command}}",
    "gate_command",
    "# ",
    "→ backend:",
    "削除されました",
    "ERROR:",
    'echo "FAIL:',
    "workflow-gate.sh",
    "plan-gate.sh",
)


def _line_allowed(line: str) -> bool:
    if any(token in line for token in LINE_ALLOWLIST):
        return True
    if line.strip().startswith(">"):
        return True
    return False


def main() -> int:
    failures: list[str] = []
    for path in sorted(TEMPLATES.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(TEMPLATES))
        if rel in ALLOWLIST_FILES or any(rel.endswith(a) for a in ALLOWLIST_FILES):
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            if _line_allowed(line):
                continue
            for pattern in ACTIVE_CMD_PATTERNS:
                if pattern.search(line):
                    failures.append(f"{rel}:{line_no}: {line.strip()}")
                    break
    if failures:
        for item in failures:
            print(f"FAIL: hard-coded profile command in {item}", file=sys.stderr)
        return 1
    print("[test_profile_selector_static] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
