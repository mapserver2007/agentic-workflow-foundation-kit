#!/usr/bin/env python3
"""workflow-gate.sh step4 の ticket / report-file 解決回帰。"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FOUNDATION = HERE.parent
TEMPLATE = (
    FOUNDATION
    / "templates"
    / "skills"
    / "session-handover"
    / "scripts"
    / "workflow-gate.sh.template"
)
REAL_GATE_DIR = ROOT / ".cursor" / "skills" / "session-handover" / "scripts"
FIXTURES = HERE.parent / "fixtures" / "artifacts"
IMPL_BASE_COMMIT = "a1b2c3d4e5f6"


def _stage_gate(tmp: Path, ticket_format: str) -> Path:
    import sys

    engine_scripts = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
    if str(engine_scripts) not in sys.path:
        sys.path.insert(0, str(engine_scripts))
    from genlib import load_manifest, render

    gate_dir = tmp / ".cursor" / "skills" / "session-handover" / "scripts"
    gate_dir.mkdir(parents=True)
    for name in (
        "gate-artifact.py",
        "gate-test.py",
        "gate-domain-write-scope.py",
        "domain_doc_scope.py",
    ):
        shutil.copy2(REAL_GATE_DIR / name, gate_dir / name)

    manifest = load_manifest(str(FOUNDATION / "manifest.yaml"))
    manifest["project"]["quality_gate"]["profile"] = "foundation"
    manifest["project"]["quality_gate"]["gen_artifact_paths"] = []
    manifest["agent_workflow"]["ticket"]["format"] = ticket_format
    gate = gate_dir / "workflow-gate.sh"
    gate.write_text(
        render(TEMPLATE.read_text(encoding="utf-8"), manifest),
        encoding="utf-8",
    )
    gate.chmod(0o755)

    foundation_gate = tmp / "bin" / "foundation-gate"
    foundation_gate.parent.mkdir(parents=True)
    foundation_gate.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    foundation_gate.chmod(0o755)
    return gate


def _write_report(tmp: Path, name: str, *, in_reports: bool) -> Path:
    report = (
        tmp / "docs" / "agent-tasks" / "reports" / name
        if in_reports
        else tmp / name
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "## 10. 完了チェック\n"
        "- [x] 実装完了\n"
        "- [x] テスト完了\n"
        "- [x] コードゲート通過\n"
        f"- implementation-base-commit: {IMPL_BASE_COMMIT}\n",
        encoding="utf-8",
    )
    artifacts = tmp / ".cursor" / ".artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    for step in ("step3", "step4"):
        fixture = (FIXTURES / f"{step}-complete.md").read_text(encoding="utf-8")
        fixture = fixture.replace(IMPL_BASE_COMMIT, IMPL_BASE_COMMIT)
        (artifacts / f"{report.stem}--{step}.md").write_text(
            fixture,
            encoding="utf-8",
        )
    return report


def _run(gate: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(gate), "step4", *args, "--format=json"],
        cwd=gate.parents[4],
        capture_output=True,
        text=True,
        check=False,
    )


def test_ticket_resolution_zero_one_multiple() -> None:
    with tempfile.TemporaryDirectory(prefix="workflow-ticket-") as temp_dir:
        tmp = Path(temp_dir)
        gate = _stage_gate(tmp, r"[0-9]+")

        zero = _run(gate, "123")
        assert zero.returncode == 2
        assert "0 件" in zero.stderr

        report = _write_report(tmp, "custom-123-fixture.md", in_reports=True)
        one = _run(gate, "123")
        assert one.returncode == 0, one.stdout + one.stderr
        assert str(report.resolve()) in one.stdout

        _write_report(tmp, "another-123-fixture.md", in_reports=True)
        multiple = _run(gate, "123")
        assert multiple.returncode == 2
        assert "2 件" in multiple.stderr


def test_nonmatching_ticket_falls_back_to_report_file() -> None:
    with tempfile.TemporaryDirectory(prefix="workflow-ticket-fallback-") as temp_dir:
        tmp = Path(temp_dir)
        gate = _stage_gate(tmp, r"[0-9]+")
        report = _write_report(tmp, "OPS-130", in_reports=False)
        result = _run(gate, "OPS-130")
        assert result.returncode == 0, result.stdout + result.stderr
        assert str(report.resolve()) in result.stdout


def test_empty_ticket_format_skips_ticket_branch() -> None:
    with tempfile.TemporaryDirectory(prefix="workflow-ticket-empty-") as temp_dir:
        tmp = Path(temp_dir)
        gate = _stage_gate(tmp, "")
        report = _write_report(tmp, "123", in_reports=False)
        result = _run(gate, "123")
        assert result.returncode == 0, result.stdout + result.stderr
        assert str(report.resolve()) in result.stdout


def main() -> int:
    if not TEMPLATE.is_file() or not REAL_GATE_DIR.is_dir():
        print("SKIP: workflow-gate prerequisites not found (pre-generate)")
        return 0
    tests = (
        test_ticket_resolution_zero_one_multiple,
        test_nonmatching_ticket_falls_back_to_report_file,
        test_empty_ticket_format_skips_ticket_branch,
    )
    for test in tests:
        test()
    print("[test_workflow_gate_ticket_resolution] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
