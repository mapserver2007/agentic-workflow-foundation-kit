#!/usr/bin/env python3
"""workflow-gate の report 解決と Step③境界の回帰テスト。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parent.parent.parent
sys.path.insert(0, str(ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"))
from genlib import load_manifest, render  # noqa: E402


def _setup() -> tuple[tempfile.TemporaryDirectory, Path, Path]:
    context = tempfile.TemporaryDirectory()
    root = Path(context.name)
    scripts = root / ".cursor/skills/session-handover/scripts"
    scripts.mkdir(parents=True)
    workflow = render(
        (SKILL / "templates/skills/session-handover/scripts/workflow-gate.sh.template").read_text(encoding="utf-8"),
        load_manifest(str(SKILL / "manifest.yaml")),
    )
    target = scripts / "workflow-gate.sh"
    target.write_text(workflow, encoding="utf-8")
    target.chmod(0o755)
    assert subprocess.run(["bash", "-n", str(target)], check=False).returncode == 0
    for name, body in {
        "gate-domain-write-scope.py": "#!/usr/bin/env python3\nimport sys\nprint('domain', *sys.argv[1:])\n",
        "gate-artifact.py": "#!/usr/bin/env python3\nimport sys\nprint('artifact', *sys.argv[1:])\n",
        "verification-gate.sh": "#!/usr/bin/env bash\nprintf 'verify %s\\n' \"$*\"\n",
    }.items():
        path = scripts / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    return context, root, target


def _run(
    script: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args], text=True, capture_output=True, check=False, env=env
    )


def _runtime_domain_repo() -> tuple[tempfile.TemporaryDirectory, Path, Path, Path]:
    context = tempfile.TemporaryDirectory()
    root = Path(context.name)
    scripts = root / ".cursor/skills/session-handover/scripts"
    scripts.mkdir(parents=True)
    manifest = load_manifest(str(SKILL / "manifest.yaml"))
    assert manifest["project"]["quality_gate"]["profile"] == "application"
    assert manifest["agent_workflow"]["maintenance_docs"]["enabled"] is True
    template_dir = SKILL / "templates/skills/session-handover/scripts"
    for output, source in (
        ("domain_doc_scope.py", "domain_doc_scope.py.template"),
        ("gate-domain-write-scope.py", "gate-domain-write-scope.py.template"),
        ("gate-maintenance-docs.py", "gate-maintenance-docs.py.template"),
        ("workflow-gate.sh", "workflow-gate.sh.template"),
        ("archive-gate.sh", "archive-gate.sh.template"),
    ):
        target = scripts / output
        target.write_text(
            render((template_dir / source).read_text(encoding="utf-8"), manifest),
            encoding="utf-8",
        )
        target.chmod(0o755)

    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    (root / "docs").mkdir()
    domain = root / "docs/spec.md"
    domain.write_text("base\n", encoding="utf-8")
    _git(root, "add", "docs/spec.md")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")

    reports = root / "docs/agent-tasks/reports"
    reports.mkdir(parents=True)
    report = reports / "campaign.md"
    report.write_text(
        "\n".join((
            "## 10. 完了チェック",
            "- [x] 実装完了",
            "- [x] テスト完了",
            "- [x] コードゲート通過",
            "- [x] PRレビュー検証完了",
            "- [x] maintenance-docs/ 起票判定",
            "- [x] ADR 起票判定",
            f"- implementation-base-commit: {base}",
            "- maintenance-docs-judgment: not_required",
            "- queue_file: なし",
            "- judgment_reason: コードから判断可能",
            "",
        )),
        encoding="utf-8",
    )
    domain.write_text("changed after base\n", encoding="utf-8")
    return context, root, scripts / "workflow-gate.sh", scripts / "archive-gate.sh"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def test_explicit_and_auto_report_resolution():
    context, root, script = _setup()
    try:
        reports = root / "docs/agent-tasks/reports"
        reports.mkdir(parents=True)
        explicit = root / "outside.md"
        explicit.write_text("", encoding="utf-8")
        result = _run(script, "step5", str(explicit))
        assert result.returncode == 0 and str(explicit.resolve()) in result.stdout, result.stderr + result.stdout
        active = reports / "only.md"
        active.write_text("", encoding="utf-8")
        result = _run(script, "step5", "--format=json")
        assert result.returncode == 0 and str(active.resolve()) in (result.stdout + result.stderr)
    finally:
        context.cleanup()


def test_multiple_reports_are_fatal_and_step3_wires_envelope():
    context, root, script = _setup()
    try:
        reports = root / "docs/agent-tasks/reports"
        reports.mkdir(parents=True)
        (reports / "one.md").write_text("", encoding="utf-8")
        (reports / "two.md").write_text("", encoding="utf-8")
        result = _run(script, "step5")
        assert result.returncode == 2
        (reports / "two.md").unlink()
        artifacts = root / ".cursor/.artifacts"
        artifacts.mkdir(parents=True)
        (artifacts / "one--step3.md").write_text("---\n---\n", encoding="utf-8")
        result = _run(script, "step3")
        assert result.returncode == 0
        assert "--step3-envelope" in result.stdout
    finally:
        context.cleanup()


def test_step5_and_archive_reject_tracked_domain_changes():
    context, root, workflow, archive = _runtime_domain_repo()
    try:
        marker = root / "verification-ran"
        verification = workflow.parent / "verification-gate.sh"
        verification.write_text(
            "#!/usr/bin/env bash\ntouch \"$MARKER\"\n", encoding="utf-8"
        )
        verification.chmod(0o755)
        env = {"PATH": "/usr/bin:/bin", "MARKER": str(marker), "CURSOR_PROJECT_DIR": str(root)}
        report = root / "docs/agent-tasks/reports/campaign.md"

        step5 = _run(workflow, "step5", str(report), env=env)
        assert step5.returncode == 1
        assert "G-WRITE-SCOPE-DOMAIN-001" in step5.stdout
        assert not marker.exists()

        archived = _run(archive, str(report), env=env)
        assert archived.returncode == 1
        assert "G-WRITE-SCOPE-DOMAIN-001" in archived.stdout
        assert report.exists()
    finally:
        context.cleanup()


def main() -> int:
    tests = [
        test_explicit_and_auto_report_resolution,
        test_multiple_reports_are_fatal_and_step3_wires_envelope,
        test_step5_and_archive_reject_tracked_domain_changes,
    ]
    for test in tests:
        test()
    print(f"[test_workflow_gate_domain_scope] {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
