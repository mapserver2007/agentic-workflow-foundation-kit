#!/usr/bin/env python3
"""validate_agent_kaizen.py の fixture テスト。

検査対象:
  - 有効設定 → PASS
  - 空モデル → G-AK-CONFIG-001
  - models セクション欠落 → G-AK-CONFIG-001
  - execution セクション欠落 → G-AK-CONFIG-001
  - score_threshold 不正（0 / 負 / 非整数 / bool） → G-AK-THRESHOLD-001
  - model_unavailable 不正 → G-AK-POLICY-001
  - high_impact_perspectives 空 → G-AK-PERSP-001
  - high_impact_perspectives 不正 ID → G-AK-PERSP-001
  - high_impact_perspectives 重複 → G-AK-PERSP-001
"""
from __future__ import annotations

import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from validate_agent_kaizen import validate, CANONICAL_PERSPECTIVES  # noqa: E402

VALID_CONFIG = {
    "models": {
        "depth_triage": "composer-2.5-fast",
        "standard_analysis": "composer-2.5-fast",
    },
    "execution": {
        "score_threshold": 2,
        "model_unavailable": "ABORT",
    },
    "high_impact_perspectives": ["SAFE", "FAIL", "CONC", "SESS", "NDST"],
}


class _Sentinel:
    pass


_DELETE = _Sentinel()


def _with(**overrides) -> dict:
    """VALID_CONFIG のコピーにネストした上書きを適用する。"""
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


def _ids(failures: list) -> set:
    return {f[0] for f in failures}


def test_valid_config():
    failures = validate(VALID_CONFIG)
    assert failures == [], f"valid config should PASS: {failures}"


def test_empty_model_fails():
    cfg = _with(**{"models.depth_triage": ""})
    failures = validate(cfg)
    assert "G-AK-CONFIG-001" in _ids(failures), f"empty model should trigger G-AK-CONFIG-001: {failures}"


def test_missing_model_key_fails():
    cfg = _with(**{"models.standard_analysis": _DELETE})
    failures = validate(cfg)
    assert "G-AK-CONFIG-001" in _ids(failures)


def test_missing_models_section():
    cfg = dict(VALID_CONFIG)
    del cfg["models"]
    failures = validate(cfg)
    assert "G-AK-CONFIG-001" in _ids(failures)


def test_missing_execution_section():
    cfg = dict(VALID_CONFIG)
    del cfg["execution"]
    failures = validate(cfg)
    assert "G-AK-CONFIG-001" in _ids(failures)


def test_missing_execution_key_fails():
    cfg = _with(**{"execution.score_threshold": _DELETE})
    failures = validate(cfg)
    assert "G-AK-CONFIG-001" in _ids(failures)


def test_zero_threshold_fails():
    cfg = _with(**{"execution.score_threshold": 0})
    failures = validate(cfg)
    assert "G-AK-THRESHOLD-001" in _ids(failures), f"zero threshold should trigger G-AK-THRESHOLD-001: {failures}"


def test_negative_threshold_fails():
    cfg = _with(**{"execution.score_threshold": -1})
    failures = validate(cfg)
    assert "G-AK-THRESHOLD-001" in _ids(failures)


def test_string_threshold_fails():
    cfg = _with(**{"execution.score_threshold": "abc"})
    failures = validate(cfg)
    assert "G-AK-THRESHOLD-001" in _ids(failures)


def test_bool_true_threshold_fails():
    cfg = _with(**{"execution.score_threshold": True})
    failures = validate(cfg)
    assert "G-AK-THRESHOLD-001" in _ids(failures), (
        f"bool True should trigger G-AK-THRESHOLD-001: {failures}"
    )


def test_bool_false_threshold_fails():
    cfg = _with(**{"execution.score_threshold": False})
    failures = validate(cfg)
    assert "G-AK-THRESHOLD-001" in _ids(failures), (
        f"bool False should trigger G-AK-THRESHOLD-001: {failures}"
    )


def test_invalid_model_unavailable_fails():
    cfg = _with(**{"execution.model_unavailable": "FALLBACK"})
    failures = validate(cfg)
    assert "G-AK-POLICY-001" in _ids(failures), (
        f"invalid model_unavailable should trigger G-AK-POLICY-001: {failures}"
    )


def test_empty_perspectives_fails():
    cfg = copy.deepcopy(VALID_CONFIG)
    cfg["high_impact_perspectives"] = []
    failures = validate(cfg)
    assert "G-AK-PERSP-001" in _ids(failures)


def test_missing_perspectives_fails():
    cfg = copy.deepcopy(VALID_CONFIG)
    del cfg["high_impact_perspectives"]
    failures = validate(cfg)
    assert "G-AK-PERSP-001" in _ids(failures)


def test_invalid_perspective_id_fails():
    cfg = copy.deepcopy(VALID_CONFIG)
    cfg["high_impact_perspectives"] = ["SAFE", "INVALID_ID"]
    failures = validate(cfg)
    assert "G-AK-PERSP-001" in _ids(failures)
    assert any("INVALID_ID" in f[1] for f in failures)


def test_duplicate_perspective_fails():
    cfg = copy.deepcopy(VALID_CONFIG)
    cfg["high_impact_perspectives"] = ["SAFE", "FAIL", "SAFE"]
    failures = validate(cfg)
    assert "G-AK-PERSP-001" in _ids(failures)
    assert any("重複" in f[1] for f in failures)


def test_all_canonical_perspectives_valid():
    cfg = copy.deepcopy(VALID_CONFIG)
    cfg["high_impact_perspectives"] = sorted(CANONICAL_PERSPECTIVES)
    failures = validate(cfg)
    assert failures == [], f"all canonical perspectives should PASS: {failures}"


def main() -> int:
    tests = [
        test_valid_config,
        test_empty_model_fails,
        test_missing_model_key_fails,
        test_missing_models_section,
        test_missing_execution_section,
        test_missing_execution_key_fails,
        test_zero_threshold_fails,
        test_negative_threshold_fails,
        test_string_threshold_fails,
        test_bool_true_threshold_fails,
        test_bool_false_threshold_fails,
        test_invalid_model_unavailable_fails,
        test_empty_perspectives_fails,
        test_missing_perspectives_fails,
        test_invalid_perspective_id_fails,
        test_duplicate_perspective_fails,
        test_all_canonical_perspectives_valid,
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

    print(f"[test_validate_agent_kaizen] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
