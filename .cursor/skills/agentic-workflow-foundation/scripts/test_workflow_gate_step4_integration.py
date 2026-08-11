#!/usr/bin/env python3
"""workflow-gate.sh step4 の完了チェック統合テスト。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
REAL_GATE_DIR = ROOT / ".cursor" / "skills" / "session-handover" / "scripts"
FIXTURES = HERE.parent / "fixtures" / "artifacts"


def _stage_gate(tmp: Path, profile: str = "foundation") -> Tuple[Path, Path]:
    gate_dir = tmp / ".cursor" / "skills" / "session-handover" / "scripts"
    gate_dir.mkdir(parents=True)
    for name in ("workflow-gate.sh", "gate-artifact.py", "gate-test.py"):
        shutil.copy2(REAL_GATE_DIR / name, gate_dir / name)

    gate = gate_dir / "workflow-gate.sh"
    text = gate.read_text(encoding="utf-8")
    text = text.replace('PROFILE="foundation"', f'PROFILE="{profile}"')
    text = text.replace('PROFILE="application"', f'PROFILE="{profile}"')
    gate.write_text(text, encoding="utf-8")
    gate.chmod(0o755)

    real_gate_test = gate_dir / "gate-test-real.py"
    shutil.copy2(gate_dir / "gate-test.py", real_gate_test)
    gate_test_log = tmp / "gate-test.log"
    gate_test = gate_dir / "gate-test.py"
    gate_test.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess\n"
        "import sys\n"
        "from pathlib import Path\n"
        f'Path({str(gate_test_log)!r}).open("a", encoding="utf-8").write("invoked\\n")\n'
        'raise SystemExit(subprocess.call([sys.executable, str(Path(__file__).with_name("gate-test-real.py")), *sys.argv[1:]]))\n',
        encoding="utf-8",
    )
    gate_test.chmod(0o755)
    return gate, gate_test_log


def _write_stubs(tmp: Path) -> Tuple[Path, Path]:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    foundation_log = tmp / "foundation-gate.log"
    quality_log = tmp / "quality-gate.log"
    (bin_dir / "foundation-gate").write_text(
        f"""#!/usr/bin/env bash
echo "$@" >> "{foundation_log}"
exit "${{STUB_FOUNDATION_EXIT:-0}}"
""",
        encoding="utf-8",
    )
    (bin_dir / "quality-gate").write_text(
        f"""#!/usr/bin/env bash
echo "$@" >> "{quality_log}"
case "${{1:-}}" in
  verify) exit "${{STUB_VERIFY_EXIT:-0}}" ;;
  gen) exit "${{STUB_GEN_EXIT:-0}}" ;;
  *) exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    for path in (bin_dir / "foundation-gate", bin_dir / "quality-gate"):
        path.chmod(0o755)
    return foundation_log, quality_log


def _setup_report(
    tmp: Path,
    slug: str,
    completion: str = (
        "- [x] 実装完了\n"
        "- [x] テスト完了\n"
        "- [x] コードゲート通過\n"
    ),
) -> Path:
    reports = tmp / "docs" / "agent-tasks" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    report = reports / f"{slug}.md"
    report.write_text(f"## 10. 完了チェック\n{completion}", encoding="utf-8")

    artifacts = tmp / ".cursor" / ".artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    for step in ("step3", "step4"):
        shutil.copy2(FIXTURES / f"{step}-complete.md", artifacts / f"{slug}--{step}.md")
    return report


def _run(
    gate: Path,
    args: Tuple[str, ...],
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    process_env = dict(os.environ)
    if env:
        process_env.update(env)
    return subprocess.run(
        ["bash", str(gate), "step4", *args],
        capture_output=True,
        text=True,
        cwd=str(gate.parents[4]),
        env=process_env,
    )


def test_foundation_success_runs_gate_test_once() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gate, gate_test_log = _stage_gate(tmp)
        foundation_log, quality_log = _write_stubs(tmp)
        report = _setup_report(tmp, "foundation-success")
        result = _run(gate, (str(report),))
        assert result.returncode == 0, result.stdout + result.stderr
        assert foundation_log.read_text(encoding="utf-8").splitlines() == ["self"]
        assert not quality_log.exists()
        assert gate_test_log.read_text(encoding="utf-8").splitlines() == ["invoked"]


def test_application_success_runs_gate_test_once() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gate, gate_test_log = _stage_gate(tmp, "application")
        foundation_log, quality_log = _write_stubs(tmp)
        report = _setup_report(tmp, "application-success")
        result = _run(gate, (str(report),))
        assert result.returncode == 0, result.stdout + result.stderr
        assert quality_log.read_text(encoding="utf-8").splitlines() == ["verify"]
        assert not foundation_log.exists()
        assert gate_test_log.read_text(encoding="utf-8").splitlines() == ["invoked"]


def test_envelope_failure_skips_code_and_completion_gates() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gate, gate_test_log = _stage_gate(tmp)
        foundation_log, quality_log = _write_stubs(tmp)
        report = _setup_report(tmp, "missing-step3")
        (tmp / ".cursor" / ".artifacts" / "missing-step3--step3.md").unlink()
        result = _run(gate, (str(report),))
        assert result.returncode == 1
        assert not foundation_log.exists()
        assert not quality_log.exists()
        assert not gate_test_log.exists()


def test_code_gate_failure_propagates_and_skips_completion_gate() -> None:
    for exit_code in ("1", "2"):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            gate, gate_test_log = _stage_gate(tmp, "application")
            _write_stubs(tmp)
            report = _setup_report(tmp, f"code-failure-{exit_code}")
            result = _run(
                gate,
                (str(report),),
                {"STUB_VERIFY_EXIT": exit_code},
            )
            assert result.returncode == int(exit_code)
            assert not gate_test_log.exists()


def test_completion_failure_propagates() -> None:
    for completion, expected in (("- [ ] 実装完了\n", 1), ("- [x] 実装完了\n", 1)):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            gate, gate_test_log = _stage_gate(tmp)
            _write_stubs(tmp)
            report = _setup_report(tmp, "completion-failure", completion)
            result = _run(gate, (str(report),))
            assert result.returncode == expected, result.stdout + result.stderr
            assert gate_test_log.read_text(encoding="utf-8").splitlines() == ["invoked"]


def test_unknown_profile_is_fatal_without_completion_gate() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gate, gate_test_log = _stage_gate(tmp, "unknown-profile")
        _write_stubs(tmp)
        report = _setup_report(tmp, "unknown-profile")
        result = _run(gate, (str(report),))
        assert result.returncode == 2
        assert not gate_test_log.exists()
        assert "unknown project.quality_gate.profile" in result.stderr


def test_explicit_and_single_auto_report_resolution() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gate, _ = _stage_gate(tmp)
        _write_stubs(tmp)
        report = _setup_report(tmp, "resolution")
        explicit = _run(gate, (str(report),))
        assert explicit.returncode == 0

        (tmp / "bin" / "foundation-gate").write_text(
            (tmp / "bin" / "foundation-gate").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        auto = _run(gate, tuple())
        assert auto.returncode == 0, auto.stdout + auto.stderr


def test_multiple_auto_reports_are_fatal() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gate, _ = _stage_gate(tmp)
        _write_stubs(tmp)
        _setup_report(tmp, "report-a")
        _setup_report(tmp, "report-b")
        result = _run(gate, tuple())
        assert result.returncode == 2


def test_json_mode_keeps_gate_result_on_stdout() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gate, _ = _stage_gate(tmp)
        _write_stubs(tmp)
        report = _setup_report(tmp, "json-result")
        result = _run(gate, (str(report), "--format=json"))
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["gate"] == "gate-test"
        assert payload["report_path"] == str(report.resolve())
        assert payload["exit_code"] == 0
        assert "workflow gate" in result.stderr


def main() -> int:
    if not (REAL_GATE_DIR / "workflow-gate.sh").exists():
        print("SKIP: generated workflow-gate.sh not found (pre-generate)")
        return 0

    tests = [
        test_foundation_success_runs_gate_test_once,
        test_application_success_runs_gate_test_once,
        test_envelope_failure_skips_code_and_completion_gates,
        test_code_gate_failure_propagates_and_skips_completion_gate,
        test_completion_failure_propagates,
        test_unknown_profile_is_fatal_without_completion_gate,
        test_explicit_and_single_auto_report_resolution,
        test_multiple_auto_reports_are_fatal,
        test_json_mode_keeps_gate_result_on_stdout,
    ]
    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL: {test.__name__}: {exc}", file=os.sys.stderr)
            failed += 1
    print(f"[test_workflow_gate_step4_integration] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
