#!/usr/bin/env python3
"""resolve_budget_thresholds.py の単体テスト。"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from resolve_budget_thresholds import format_shell_bytes_label, resolve, main  # noqa: E402


def test_shell_bytes_label():
    assert format_shell_bytes_label(768000) == "750 KiB"
    assert format_shell_bytes_label(4194304) == "4 MiB"
    assert format_shell_bytes_label(1048576) == "1 MiB"
    assert format_shell_bytes_label(5242880) == "5 MiB"
    print("PASS: shell_bytes_label formatting")


def test_200k_preset():
    r = resolve(200000)
    assert r["compact_yellow_percent"] == 60, f"yellow_pct: {r['compact_yellow_percent']}"
    assert r["compact_red_percent"] == 78, f"red_pct: {r['compact_red_percent']}"
    assert r["yellow"]["prompt_count"] == 35, f"prompt_y: {r['yellow']['prompt_count']}"
    assert r["red"]["prompt_count"] == 70, f"prompt_r: {r['red']['prompt_count']}"
    assert r["yellow"]["shell_bytes"] == 768000
    assert r["yellow"]["shell_bytes_label"] == "750 KiB"
    assert r["red"]["shell_bytes"] == 4194304
    assert r["red"]["shell_bytes_label"] == "4 MiB"
    assert r["min_context_window_tokens"] == 200000
    assert r["checkpoint_interval_prompts"] == 15
    assert r["compact_freshness_sec"] == 300
    assert r["compact_thrashing_count"] == 3
    print("PASS: 200K preset")


def test_300k_preset():
    r = resolve(300000)
    assert r["compact_yellow_percent"] == 60
    assert r["compact_red_percent"] == 80
    assert r["yellow"]["prompt_count"] == 45
    assert r["red"]["prompt_count"] == 90
    assert r["yellow"]["shell_bytes"] == 1048576
    assert r["yellow"]["shell_bytes_label"] == "1 MiB"
    assert r["red"]["shell_bytes"] == 5242880
    assert r["red"]["shell_bytes_label"] == "5 MiB"
    assert r["min_context_window_tokens"] == 300000
    print("PASS: 300K preset")


def test_custom_150k():
    r = resolve(150000)
    ratio = 150000 / 300000
    assert r["compact_yellow_percent"] == 60, f"yellow_pct: {r['compact_yellow_percent']}"
    assert r["compact_red_percent"] == 78, f"red_pct: {r['compact_red_percent']}"
    expected_y = max(15, round(45 * ratio))  # 23 → clamped to 23 (>15)
    expected_r = max(30, round(90 * ratio))  # 45
    assert r["yellow"]["prompt_count"] == expected_y, f"prompt_y: {r['yellow']['prompt_count']} != {expected_y}"
    assert r["red"]["prompt_count"] == expected_r, f"prompt_r: {r['red']['prompt_count']} != {expected_r}"
    assert r["min_context_window_tokens"] == 150000
    print(f"PASS: 150K custom → prompt_y={r['yellow']['prompt_count']}, prompt_r={r['red']['prompt_count']}")


def test_custom_1m():
    r = resolve(1000000)
    assert 55 <= r["compact_yellow_percent"] <= 60, f"yellow_pct: {r['compact_yellow_percent']}"
    assert 75 <= r["compact_red_percent"] <= 80, f"red_pct: {r['compact_red_percent']}"
    ratio = 1000000 / 300000
    assert r["yellow"]["prompt_count"] == round(45 * ratio), f"prompt_y: {r['yellow']['prompt_count']}"
    assert r["red"]["prompt_count"] == round(90 * ratio), f"prompt_r: {r['red']['prompt_count']}"
    print(f"PASS: 1M custom → prompt_y={r['yellow']['prompt_count']}, prompt_r={r['red']['prompt_count']}")


def test_null_fallback():
    """project.context_budget が未設定の manifest → exit 1 + 200K tier fallback"""
    manifest_content = """\
version: 1
project:
  name: "test"
framework:
  budget_thresholds:
    compact_yellow_percent: 60
    compact_red_percent: 80
    compact_freshness_sec: 300
    compact_thrashing_count: 3
    max_injection_bytes: 8192
    max_snapshot_bytes: 8192
    yellow:
      prompt_count: 45
      shell_bytes: 1048576
    red:
      prompt_count: 90
      shell_bytes: 5242880
    checkpoint_interval_prompts: 15
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(manifest_content)
        tmppath = f.name
    try:
        exit_code = main(["--manifest", tmppath])
        assert exit_code == 1, f"exit_code: {exit_code}"
        with open(tmppath) as f:
            content = f.read()
        assert "compact_red_percent: 78" in content, "200K tier fallback が適用されていない"
        assert "prompt_count: 35" in content, "200K tier prompt_y が適用されていない"
        print("PASS: null fallback (exit 1, 200K tier)")
    finally:
        os.unlink(tmppath)


def test_idempotent():
    """同一入力で2回実行 → 出力が同一"""
    manifest_content = """\
version: 1
project:
  name: "test"
  context_budget:
    min_context_window_tokens: 300000
framework:
  budget_thresholds:
    compact_yellow_percent: 60
    compact_red_percent: 80
    compact_freshness_sec: 300
    compact_thrashing_count: 3
    max_injection_bytes: 8192
    max_snapshot_bytes: 8192
    yellow:
      prompt_count: 45
      shell_bytes: 1048576
    red:
      prompt_count: 90
      shell_bytes: 5242880
    checkpoint_interval_prompts: 15
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(manifest_content)
        tmppath = f.name
    try:
        main(["--manifest", tmppath])
        with open(tmppath) as f:
            first = f.read()
        main(["--manifest", tmppath])
        with open(tmppath) as f:
            second = f.read()
        assert first == second, "冪等性が破れている"
        print("PASS: idempotent (2 runs produce identical output)")
    finally:
        os.unlink(tmppath)


if __name__ == "__main__":
    test_shell_bytes_label()
    test_200k_preset()
    test_300k_preset()
    test_custom_150k()
    test_custom_1m()
    test_null_fallback()
    test_idempotent()
    print("\nAll tests passed.")
