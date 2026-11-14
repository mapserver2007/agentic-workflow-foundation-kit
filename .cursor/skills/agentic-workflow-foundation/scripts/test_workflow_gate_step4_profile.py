#!/usr/bin/env python3
"""workflow-gate.sh step4 の profile selector をテンプレートで静的に検査する。

foundation / application / unknown それぞれの実行結果（self のみ・verify のみ・exit 2）は
test_workflow_gate_step4_integration.py が検査する。ここは、実行では観測しにくいテンプレート側の宣言だけを見る。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = (
    HERE.parent
    / "templates"
    / "skills"
    / "session-handover"
    / "scripts"
    / "workflow-gate.sh.template"
)


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


def test_application_template_always_runs_gen() -> None:
    content = _read(TEMPLATE)
    # gen が application profile で実行される契約は、gen コマンド行と GEN_DIRTY 不在で担保する（ログ文言は契約ではない）。
    assert "GEN_DIRTY" not in content
    assert '"$ROOT_DIR/bin/quality-gate" gen' in content


def main() -> int:
    tests = [
        test_template_declares_profile_selector,
        test_application_template_always_runs_gen,
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
