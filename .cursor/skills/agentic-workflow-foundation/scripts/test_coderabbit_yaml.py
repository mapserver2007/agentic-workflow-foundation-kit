#!/usr/bin/env python3
"""生成済み CodeRabbit 設定が有効な YAML であることを検査する。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def _enabled_flag(node: object) -> bool | None:
    """契約フィールド用。bool 以外は未確定として無視する。"""
    if isinstance(node, dict) and isinstance(node.get("enabled"), bool):
        return node["enabled"]
    return None


def _feature_enabled_flag(node: object) -> bool | None:
    """top-level feature 用。生成器の bool() と同じく 0 を無効にする。"""
    if isinstance(node, dict) and "enabled" in node:
        return bool(node["enabled"])
    return None


def _check_enabled_normalization() -> str | None:
    if _feature_enabled_flag({"enabled": 0}) is not False:
        return "top-level enabled: 0 が無効になりません"
    if _feature_enabled_flag({"enabled": 1}) is not True:
        return "top-level enabled: 1 が有効になりません"
    if _enabled_flag({"enabled": 0}) is not None:
        return "契約の enabled: 0 を無効化とみなしました"
    if _enabled_flag({"enabled": False}) is not False:
        return "契約の enabled: false を無視しました"
    return None


def _coderabbit_explicitly_disabled(root: Path) -> bool:
    """生成と同じ優先順で coderabbit.enabled が false と確定しているときだけ真。

    seed の top-level、root overlay は生成器と同じ bool()。
    承認済み tech_contract.review.coderabbit は bool のときだけ上書きする。
    判定できないときは false（ファイル不在を失敗のままにする）。
    """
    import yaml

    enabled: bool | None = None
    seed = root / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"
    root_manifest = root / "manifest.yaml"
    for path in (seed, root_manifest):
        if not path.is_file():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        flag = _feature_enabled_flag(data.get("coderabbit"))
        if flag is not None:
            enabled = flag
        if path != root_manifest:
            continue
        contract = data.get("tech_contract")
        review = contract.get("review") if isinstance(contract, dict) else None
        coderabbit = review.get("coderabbit") if isinstance(review, dict) else None
        projected = _enabled_flag(coderabbit)
        if projected is not None:
            enabled = projected
    return enabled is False


def main() -> int:
    normalization_error = _check_enabled_normalization()
    if normalization_error:
        print(f"[test_coderabbit_yaml] FAIL: {normalization_error}", file=sys.stderr)
        return 1
    try:
        import yaml
    except ImportError:
        print("[test_coderabbit_yaml] FATAL: PyYAML が必要です", file=sys.stderr)
        return 2

    path = ROOT / ".coderabbit.yaml"
    if not path.is_file():
        if _coderabbit_explicitly_disabled(ROOT):
            print("[test_coderabbit_yaml] SKIP: .coderabbit.yaml 不在（coderabbit 無効）")
            return 0
        print("[test_coderabbit_yaml] FAIL: .coderabbit.yaml がありません", file=sys.stderr)
        return 1
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"[test_coderabbit_yaml] FAIL: {exc}", file=sys.stderr)
        return 1
    if not isinstance(value, dict):
        print("[test_coderabbit_yaml] FAIL: top-level mapping が必要です", file=sys.stderr)
        return 1
    instructions = ((value.get("reviews") or {}).get("path_instructions") or [])
    if not instructions or not all(
        isinstance(item, dict) and isinstance(item.get("instructions"), str)
        for item in instructions
    ):
        print("[test_coderabbit_yaml] FAIL: path_instructions が不正です", file=sys.stderr)
        return 1
    print("[test_coderabbit_yaml] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
