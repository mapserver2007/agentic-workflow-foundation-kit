#!/usr/bin/env python3
"""実差分 Domain docs ゲートの回帰テスト。"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parent.parent.parent
sys.path.insert(0, str(ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"))
from genlib import load_manifest, render  # noqa: E402


def _module(
    profile: str = "application",
    maintenance_docs_enabled: bool = True,
):
    manifest = load_manifest(str(SKILL / "manifest.yaml"))
    manifest["project"]["quality_gate"]["profile"] = profile
    manifest["agent_workflow"]["maintenance_docs"]["enabled"] = maintenance_docs_enabled
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        scripts = SKILL / "templates/skills/session-handover/scripts"
        for output, source in (
            ("domain_doc_scope.py", "domain_doc_scope.py.template"),
            ("gate_domain.py", "gate-domain-write-scope.py.template"),
        ):
            (temp / output).write_text(render((scripts / source).read_text(encoding="utf-8"), manifest), encoding="utf-8")
        sys.path.insert(0, str(temp))
        sys.modules.pop("domain_doc_scope", None)
        spec = importlib.util.spec_from_file_location("gate_domain_write_scope_test", temp / "gate_domain.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _repo(include_domain: bool = False) -> tuple[tempfile.TemporaryDirectory, Path, Path, str]:
    context = tempfile.TemporaryDirectory()
    repo = Path(context.name)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "src").mkdir()
    (repo / "src/main.py").write_text("before\n", encoding="utf-8")
    if include_domain:
        (repo / "docs").mkdir()
        (repo / "docs/spec.md").write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    report = repo / "report.md"
    report.write_text(f"- implementation-base-commit: {base}\n", encoding="utf-8")
    return context, repo, report, base


def test_tracked_domain_modification_fails():
    mod = _module()
    context, repo, report, _ = _repo(include_domain=True)
    try:
        (repo / "docs/spec.md").write_text("changed\n", encoding="utf-8")
        assert mod.check(report, repo)[0] == 1
    finally:
        context.cleanup()


def test_untracked_domain_file_fails_even_if_envelope_omits_it():
    mod = _module()
    context, repo, report, base = _repo()
    try:
        (repo / "docs").mkdir()
        (repo / "docs/api.md").write_text("untracked\n", encoding="utf-8")
        envelope = repo / "step3.md"
        envelope.write_text(
            f"---\nstep: step3\nstatus: complete\nbase_commit_sha: {base[:12]}\n"
            "changed_files:\n  - src/main.py\nuntracked_files: []\n---\n",
            encoding="utf-8",
        )
        rc, messages = mod.check(report, repo, envelope)
        assert rc == 1 and "G-WRITE-SCOPE-DOMAIN-001" in "\n".join(messages)
    finally:
        context.cleanup()


def test_source_passes_and_base_mismatch_fails():
    mod = _module()
    context, repo, report, base = _repo()
    try:
        (repo / "src/main.py").write_text("changed\n", encoding="utf-8")
        assert mod.check(report, repo)[0] == 0
        _git(repo, "add", "src/main.py")
        _git(repo, "commit", "-m", "other")
        other = _git(repo, "rev-parse", "HEAD")
        envelope = repo / "step3.md"
        envelope.write_text(
            f"---\nbase_commit_sha: {other[:12]}\n---\n",
            encoding="utf-8",
        )
        rc, messages = mod.check(report, repo, envelope)
        assert rc == 1 and "G-WRITE-SCOPE-BASE-001" in "\n".join(messages)
        envelope.write_text(f"---\nbase_commit_sha: {base[:12]}\n---\n", encoding="utf-8")
        assert mod.check(report, repo, envelope)[0] == 0
    finally:
        context.cleanup()


def test_non_ancestor_base_commit_fails():
    mod = _module()
    context, repo, report, base = _repo()
    try:
        (repo / "docs").mkdir()
        (repo / "docs/spec.md").write_text("same\n", encoding="utf-8")
        (repo / "src/main.py").write_text("current\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "current")
        current = _git(repo, "rev-parse", "HEAD")

        _git(repo, "branch", "other", base)
        _git(repo, "checkout", "other")
        (repo / "docs").mkdir(exist_ok=True)
        (repo / "docs/spec.md").write_text("same\n", encoding="utf-8")
        _git(repo, "add", "docs/spec.md")
        _git(repo, "commit", "-m", "non-ancestor-base")
        non_ancestor = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", current)

        report.write_text(
            f"- implementation-base-commit: {non_ancestor}\n",
            encoding="utf-8",
        )
        rc, messages = mod.check(report, repo)
        assert rc == 1
        assert "G-WRITE-SCOPE-BASE-001" in "\n".join(messages)
    finally:
        context.cleanup()


def test_report_and_repository_error_contract():
    mod = _module()
    context, repo, report, _ = _repo()
    try:
        assert mod.check(repo / "missing.md", repo)[0] == 2
        assert mod.check(report, repo / "missing-repo")[0] == 2
        report.write_text("", encoding="utf-8")
        assert mod.check(report, repo)[0] == 1
        report.write_text(
            "- implementation-base-commit: 0123456\n- implementation-base-commit: 7654321\n",
            encoding="utf-8",
        )
        assert mod.check(report, repo)[0] == 1
    finally:
        context.cleanup()


def test_foundation_profile_skips_before_report_and_repo_validation():
    mod = _module("foundation")
    rc, messages = mod.check(Path("/missing-report.md"), Path("/missing-repo"))
    assert rc == 0
    assert "policy 無効" in "\n".join(messages)


def test_maintenance_docs_disabled_skips_before_base_commit_validation():
    mod = _module(maintenance_docs_enabled=False)
    context, repo, report, _ = _repo()
    try:
        report.write_text("", encoding="utf-8")
        rc, messages = mod.check(report, repo)
        assert rc == 0
        assert "policy 無効" in "\n".join(messages)
    finally:
        context.cleanup()


def main() -> int:
    tests = [
        test_tracked_domain_modification_fails,
        test_untracked_domain_file_fails_even_if_envelope_omits_it,
        test_source_passes_and_base_mismatch_fails,
        test_non_ancestor_base_commit_fails,
        test_report_and_repository_error_contract,
        test_foundation_profile_skips_before_report_and_repo_validation,
        test_maintenance_docs_disabled_skips_before_base_commit_validation,
    ]
    for test in tests:
        test()
    print(f"[test_gate_domain_write_scope] {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
