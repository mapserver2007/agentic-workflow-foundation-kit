#!/usr/bin/env python3
"""consumer audit の seed required_sections 例外を検査する。"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ENGINE_SCRIPTS = HERE.parents[1] / "agentic-workflow-engine" / "scripts"
if str(ENGINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ENGINE_SCRIPTS))

import audit  # noqa: E402


def _load_runner():
    path = HERE / "run_resolved_engine.py"
    spec = importlib.util.spec_from_file_location("test_seed_audit_scope_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"runner を読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()


MANIFEST = """\
marker_id: test-audit
outputs:
  - path: seed.md
    template: seed.template
    mode: seed
    required_sections:
      - KIT-SEED-SECTION
  - path: rendered.md
    template: rendered.template
    mode: render
    required_sections:
      - RENDER-SECTION
  - path: managed.txt
    template: managed.template
    mode: marker
    required_sections:
      - MARKER-SECTION
"""


def _write_skill(root: Path) -> Path:
    skill_dir = root / ".cursor" / "skills" / "test-skill"
    (skill_dir / "templates").mkdir(parents=True)
    (skill_dir / "manifest.yaml").write_text(MANIFEST, encoding="utf-8")
    (skill_dir / "templates" / "seed.template").write_text(
        "KIT-SEED-SECTION\n",
        encoding="utf-8",
    )
    (skill_dir / "templates" / "rendered.template").write_text(
        "RENDER-SECTION\n",
        encoding="utf-8",
    )
    (skill_dir / "templates" / "managed.template").write_text(
        "MARKER-SECTION\n",
        encoding="utf-8",
    )
    (root / "seed.md").write_text("consumer-owned seed\n", encoding="utf-8")
    (root / "rendered.md").write_text("RENDER-SECTION\n", encoding="utf-8")
    (root / "managed.txt").write_text(
        "project-owned\n"
        "# >>> test-audit managed >>>\n"
        "MARKER-SECTION\n"
        "# <<< test-audit managed <<<\n",
        encoding="utf-8",
    )
    return skill_dir


def test_default_audit_requires_seed_sections() -> None:
    with tempfile.TemporaryDirectory(prefix="seed-audit-default-") as temp_dir:
        skill_dir = _write_skill(Path(temp_dir) / "repo")
        assert audit.main(["--skill-dir", str(skill_dir)]) == 1
        assert (
            audit.main(
                [
                    "--skill-dir",
                    str(skill_dir),
                    "--skip-seed-required-sections",
                ]
            )
            == 0
        )


def test_seed_exception_keeps_other_checks_and_exit_codes() -> None:
    with tempfile.TemporaryDirectory(prefix="seed-audit-scope-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _write_skill(root)

        (root / "rendered.md").write_text("wrong\n", encoding="utf-8")
        assert audit.run(str(skill_dir), skip_seed_required_sections=True) == 1

        (root / "rendered.md").write_text("RENDER-SECTION\n", encoding="utf-8")
        (root / "managed.txt").write_text("project-owned\n", encoding="utf-8")
        assert audit.run(str(skill_dir), skip_seed_required_sections=True) == 1

        (root / "managed.txt").write_text(
            "project-owned\n"
            "# >>> test-audit managed >>>\n"
            "MARKER-SECTION\n"
            "# <<< test-audit managed <<<\n",
            encoding="utf-8",
        )
        (root / "seed.md").unlink()
        assert audit.run(str(skill_dir), skip_seed_required_sections=True) == 1


def test_seed_exception_keeps_fatal_errors() -> None:
    with tempfile.TemporaryDirectory(prefix="seed-audit-fatal-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _write_skill(root)

        manifest = (skill_dir / "manifest.yaml").read_text(encoding="utf-8")
        (skill_dir / "manifest.yaml").write_text(
            manifest.replace("mode: marker", "mode: unknown"),
            encoding="utf-8",
        )
        assert audit.run(str(skill_dir), skip_seed_required_sections=True) == 2

        (skill_dir / "manifest.yaml").write_text(MANIFEST, encoding="utf-8")
        (skill_dir / "templates" / "seed.template").unlink()
        assert audit.run(str(skill_dir), skip_seed_required_sections=True) == 2

        (skill_dir / "templates" / "seed.template").write_text(
            "KIT-SEED-SECTION\n",
            encoding="utf-8",
        )
        (skill_dir / "manifest.yaml").write_text("outputs: [\n", encoding="utf-8")
        assert audit.run(str(skill_dir), skip_seed_required_sections=True) == 2


def test_foundation_gate_keeps_default_audit() -> None:
    gate_template = (
        HERE.parent / "templates" / "bin" / "foundation-gate.template"
    ).read_text(encoding="utf-8")
    assert "--skip-seed-required-sections" not in gate_template


def test_resolved_runner_routes_flag_only_to_audit() -> None:
    with tempfile.TemporaryDirectory(prefix="seed-audit-runner-") as temp_dir:
        work_root = Path(temp_dir) / "work"
        (work_root / ".cursor" / "skills").mkdir(parents=True)
        calls: list[list[str]] = []

        def record_call(command: list[str], cwd: str) -> int:
            calls.append(command)
            return 0

        with (
            patch.object(RUNNER, "resolved_manifest", return_value={}),
            patch.object(RUNNER, "prepare_skill_dir", return_value=str(work_root)),
            patch.object(RUNNER, "_run_deep_thinking_validator", return_value=0),
            patch.object(RUNNER, "_run_requirement_analysis_validator", return_value=0),
            patch.object(RUNNER, "_run_agent_kaizen_validator", return_value=0),
            patch.object(RUNNER, "_run_worker_contract_validator", return_value=0),
            patch.object(RUNNER.subprocess, "call", side_effect=record_call),
        ):
            assert (
                RUNNER.main(
                    [
                        "audit",
                        "--work-root",
                        str(work_root),
                        "--skip-seed-required-sections",
                    ]
                )
                == 0
            )

        assert "--skip-seed-required-sections" in calls[0]
        assert "audit.py" in calls[0][1]

        calls.clear()
        with patch.object(RUNNER.subprocess, "call", side_effect=record_call):
            assert RUNNER.run_engine("generate", "/tmp/resolved") == 0
            assert RUNNER.run_engine("check", "/tmp/resolved") == 0
        assert all("--skip-seed-required-sections" not in command for command in calls)

        assert (
            RUNNER.run_engine(
                "generate",
                "/tmp/resolved",
                skip_seed_required_sections=True,
            )
            == 2
        )
        assert RUNNER.main(["generate", "--skip-seed-required-sections"]) == 2


def test_audit_passes_work_root_to_post_validators() -> None:
    """audit 後段の全 validator が同じ work_root を検査対象にする。"""
    with tempfile.TemporaryDirectory(prefix="seed-audit-validator-root-") as temp_dir:
        work_root = Path(temp_dir) / "work"
        manifest = {
            "deep_thinking": {"enabled": True},
            "requirement_analysis": {"enabled": True},
            "agent_kaizen": {"enabled": True},
            "agent_workflow": {"enabled": True},
        }
        captured: dict[str, tuple[object, ...]] = {}

        def capture(name: str):
            def _capture(*args: object) -> int:
                captured[name] = args
                return 0

            return _capture

        with (
            patch.object(RUNNER.subprocess, "call", return_value=0),
            patch.object(
                RUNNER,
                "_run_deep_thinking_validator",
                side_effect=capture("deep"),
            ),
            patch.object(
                RUNNER,
                "_run_requirement_analysis_validator",
                side_effect=capture("requirement"),
            ),
            patch.object(
                RUNNER,
                "_run_agent_kaizen_validator",
                side_effect=capture("kaizen"),
            ),
            patch.object(
                RUNNER,
                "_run_worker_contract_validator",
                side_effect=capture("worker"),
            ),
        ):
            assert (
                RUNNER.run_engine(
                    "audit",
                    "/tmp/resolved",
                    manifest,
                    work_root=str(work_root),
                )
                == 0
            )

        assert set(captured) == {"deep", "requirement", "kaizen", "worker"}
        for args in captured.values():
            assert args[0] is manifest
            assert args[1] == str(work_root)


def test_requirement_analysis_requires_agent_workflow() -> None:
    disabled = {
        "agent_workflow": {"enabled": False},
        "requirement_analysis": {"enabled": True},
    }
    enabled = {
        "agent_workflow": {"enabled": True},
        "requirement_analysis": {"enabled": True},
    }
    assert RUNNER._is_feature_enabled(disabled, "requirement_analysis") is False
    assert RUNNER._is_feature_enabled(enabled, "requirement_analysis") is True
    manifest = {
        **disabled,
        "outputs": [
            {"path": "keep.md", "template": "keep.md.template", "mode": "render"},
            {
                "path": ".cursor/skills/requirement-analysis/SKILL.md",
                "template": "skills/requirement-analysis/SKILL.md.template",
                "mode": "render",
                "feature": "requirement_analysis",
            },
        ],
    }
    filtered = RUNNER._filter_outputs_by_features(manifest)
    assert [item["path"] for item in filtered["outputs"]] == ["keep.md"]
    assert RUNNER._run_requirement_analysis_validator(disabled, "/tmp") == 0


def main() -> int:
    tests = (
        ("default audit requires seed sections", test_default_audit_requires_seed_sections),
        ("seed exception keeps other checks", test_seed_exception_keeps_other_checks_and_exit_codes),
        ("seed exception keeps fatal errors", test_seed_exception_keeps_fatal_errors),
        ("foundation gate keeps default audit", test_foundation_gate_keeps_default_audit),
        ("resolved runner routes flag", test_resolved_runner_routes_flag_only_to_audit),
        ("audit validator work root", test_audit_passes_work_root_to_post_validators),
        ("requirement analysis parent gate", test_requirement_analysis_requires_agent_workflow),
    )
    for label, test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            print(f"[test_seed_audit_scope] FAIL: {label}: {exc}", file=sys.stderr)
            return 1
        print(f"[test_seed_audit_scope] PASS: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
