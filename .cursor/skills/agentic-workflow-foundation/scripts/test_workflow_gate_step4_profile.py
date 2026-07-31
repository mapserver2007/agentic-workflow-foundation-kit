#!/usr/bin/env python3
"""workflow-gate.sh step4 の profile selector 回帰。

foundation profile: pnpm/quality-gate に触れず bin/foundation-gate self へ進むこと。
application profile: G-GEN semantics + bin/quality-gate verify を使うこと。
unknown profile: exit 2 fail-closed。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
TEMPLATE = (
    HERE.parent
    / "templates"
    / "skills"
    / "session-handover"
    / "scripts"
    / "workflow-gate.sh.template"
)
REAL_GATE_DIR = ROOT / ".cursor" / "skills" / "session-handover" / "scripts"
FIXTURES = HERE.parent / "fixtures" / "artifacts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_template_declares_profile_selector() -> None:
    content = _read(TEMPLATE)
    assert content, f"missing template: {TEMPLATE}"
    assert "{{project.quality_gate.profile}}" in content
    assert "foundation)" in content and "application)" in content
    assert "bin/foundation-gate" in content and " self" in content
    assert "bin/quality-gate" in content and "verify" in content
    assert "unknown project.quality_gate.profile" in content


def _stage_gate_tree(tmp: Path, profile: str) -> Path:
    gate_dir = tmp / ".cursor" / "skills" / "session-handover" / "scripts"
    gate_dir.mkdir(parents=True)
    bin_dir = tmp / "bin"
    bin_dir.mkdir(parents=True)
    for name in ("workflow-gate.sh", "gate-artifact.py"):
        src = REAL_GATE_DIR / name
        if not src.exists():
            raise FileNotFoundError(f"missing generated gate asset: {src}")
        shutil.copy2(src, gate_dir / name)
    gate = gate_dir / "workflow-gate.sh"
    text = gate.read_text(encoding="utf-8")
    text = text.replace('PROFILE="foundation"', f'PROFILE="{profile}"')
    text = text.replace('PROFILE="application"', f'PROFILE="{profile}"')
    if f'PROFILE="{profile}"' not in text:
        raise AssertionError(f"could not patch PROFILE in staged workflow-gate.sh (wanted {profile})")
    gate.write_text(text, encoding="utf-8")
    gate.chmod(0o755)
    return gate


def _write_stub_executables(tmp: Path) -> tuple[Path, Path]:
    bin_dir = tmp / "bin"
    foundation_log = tmp / "foundation-gate.log"
    quality_log = tmp / "quality-gate.log"
    (bin_dir / "foundation-gate").write_text(
        f"""#!/usr/bin/env bash
echo "$@" >> "{foundation_log}"
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "quality-gate").write_text(
        f"""#!/usr/bin/env bash
echo "$@" >> "{quality_log}"
case "${{1:-}}" in
  verify) exit 0 ;;
  gen) exit 0 ;;
  *) exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    for path in (bin_dir / "foundation-gate", bin_dir / "quality-gate"):
        path.chmod(0o755)
    return foundation_log, quality_log


def _setup_envelopes(tmp: Path, slug: str) -> Path:
    reports = tmp / "docs" / "agent-tasks" / "reports"
    reports.mkdir(parents=True)
    report = reports / f"{slug}.md"
    report.write_text("# report\n", encoding="utf-8")
    art = tmp / ".cursor" / ".artifacts"
    art.mkdir(parents=True)
    for step, fixture in (("step3", "step3-complete.md"), ("step4", "step4-complete.md")):
        src = FIXTURES / fixture
        if not src.exists():
            raise FileNotFoundError(f"missing fixture: {src}")
        shutil.copy2(src, art / f"{slug}--{step}.md")
    return report


def _run_step4(gate: Path, report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(gate), "step4", str(report)],
        capture_output=True,
        text=True,
        cwd=str(gate.parents[4]),
    )


def test_foundation_profile_uses_self_not_quality_gate() -> None:
    if not (REAL_GATE_DIR / "workflow-gate.sh").exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gate = _stage_gate_tree(tmp, "foundation")
        foundation_log, quality_log = _write_stub_executables(tmp)
        report = _setup_envelopes(tmp, "profile-foundation")
        result = _run_step4(gate, report)
        assert result.returncode == 0, (
            f"foundation step4 should exit 0 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "foundation profile" in result.stdout
        assert "pnpm" not in result.stdout.lower()
        assert foundation_log.read_text(encoding="utf-8").strip() == "self"
        assert not quality_log.exists() or quality_log.read_text(encoding="utf-8").strip() == ""


def test_application_profile_uses_quality_gate_verify() -> None:
    if not (REAL_GATE_DIR / "workflow-gate.sh").exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gate = _stage_gate_tree(tmp, "application")
        foundation_log, quality_log = _write_stub_executables(tmp)
        report = _setup_envelopes(tmp, "profile-application")
        result = _run_step4(gate, report)
        assert result.returncode == 0, (
            f"application step4 should exit 0 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "application profile" in result.stdout
        assert "--- verify ---" in result.stdout
        assert "verify" in quality_log.read_text(encoding="utf-8")
        assert not foundation_log.exists() or foundation_log.read_text(encoding="utf-8").strip() == ""


def test_application_template_always_runs_gen() -> None:
    content = _read(TEMPLATE)
    assert "gen 必須実行" in content or "常に" in content
    assert "GEN_DIRTY" not in content
    assert '"$ROOT_DIR/bin/quality-gate" gen' in content


def test_unknown_profile_exit_2() -> None:
    if not (REAL_GATE_DIR / "workflow-gate.sh").exists():
        print("  SKIP: workflow-gate.sh not found (pre-generate)", file=sys.stderr)
        return
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        gate = _stage_gate_tree(tmp, "unknown-profile")
        _write_stub_executables(tmp)
        report = _setup_envelopes(tmp, "profile-unknown")
        result = _run_step4(gate, report)
        assert result.returncode == 2, (
            f"unknown profile should exit 2 (got {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "unknown project.quality_gate.profile" in result.stderr


def main() -> int:
    tests = [
        test_template_declares_profile_selector,
        test_application_template_always_runs_gen,
        test_foundation_profile_uses_self_not_quality_gate,
        test_application_profile_uses_quality_gate_verify,
        test_unknown_profile_exit_2,
    ]
    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL: {test.__name__}: {exc}", file=sys.stderr)
            failed += 1
    print(f"[test_workflow_gate_step4_profile] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
