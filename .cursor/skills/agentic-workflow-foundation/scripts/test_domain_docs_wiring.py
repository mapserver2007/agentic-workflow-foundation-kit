#!/usr/bin/env python3
"""Domain docs 防御の artifact・Step⑤・archive 配線を静的に検査する。"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import shutil
import subprocess
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
    namespace = {"__name__": "rendered_gate_artifact"}
    exec(compile(artifact, "gate-artifact.py", "exec"), namespace)
    with tempfile.TemporaryDirectory() as td:
        envelope = Path(td) / "campaign--step3.md"
        envelope.write_text(
            "---\n"
            "status: complete\n"
            "step: step3\n"
            "changed_files: []\n"
            "base_commit_sha: abcdef0\n"
            "impl_summary: fixture\n"
            "adr_needed: false\n"
            "---\n",
            encoding="utf-8",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert namespace["check_artifact"](str(envelope), json_mode=True) == 1
        check_ids = [
            check["id"]
            for check in json.loads(output.getvalue())["checks"]
        ]
        assert check_ids.count("G-ARTIFACT-STEP3-UNTRACKED-001") == 1
        assert "G-ARTIFACT-STEP-FIELD-001" not in check_ids


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


def test_document_templates_preserve_bundling_contracts():
    quality = _render("docs/QUALITY_GATE.md.template")
    completion = _render("docs/agent-tasks/agent-workflow/06-completion.md.template")
    implementation = _render("docs/agent-tasks/agent-workflow/03-implementation.md.template")
    dispatch = _render("skills/workflow-orchestrator/references/worker-dispatch.md.template")

    assert (
        "`workflow-gate.sh step5`（G-WRITE-SCOPE-DOMAIN-001 による Domain 実差分検査後、"
        "`session.verification.gate_command` 実行）"
    ) in quality
    assert "{具体的な理由}" not in completion
    for allowed_reason in ("コードから判断可能", "振る舞い非変更", "バグ修正で仕様へ復帰"):
        assert allowed_reason in completion
    assert "3.1〜3.5" in implementation
    for document in (implementation, dispatch):
        assert "git diff --name-only <base_commit_sha>" in document
        assert "git ls-files --others --exclude-standard" in document
        assert "changed_files" in document and "untracked_files" in document
        assert "working tree" in document
        assert "workflow-gate.sh step3 [report-file]" in document


def test_rendered_python_templates_parse():
    for relative in (
        "skills/session-handover/scripts/domain_doc_scope.py.template",
        "skills/session-handover/scripts/gate-domain-write-scope.py.template",
        "skills/session-handover/scripts/gate-report.py.template",
        "skills/session-handover/scripts/gate-artifact.py.template",
        "skills/session-handover/scripts/gate-maintenance-docs.py.template",
    ):
        ast.parse(_render(relative), filename=relative)


def test_ticket_format_renders_as_python_string_literal():
    manifest = load_manifest(str(SKILL / "manifest.yaml"))
    ticket_format = r'[A-Z]+-"[0-9]+"'
    manifest["agent_workflow"]["ticket"]["format"] = ticket_format
    rendered = render(
        (
            TEMPLATES
            / "skills/session-handover/scripts/gate-report.py.template"
        ).read_text(encoding="utf-8"),
        manifest,
    )
    tree = ast.parse(rendered, filename="gate-report.py.template")
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "TICKET_FORMAT"
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.Constant)
    assert assignment.value.value == ticket_format


def _run_rendered_gate_report(ticket_format, report_text, *, json_mode=True):
    manifest = load_manifest(str(SKILL / "manifest.yaml"))
    manifest["agent_workflow"]["ticket"]["format"] = ticket_format
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts = root / "scripts"
        scripts.mkdir()
        for filename in ("gate-report.py.template", "domain_doc_scope.py.template"):
            (scripts / filename.removesuffix(".template")).write_text(
                render(
                    (TEMPLATES / "skills/session-handover/scripts" / filename).read_text(
                        encoding="utf-8",
                    ),
                    manifest,
                ),
                encoding="utf-8",
            )
        report = root / "report.md"
        report.write_text(report_text, encoding="utf-8")
        args = [sys.executable, str(scripts / "gate-report.py"), str(report)]
        if json_mode:
            args.append("--format=json")
        return subprocess.run(
            args,
            cwd=root,
            env={**os.environ, "CURSOR_PROJECT_DIR": str(root)},
            capture_output=True,
            text=True,
            check=False,
        )


def test_gate_report_ticket_contract_and_matching() -> None:
    report_text = "## 1. タスクの概要\n- 関連チケット: {ticket}\n"
    for ticket in (
        "TICKET-123",
        "[TICKET-123](https://example.test/issues/123)",
        "https://github.com/owner/repo/issues/123",
        "https://github.com/owner/repo/pull/123",
    ):
        result = _run_rendered_gate_report(
            r"TICKET-[0-9]+", report_text.format(ticket=ticket),
        )
        assert result.returncode == 1
        checks = json.loads(result.stdout)["results"][0]["checks"]
        assert not any(check["id"] == "G-REPORT-TICKET-001" for check in checks)

    partial = _run_rendered_gate_report(
        r"[A-Z]{4}", report_text.format(ticket="TICKET-123"),
    )
    assert partial.returncode == 1
    checks = json.loads(partial.stdout)["results"][0]["checks"]
    assert any(check["id"] == "G-REPORT-TICKET-001" for check in checks)

    for json_mode in (False, True):
        result = _run_rendered_gate_report("", report_text.format(ticket="TICKET-123"), json_mode=json_mode)
        assert result.returncode == 2
        assert "G-REPORT-" not in result.stdout
        if json_mode:
            payload = json.loads(result.stdout)
            assert payload["fatal"] is True
        else:
            assert "FATAL:" in result.stdout


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
    tests = [
        test_step3_untracked_contract,
        test_step4_step5_archive_wiring,
        test_reason_allowlist_and_worker_contract,
        test_document_templates_preserve_bundling_contracts,
        test_rendered_python_templates_parse,
        test_ticket_format_renders_as_python_string_literal,
        test_gate_report_ticket_contract_and_matching,
        test_rendered_reason_allowlist_behavior,
    ]
    for test in tests:
        test()
    print(f"[test_domain_docs_wiring] {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
