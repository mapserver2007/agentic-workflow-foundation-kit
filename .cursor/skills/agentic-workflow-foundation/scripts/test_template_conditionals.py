#!/usr/bin/env python3
"""foundation / github_pr / AGENTS 任意ブロックの生成条件回帰。"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import tempfile
import time
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

    partial_cases = (
        ("architecture_dirs", "主要ディレクトリ本文", "## Architecture", "### 主要ディレクトリ"),
        ("collaboration", "協働本文", "## Working with This Codebase", "### ユーザーとの協働"),
        ("code_patterns", "パターン本文", "## Working with This Codebase", "### Code Patterns"),
        ("critical_files", "重要ファイル本文", "## Working with This Codebase", "### Critical Files"),
    )
    for field, text, parent_heading, child_heading in partial_cases:
        partial = copy.deepcopy(manifest)
        partial["project"]["agents_optional"] = {
            key: "" for key in configured["project"]["agents_optional"]
        }
        partial["project"]["agents_optional"][field] = text
        partial_rendered = genlib.render(
            (SKILL_DIR / "templates" / "AGENTS.md.template").read_text(encoding="utf-8"),
            partial,
        )
        assert text in partial_rendered, field
        assert partial_rendered.count(parent_heading) == 1, field
        assert partial_rendered.count(child_heading) == 1, field


def _render(template: Path, manifest: dict) -> str:
    return genlib.render(template.read_text(encoding="utf-8"), manifest)


def _completion_items(manifest: dict) -> list[str]:
    return [
        "実装完了",
        "テスト完了",
        "コードゲート通過",
        "PRレビュー検証完了",
        (
            "maintenance-docs/ 起票判定"
            if manifest["agent_workflow"]["maintenance_docs"]["enabled"]
            else "docs への仕様反映"
        ),
        "ADR 起票判定",
    ]


def _report(manifest: dict, completed: int = 6, *, outside: bool = False, duplicate: bool = False) -> str:
    lines = [f"- [x] {item}" for item in _completion_items(manifest)[:completed]]
    if outside:
        return "\n".join(lines + ["", "## 10. 完了チェック", ""]) + "\n"
    body = "\n".join(["## 10. 完了チェック", *lines, ""])
    return body + ("\n## 完了チェック\n" if duplicate else "")


def _run_session_start(
    manifest: dict,
    reports: dict[str, str] | None = None,
    *,
    archive_exit: int = 0,
    ages: dict[str, int] | None = None,
    tracker_age: int | None = None,
) -> subprocess.CompletedProcess[str]:
    script_text = _render(
        SKILL_DIR / "templates" / "skills" / "session-handover" / "scripts" / "session-start-gate.sh.template",
        manifest,
    )
    with tempfile.TemporaryDirectory(prefix="session-start-template-") as td:
        tmp = Path(td)
        project = tmp / "project"
        scripts = tmp / "scripts"
        cwd = tmp / "different-cwd"
        project.mkdir()
        scripts.mkdir()
        cwd.mkdir()
        script = scripts / "session-start-gate.sh"
        script.write_text(script_text, encoding="utf-8")
        script.chmod(0o700)
        record = tmp / "archive-argument.txt"
        stub_name = (
            "workflow-gate.sh"
            if manifest["agent_workflow"]["gate_scripts"]
            else "archive-gate.sh"
        )
        (scripts / stub_name).write_text(
            "#!/usr/bin/env bash\n"
            "set -u\n"
            "if [[ $# -gt 0 && \"$1\" == \"archive\" ]]; then shift; fi\n"
            "printf '%s' \"${1:-}\" > \"$ARCHIVE_RECORD\"\n"
            "exit \"$ARCHIVE_EXIT\"\n",
            encoding="utf-8",
        )
        (scripts / stub_name).chmod(0o700)

        if reports is not None:
            reports_dir = project / "docs" / "agent-tasks" / "reports"
            reports_dir.mkdir(parents=True)
            for name, content in reports.items():
                report = reports_dir / name
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text(content, encoding="utf-8")
                if ages and name in ages:
                    old = time.time() - ages[name] * 3600
                    os.utime(report, (old, old))
        if tracker_age is not None:
            tracker = project / ".cursor" / ".tracking" / "tracker-campaign.md"
            tracker.parent.mkdir(parents=True)
            tracker.write_text("# tracker\n", encoding="utf-8")
            old = time.time() - tracker_age * 3600
            os.utime(tracker, (old, old))

        env = dict(os.environ)
        env.update(
            {
                "CURSOR_PROJECT_DIR": str(project),
                "ARCHIVE_EXIT": str(archive_exit),
                "ARCHIVE_RECORD": str(record),
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(script)],
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        result.archive_argument = record.read_text(encoding="utf-8") if record.exists() else ""  # type: ignore[attr-defined]
        return result


def test_session_start_report_conditionals_and_runtime_contract() -> None:
    manifest = _manifest()
    enabled = copy.deepcopy(manifest)
    disabled = copy.deepcopy(manifest)
    disabled["agent_workflow"]["enabled"] = False

    start_template = SKILL_DIR / "templates" / "skills" / "session-handover" / "scripts" / "session-start-gate.sh.template"
    quality_template = SKILL_DIR / "templates" / "docs" / "QUALITY_GATE.md.template"
    agents_template = SKILL_DIR / "templates" / "AGENTS.md.template"
    index_template = SKILL_DIR / "templates" / "docs" / "agent-tasks" / "agent-workflow.md.template"
    archive_template = SKILL_DIR / "templates" / "skills" / "session-handover" / "scripts" / "archive-gate.sh.template"
    report_template = SKILL_DIR / "templates" / "docs" / "agent-tasks" / "agent-workflow" / "02-report-creation.md.template"

    enabled_start = _render(start_template, enabled)
    disabled_start = _render(start_template, disabled)
    assert "G-SESSION-STALE-001" in enabled_start and "G-SESSION-STALE-001" in disabled_start
    for code in ("G-SESSION-ARCH-001", "G-SESSION-ARCH-002", "G-SESSION-REPORT-001"):
        assert code in enabled_start
        assert code not in disabled_start
    assert "git log -1" not in enabled_start
    assert 'find "$REPORTS_DIR" -maxdepth 1 -type f -name \'*.md\' ! -name \'*-review.md\'' in enabled_start
    assert '"$SCRIPT_DIR/workflow-gate.sh" archive "$report"' in enabled_start

    for maintenance_enabled in (True, False):
        for gate_scripts in (True, False):
            variant = copy.deepcopy(enabled)
            variant["agent_workflow"]["maintenance_docs"]["enabled"] = maintenance_enabled
            variant["agent_workflow"]["gate_scripts"] = gate_scripts
            rendered_start = _render(start_template, variant)
            rendered_archive = _render(archive_template, variant)
            rendered_report = _render(report_template, variant)
            for item in _completion_items(variant):
                assert item in rendered_start
                assert item in rendered_archive
                assert item in rendered_report
            command = "workflow-gate.sh" if gate_scripts else "archive-gate.sh"
            assert command in rendered_start

    enabled_quality = _render(quality_template, enabled)
    disabled_quality = _render(quality_template, disabled)
    enabled_agents = _render(agents_template, enabled)
    disabled_agents = _render(agents_template, disabled)
    enabled_index = _render(index_template, enabled)
    assert "G-SESSION-ARCH-001" in enabled_quality
    assert "G-SESSION-ARCH-001" not in disabled_quality
    assert "archive 可能な reports" in enabled_agents
    assert "archive 可能な reports" not in disabled_agents
    assert "archive 可能な reports" in enabled_index

    missing = _run_session_start(enabled, None)
    assert missing.returncode == 2 and "reports ディレクトリ" in missing.stdout
    empty = _run_session_start(enabled, {})
    assert empty.returncode == 0 and "G-SESSION-ARCH-001" in empty.stdout
    disabled_runtime = _run_session_start(disabled, None)
    assert disabled_runtime.returncode == 0
    assert "G-SESSION-ARCH-" not in disabled_runtime.stdout

    complete = _report(enabled)
    arch_fail = _run_session_start(enabled, {"TICKET-1-complete.md": complete})
    assert arch_fail.returncode == 1
    assert "G-SESSION-ARCH-001" in arch_fail.stdout
    assert "git mv" in arch_fail.stdout
    assert arch_fail.archive_argument.endswith("TICKET-1-complete.md")  # type: ignore[attr-defined]

    five_of_six = _run_session_start(enabled, {"TICKET-1-incomplete.md": _report(enabled, 5)})
    assert five_of_six.returncode == 0 and "G-SESSION-ARCH-" not in five_of_six.stdout
    outside = _run_session_start(enabled, {"TICKET-1-outside.md": _report(enabled, outside=True)})
    assert outside.returncode == 0 and "G-SESSION-ARCH-" not in outside.stdout
    wrong_number = "\n".join(
        ["## 9. 完了チェック", *[f"- [x] {item}" for item in _completion_items(enabled)], ""]
    )
    wrong_number_result = _run_session_start(
        enabled, {"TICKET-1-wrong-number.md": wrong_number}
    )
    assert wrong_number_result.returncode == 0
    assert "G-SESSION-ARCH-" not in wrong_number_result.stdout
    uppercase = _run_session_start(
        enabled,
        {"TICKET-1-uppercase.md": complete.replace("- [x]", "- [X]")},
    )
    assert uppercase.returncode == 0 and "G-SESSION-ARCH-" not in uppercase.stdout
    excluded = _run_session_start(
        enabled,
        {
            "TICKET-1-review.md": complete,
            "archives/TICKET-1-archived.md": complete,
        },
    )
    assert excluded.returncode == 0
    assert excluded.archive_argument == ""  # type: ignore[attr-defined]
    assert "[FAIL]" not in excluded.stdout and "[WARN]" not in excluded.stdout
    duplicate = _run_session_start(enabled, {"TICKET-1-duplicate.md": _report(enabled, duplicate=True)})
    assert duplicate.returncode == 2 and "複数" in duplicate.stdout

    arch_warn = _run_session_start(enabled, {"TICKET-1-warn.md": complete}, archive_exit=1)
    assert arch_warn.returncode == 0 and "G-SESSION-ARCH-002" in arch_warn.stdout
    arch_fatal = _run_session_start(enabled, {"TICKET-1-fatal.md": complete}, archive_exit=2)
    assert arch_fatal.returncode == 2 and "G-SESSION-ARCH-002" in arch_fatal.stdout

    stale_report = _run_session_start(
        enabled,
        {"TICKET-1-stale.md": _report(enabled, 0)},
        ages={"TICKET-1-stale.md": 24},
    )
    assert stale_report.returncode == 0 and "G-SESSION-REPORT-001" in stale_report.stdout
    fresh_report = _run_session_start(
        enabled,
        {"TICKET-1-fresh.md": _report(enabled, 0)},
        ages={"TICKET-1-fresh.md": 23},
    )
    assert fresh_report.returncode == 0 and "G-SESSION-REPORT-001" not in fresh_report.stdout
    stale_tracker = _run_session_start(enabled, {}, tracker_age=24)
    assert stale_tracker.returncode == 0 and "G-SESSION-STALE-001" in stale_tracker.stdout

    direct_archive = copy.deepcopy(enabled)
    direct_archive["agent_workflow"]["gate_scripts"] = False
    direct_result = _run_session_start(direct_archive, {"TICKET-1-direct.md": _report(direct_archive)})
    assert direct_result.returncode == 1
    assert direct_result.archive_argument.endswith("TICKET-1-direct.md")  # type: ignore[attr-defined]


def main() -> int:
    tests = (
        test_foundation_false_removes_self_validation_references,
        test_github_pr_false_removes_wrapper_guidance,
        test_agents_optional_sections_are_empty_or_rendered_as_configured,
        test_session_start_report_conditionals_and_runtime_contract,
    )
    for test in tests:
        test()
    print("[test_template_conditionals] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
