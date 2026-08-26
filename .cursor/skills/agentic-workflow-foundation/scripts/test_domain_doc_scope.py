#!/usr/bin/env python3
"""domain_doc_scope.py.template の回帰テスト。"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parent.parent.parent
sys.path.insert(0, str(ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"))
from genlib import load_manifest, render  # noqa: E402

TEMPLATE = SKILL / "templates/skills/session-handover/scripts/domain_doc_scope.py.template"
MANIFEST = SKILL / "manifest.yaml"


def _module(profile: str = "application", enabled: bool = True):
    manifest = load_manifest(str(MANIFEST))
    manifest["project"]["quality_gate"]["profile"] = profile
    manifest["agent_workflow"]["maintenance_docs"]["enabled"] = enabled
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "domain_doc_scope.py"
        path.write_text(render(TEMPLATE.read_text(encoding="utf-8"), manifest), encoding="utf-8")
        sys.modules.pop("domain_doc_scope", None)
        spec = importlib.util.spec_from_file_location("domain_doc_scope_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module


def test_policy_conditions():
    assert next(_module()).POLICY_ENABLED is True
    assert next(_module(profile="foundation")).POLICY_ENABLED is False
    assert next(_module(enabled=False)).POLICY_ENABLED is False


def test_domain_and_boundary_matching():
    mod = next(_module())
    assert mod.classify_path("docs/spec.md")[0]
    assert mod.classify_path("docs/spec/feature.md")[0]
    assert not mod.classify_path("docs/specification.md")[0]
    assert not mod.classify_path("docs/agent-tasks/reports/a.md")[0]


def test_markdown_normalization_and_fail_closed():
    mod = next(_module())
    assert mod.normalize_path_cell("./docs/spec.md") == "docs/spec.md"
    assert mod.normalize_path_cell("`docs/spec.md`") == "docs/spec.md"
    assert mod.normalize_path_cell("[spec](docs/spec.md)") == "docs/spec.md"
    for value in (
        "/tmp/docs/spec.md",
        "../docs/spec.md",
        "",
        "docs/spec.md, docs/api.md",
        "docs/spec.md docs/api.md",
        "docs/spec.md<br>docs/api.md",
        "docs/spec.md;docs/api.md",
        "[spec](docs/spec.md) [api](docs/api.md)",
    ):
        assert mod.classify_path(value)[2], value


def main() -> int:
    tests = [test_policy_conditions, test_domain_and_boundary_matching, test_markdown_normalization_and_fail_closed]
    for test in tests:
        test()
    print(f"[test_domain_doc_scope] {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
