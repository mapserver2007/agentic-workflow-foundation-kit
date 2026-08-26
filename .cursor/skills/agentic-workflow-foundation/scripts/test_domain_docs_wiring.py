#!/usr/bin/env python3
"""Domain docs 防御の artifact・Step⑤・archive 配線を静的に検査する。"""
from __future__ import annotations

import ast
import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parent.parent.parent
TEMPLATES = SKILL / "templates"
sys.path.insert(0, str(ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"))
from genlib import load_manifest, render  # noqa: E402


def _render(relative: str) -> str:
    return render(
        (TEMPLATES / relative).read_text(encoding="utf-8"),
        load_manifest(str(SKILL / "manifest.yaml")),
    )


def test_step3_untracked_contract():
    artifact = _render("skills/session-handover/scripts/gate-artifact.py.template")
    assert '"untracked_files"' in artifact
    assert "G-ARTIFACT-STEP3-UNTRACKED-001" in artifact


def test_step4_step5_archive_wiring():
    workflow = _render("skills/session-handover/scripts/workflow-gate.sh.template")
    archive = _render("skills/session-handover/scripts/archive-gate.sh.template")
    assert workflow.count("gate-domain-write-scope.py") >= 3
    assert "step3" in workflow and "--step3-envelope" in workflow
    assert "G-WRITE-SCOPE-BASE-001" in _render("skills/session-handover/scripts/gate-domain-write-scope.py.template")
    assert "step5" in workflow and "resolve_active_report" in workflow
    assert "G-WRITE-SCOPE-DOMAIN-001" in archive


def test_reason_allowlist_and_worker_contract():
    reason = _render("skills/session-handover/scripts/gate-maintenance-docs.py.template")
    dispatch = (TEMPLATES / "skills/workflow-orchestrator/references/worker-dispatch.md.template").read_text(encoding="utf-8")
    assert "G-MDOCS-REASON-002" in reason
    assert "REJECT_REASON_PATTERNS" in reason and "ALLOW_REASON_PATTERNS" in reason
    assert "implementation-base-commit" in dispatch


def test_rendered_python_templates_parse():
    for relative in (
        "skills/session-handover/scripts/domain_doc_scope.py.template",
        "skills/session-handover/scripts/gate-domain-write-scope.py.template",
        "skills/session-handover/scripts/gate-report.py.template",
        "skills/session-handover/scripts/gate-artifact.py.template",
        "skills/session-handover/scripts/gate-maintenance-docs.py.template",
    ):
        ast.parse(_render(relative), filename=relative)


def test_rendered_reason_allowlist_behavior():
    namespace = {"__name__": "rendered_gate_maintenance_docs"}
    exec(compile(_render("skills/session-handover/scripts/gate-maintenance-docs.py.template"), "gate.py", "exec"), namespace)
    check_report = namespace["check_report"]
    fixtures = SKILL / "fixtures/reports-mdocs"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        reports = root / "docs/agent-tasks/reports"
        reports.mkdir(parents=True)
        for name, expected in (("report-not-required-valid.md", 0), ("report-not-required-reflected.md", 1)):
            report = reports / name
            shutil.copy2(fixtures / name, report)
            with contextlib.redirect_stdout(io.StringIO()):
                assert check_report(report, root) == expected


def main() -> int:
    tests = [test_step3_untracked_contract, test_step4_step5_archive_wiring, test_reason_allowlist_and_worker_contract, test_rendered_python_templates_parse, test_rendered_reason_allowlist_behavior]
    for test in tests:
        test()
    print(f"[test_domain_docs_wiring] {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
