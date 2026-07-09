#!/usr/bin/env python3
"""project.context_budget.min_context_window_tokens から budget_thresholds を算出する（Phase 1.55）。

tier テーブル:
  ≤200K → 保守的（red_pct=78, prompt_y=35 等）
  ≤300K → 標準（red_pct=80, prompt_y=45 等）
  >300K → headroom 式でスケール

exit code:
  0 — 正常（budget_thresholds を root manifest に書き込み済み）
  1 — WARN: project.context_budget 未設定。seed default（200K tier）で fallback
  2 — 致命的エラー（manifest 破損等）
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
GENLIB_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if GENLIB_DIR not in sys.path:
    sys.path.insert(0, GENLIB_DIR)

import genlib  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")

# ---- tier テーブル ----
TIER_200K = {
    "min_context_window_tokens": 200000,
    "compact_yellow_percent": 60,
    "compact_red_percent": 78,
    "yellow_prompt_count": 35,
    "red_prompt_count": 70,
    "yellow_shell_bytes": 768000,
    "red_shell_bytes": 4194304,
}

TIER_300K = {
    "min_context_window_tokens": 300000,
    "compact_yellow_percent": 60,
    "compact_red_percent": 80,
    "yellow_prompt_count": 45,
    "red_prompt_count": 90,
    "yellow_shell_bytes": 1048576,
    "red_shell_bytes": 5242880,
}

# 固定値（全 tier 共通 — context サイズに非依存）
FIXED = {
    "compact_freshness_sec": 300,
    "compact_thrashing_count": 3,
    "max_injection_bytes": 8192,
    "max_snapshot_bytes": 8192,
    "checkpoint_interval_prompts": 15,
}

# headroom 式のベース・クランプ
BASE_WINDOW = 300000
BASE_YELLOW_PCT = 60
BASE_RED_PCT = 80
BASE_PROMPT_Y = 45
BASE_PROMPT_R = 90
YELLOW_PCT_FLOOR = 55
YELLOW_PCT_CEIL = 60
RED_PCT_FLOOR = 75
RED_PCT_CEIL = 80


def format_shell_bytes_label(n: int) -> str:
    """shell_bytes を二進 KiB/MiB の人間可読表記に変換する（1024 基数）。"""
    mib = 1024 * 1024
    kib = 1024
    if n >= mib and n % mib == 0:
        return f"{n // mib} MiB"
    if n >= kib and n % kib == 0:
        return f"{n // kib} KiB"
    if n >= mib:
        return f"{n / mib:.2f} MiB"
    return f"{n / kib:.1f} KiB"


def _out(level: str, msg: str) -> None:
    print(f"[resolve_budget_thresholds] {level}: {msg}")


def resolve(min_window: int) -> dict:
    """min_context_window_tokens から全 budget_thresholds を算出する。"""
    if min_window == 200000:
        tier = TIER_200K
    elif min_window == 300000:
        tier = TIER_300K
    else:
        # headroom 式: プリセット以外は 300K ベースで比例スケール + clamp
        ratio = min_window / BASE_WINDOW
        if min_window < 200000:
            base_yellow = TIER_200K["compact_yellow_percent"]
            base_red = TIER_200K["compact_red_percent"]
            shell_y = TIER_200K["yellow_shell_bytes"]
            shell_r = TIER_200K["red_shell_bytes"]
        else:
            base_yellow = BASE_YELLOW_PCT
            base_red = BASE_RED_PCT
            shell_y = 1048576
            shell_r = 5242880
        tier = {
            "min_context_window_tokens": min_window,
            "compact_yellow_percent": max(YELLOW_PCT_FLOOR, min(YELLOW_PCT_CEIL, base_yellow)),
            "compact_red_percent": max(RED_PCT_FLOOR, min(RED_PCT_CEIL, base_red)),
            "yellow_prompt_count": max(15, round(BASE_PROMPT_Y * ratio)),
            "red_prompt_count": max(30, round(BASE_PROMPT_R * ratio)),
            "yellow_shell_bytes": shell_y,
            "red_shell_bytes": shell_r,
        }

    return {
        "min_context_window_tokens": tier["min_context_window_tokens"],
        "compact_yellow_percent": tier["compact_yellow_percent"],
        "compact_red_percent": tier["compact_red_percent"],
        "compact_freshness_sec": FIXED["compact_freshness_sec"],
        "compact_thrashing_count": FIXED["compact_thrashing_count"],
        "max_injection_bytes": FIXED["max_injection_bytes"],
        "max_snapshot_bytes": FIXED["max_snapshot_bytes"],
        "yellow": {
            "prompt_count": tier["yellow_prompt_count"],
            "shell_bytes": tier["yellow_shell_bytes"],
            "shell_bytes_label": format_shell_bytes_label(tier["yellow_shell_bytes"]),
        },
        "red": {
            "prompt_count": tier["red_prompt_count"],
            "shell_bytes": tier["red_shell_bytes"],
            "shell_bytes_label": format_shell_bytes_label(tier["red_shell_bytes"]),
        },
        "checkpoint_interval_prompts": FIXED["checkpoint_interval_prompts"],
    }


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_nested_block(lines: list[str], parent: str, child: str):
    """parent > child ブロックの開始行・終了行・parent 終了行を返す。"""
    p_start = None
    for idx, line in enumerate(lines):
        if line.rstrip() == f"{parent}:" and _indent_of(line) == 0:
            p_start = idx
            break
    if p_start is None:
        return None, None, None
    p_last = p_start
    j = p_start + 1
    while j < len(lines):
        if lines[j].strip() == "":
            j += 1
            continue
        if _indent_of(lines[j]) > 0:
            p_last = j
            j += 1
            continue
        break

    parent_indent = 2
    c_start = None
    for idx in range(p_start + 1, p_last + 1):
        stripped = lines[idx].rstrip()
        if stripped == f"{'  ' * 1}{child}:" and _indent_of(lines[idx]) == parent_indent:
            c_start = idx
            break
    if c_start is None:
        return p_last + 1, p_last, p_last
    last = c_start
    j = c_start + 1
    while j < len(lines):
        if lines[j].strip() == "":
            j += 1
            continue
        if _indent_of(lines[j]) > parent_indent:
            last = j
            j += 1
            continue
        break
    return c_start, last, p_last


def _render_budget_block(resolved: dict) -> list[str]:
    """budget_thresholds ブロックの YAML 行を生成する。"""
    return [
        "  budget_thresholds:",
        f"    # resolve_budget_thresholds.py が project.context_budget.min_context_window_tokens から算出。",
        f"    # 以下は {resolved['min_context_window_tokens'] // 1000}K tier のデフォルト。Phase 1.55 resolver が上書きする。",
        f"    min_context_window_tokens: {resolved['min_context_window_tokens']}",
        f"    compact_yellow_percent: {resolved['compact_yellow_percent']}",
        f"    compact_red_percent: {resolved['compact_red_percent']}",
        f"    compact_freshness_sec: {resolved['compact_freshness_sec']}",
        f"    compact_thrashing_count: {resolved['compact_thrashing_count']}",
        f"    max_injection_bytes: {resolved['max_injection_bytes']}",
        f"    max_snapshot_bytes: {resolved['max_snapshot_bytes']}",
        "    yellow:",
        f"      prompt_count: {resolved['yellow']['prompt_count']}",
        f"      shell_bytes: {resolved['yellow']['shell_bytes']}",
        f"      shell_bytes_label: \"{resolved['yellow']['shell_bytes_label']}\"",
        "    red:",
        f"      prompt_count: {resolved['red']['prompt_count']}",
        f"      shell_bytes: {resolved['red']['shell_bytes']}",
        f"      shell_bytes_label: \"{resolved['red']['shell_bytes_label']}\"",
        f"    checkpoint_interval_prompts: {resolved['checkpoint_interval_prompts']}",
    ]


def _render_manifest(content: str, resolved: dict) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]

    start, last, p_last = _find_nested_block(lines, "framework", "budget_thresholds")
    block = _render_budget_block(resolved)

    if start is None:
        _out("WARN", "framework.budget_thresholds ブロックが見つからない — 末尾に追加")
        lines = lines + [""] + ["framework:"] + block
    elif start > last:
        insert_at = p_last + 1
        lines = lines[:insert_at] + block + lines[insert_at:]
    else:
        lines = lines[:start] + block + lines[last + 1:]

    return newline.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="min_context_window_tokens から budget_thresholds を算出する"
    )
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true",
                        help="dry-run: 算出結果を表示するが書き込まない")
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        _out("ERROR", f"manifest が見つからない: {args.manifest}")
        return 2
    try:
        manifest = genlib.load_manifest(args.manifest)
    except genlib.YamlError as e:
        _out("ERROR", f"manifest 解析失敗: {e}")
        return 2

    ctx = (manifest.get("project") or {}).get("context_budget") or {}
    raw = ctx.get("min_context_window_tokens")

    if raw is None:
        _out("WARN", "project.context_budget.min_context_window_tokens が未設定 → seed default（200K tier）で fallback")
        min_window = 200000
        exit_code = 1
    else:
        try:
            min_window = int(raw)
        except (ValueError, TypeError):
            _out("ERROR", f"min_context_window_tokens が数値でない: {raw}")
            return 2
        if min_window < 50000:
            _out("ERROR", f"min_context_window_tokens が小さすぎる（< 50K）: {min_window}")
            return 2
        exit_code = 0

    resolved = resolve(min_window)
    _out("INFO", f"min_window={min_window} → yellow_pct={resolved['compact_yellow_percent']}, "
         f"red_pct={resolved['compact_red_percent']}, "
         f"prompt_y={resolved['yellow']['prompt_count']}, "
         f"prompt_r={resolved['red']['prompt_count']}")

    if args.check:
        _out("INFO", f"--check モード。書き込みスキップ")
        return exit_code

    with open(args.manifest, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = _render_manifest(content, resolved)
    changed = new_content != content

    if changed:
        with open(args.manifest, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
    _out("PASS", f"budget_thresholds を root manifest へ反映（{'更新あり' if changed else '更新なし=冪等'}）")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
