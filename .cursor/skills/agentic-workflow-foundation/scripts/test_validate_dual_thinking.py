#!/usr/bin/env python3
"""validate_dual_thinking.py の fixture テスト。

検査対象:
  - 有効設定 → PASS
  - A/B 同一モデル → G-DT-MODEL-001
  - 空モデル → G-DT-CONFIG-001
  - 無効な再審予算（0 / 負 / 非整数） → G-DT-BUDGET-001
  - 無効な停止方針 → G-DT-POLICY-001
  - 実行部の必須キー欠落 → G-DT-CONFIG-001
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from validate_dual_thinking import validate  # noqa: E402

VALID_CONFIG = {
    "models": {
        "analyst_a": "composer-2.5-fast",
        "analyst_b": "gpt-5.6-terra-medium",
    },
    "execution": {
        "require_distinct_agents": True,
        "require_distinct_models": True,
        "model_unavailable": "ABORT",
        "max_rounds": 3,
        "max_rebuttal_turns_per_issue": 1,
        "max_issues_per_round": 1,
        "stop_when": "NO_MATERIAL_ISSUES",
    },
    "high_impact_categories": ["security_or_authorization"],
}


def _with(**overrides) -> dict:
    """VALID_CONFIG のコピーにネストした上書きを適用する。"""
    import copy
    cfg = copy.deepcopy(VALID_CONFIG)
    for dotted_key, value in overrides.items():
        parts = dotted_key.split(".")
        node = cfg
        for p in parts[:-1]:
            node = node[p]
        if value is _DELETE:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = value
    return cfg


class _Sentinel:
    pass

_DELETE = _Sentinel()


def _ids(failures: list) -> set:
    return {f[0] for f in failures}


def test_valid_config():
    failures = validate(VALID_CONFIG)
    assert failures == [], f"valid config should PASS: {failures}"


def test_same_model_fails():
    cfg = _with(**{"models.analyst_b": "composer-2.5-fast"})
    failures = validate(cfg)
    assert "G-DT-MODEL-001" in _ids(failures), f"same model should trigger G-DT-MODEL-001: {failures}"


def test_same_model_allowed_when_not_required():
    cfg = _with(**{
        "models.analyst_b": "composer-2.5-fast",
        "execution.require_distinct_models": False,
    })
    failures = validate(cfg)
    assert "G-DT-MODEL-001" not in _ids(failures), (
        f"same model should be allowed when require_distinct_models=false: {failures}"
    )


def test_empty_model_fails():
    cfg = _with(**{"models.analyst_a": ""})
    failures = validate(cfg)
    assert "G-DT-CONFIG-001" in _ids(failures), f"empty model should trigger G-DT-CONFIG-001: {failures}"


def test_missing_model_key_fails():
    cfg = _with(**{"models.analyst_b": _DELETE})
    failures = validate(cfg)
    assert "G-DT-CONFIG-001" in _ids(failures)


def test_zero_budget_fails():
    cfg = _with(**{"execution.max_rounds": 0})
    failures = validate(cfg)
    assert "G-DT-BUDGET-001" in _ids(failures), f"zero budget should trigger G-DT-BUDGET-001: {failures}"


def test_negative_budget_fails():
    cfg = _with(**{"execution.max_rebuttal_turns_per_issue": -1})
    failures = validate(cfg)
    assert "G-DT-BUDGET-001" in _ids(failures)


def test_string_budget_fails():
    cfg = _with(**{"execution.max_issues_per_round": "abc"})
    failures = validate(cfg)
    assert "G-DT-BUDGET-001" in _ids(failures)


def test_invalid_model_unavailable_fails():
    cfg = _with(**{"execution.model_unavailable": "FALLBACK"})
    failures = validate(cfg)
    assert "G-DT-POLICY-001" in _ids(failures), (
        f"invalid model_unavailable should trigger G-DT-POLICY-001: {failures}"
    )


def test_invalid_stop_when_fails():
    cfg = _with(**{"execution.stop_when": "NEVER"})
    failures = validate(cfg)
    assert "G-DT-POLICY-001" in _ids(failures)


def test_missing_execution_key_fails():
    cfg = _with(**{"execution.stop_when": _DELETE})
    failures = validate(cfg)
    assert "G-DT-CONFIG-001" in _ids(failures)


def test_missing_models_section():
    cfg = dict(VALID_CONFIG)
    del cfg["models"]
    failures = validate(cfg)
    assert "G-DT-CONFIG-001" in _ids(failures)


def test_missing_execution_section():
    cfg = dict(VALID_CONFIG)
    del cfg["execution"]
    failures = validate(cfg)
    assert "G-DT-CONFIG-001" in _ids(failures)


def main() -> int:
    tests = [
        test_valid_config,
        test_same_model_fails,
        test_same_model_allowed_when_not_required,
        test_empty_model_fails,
        test_missing_model_key_fails,
        test_zero_budget_fails,
        test_negative_budget_fails,
        test_string_budget_fails,
        test_invalid_model_unavailable_fails,
        test_invalid_stop_when_fails,
        test_missing_execution_key_fails,
        test_missing_models_section,
        test_missing_execution_section,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}", file=sys.stderr)
            failed += 1
        except Exception as e:
            print(f"  ERROR: {t.__name__}: {e}", file=sys.stderr)
            failed += 1

    print(f"[test_validate_dual_thinking] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
