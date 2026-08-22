#!/usr/bin/env python3
"""validate_requirement_analysis.py の deep-brief fixture テスト。

検査対象:
  - 有効な config と deep-brief → PASS
  - deep-brief 不在 → G-RA-DEEP-BRIEF-001 / exit 1
  - 必須見出し欠落 → G-RA-DEEP-BRIEF-001 / exit 1
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from validate_requirement_analysis import run  # noqa: E402

VALID_CONFIG = """\
models:
  normalize: "normalize-model"
  depth_triage: "triage-model"
  standard_investigation: "investigation-model"
execution:
  score_threshold: 2
  max_gate_retries: 3
  model_unavailable: "ABORT"
high_impact_categories:
  - "security_or_authorization"
"""


def _run_fixture(deep_brief_content: str | None) -> int:
    """一時 fixture のみで validator を実行し、root の生成物を変更しない。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        config_path = temp_path / "config.yaml"
        deep_brief_path = temp_path / "deep-brief.md"
        config_path.write_text(VALID_CONFIG, encoding="utf-8")
        if deep_brief_content is not None:
            deep_brief_path.write_text(deep_brief_content, encoding="utf-8")
        return run(str(config_path), str(deep_brief_path))


def test_valid_deep_brief_passes():
    exit_code = _run_fixture(
        "## 必須ブリーフ要素\n\n内容\n\n## 検査次元インベントリ\n\n内容\n"
    )
    assert exit_code == 0, f"valid deep-brief should PASS: exit {exit_code}"


def test_missing_deep_brief_fails():
    exit_code = _run_fixture(None)
    assert exit_code == 1, f"missing deep-brief should return exit 1: exit {exit_code}"


def test_missing_required_heading_fails():
    exit_code = _run_fixture("## 必須ブリーフ要素\n\n内容\n")
    assert exit_code == 1, f"missing required heading should return exit 1: exit {exit_code}"


def main() -> int:
    tests = [
        test_valid_deep_brief_passes,
        test_missing_deep_brief_fails,
        test_missing_required_heading_fails,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL: {test.__name__}: {exc}", file=sys.stderr)
            failed += 1
        except Exception as exc:
            print(f"  ERROR: {test.__name__}: {exc}", file=sys.stderr)
            failed += 1

    print(f"[test_validate_requirement_analysis] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
