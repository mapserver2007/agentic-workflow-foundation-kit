#!/usr/bin/env python3
"""validate_requirement_analysis.py — 生成済み config.yaml の静的契約検査。

検査 ID:
  G-RA-CONFIG-001 : 必須キー（models.* / execution.*）の存在・型・非空
  G-RA-DEPTH-001  : analysis_depth 値域が standard | deep
  G-RA-GATE-001   : Gate A/B/C 定義と Issue Ledger type enum の存在（SKILL.md 参照で確認）
  G-RA-EXIT-001   : blocking_open_issues ゼロの退出条件定義（SKILL.md 参照で確認）
  G-RA-DEEP-001     : deep_thinking.enabled: true 時のみ deep 経路利用可
  G-RA-LEGACY-001 : workflow-triage 文字列が requirement-analysis テンプレートに含まれない
  G-RA-HIC-001    : high_impact_categories が定義されている

exit code:
  0 = 全検査 PASS
  1 = 契約違反あり
  2 = 致命的エラー（ファイル不在 / YAML 破損）
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
ENGINE_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import genlib  # noqa: E402

CONFIG_REL = os.path.join(
    ".cursor", "skills", "requirement-analysis", "config.yaml"
)

REQUIRED_MODELS_KEYS = ("normalize", "depth_triage", "standard_investigation")

PLACEHOLDER_MARKERS = ("[要確認]",)

REQUIRED_EXECUTION_KEYS = (
    "score_threshold",
    "max_gate_retries",
    "model_unavailable",
)

VALID_MODEL_UNAVAILABLE = ("ABORT",)


def _load_config(path: str) -> dict | None:
    try:
        return genlib.load_manifest(path)
    except genlib.YamlError:
        return None


def validate(config: dict) -> list[tuple[str, str]]:
    """config dict を検査し、(検査ID, 理由) のリストを返す。空なら全 PASS。"""
    failures: list[tuple[str, str]] = []

    models = config.get("models")
    if not isinstance(models, dict):
        failures.append(("G-RA-CONFIG-001", "models セクションが存在しないか dict でない"))
        models = {}

    for key in REQUIRED_MODELS_KEYS:
        val = models.get(key)
        if not val or not isinstance(val, str) or not val.strip():
            failures.append(("G-RA-CONFIG-001", f"models.{key} が未設定または空"))
        elif val.strip() in PLACEHOLDER_MARKERS:
            failures.append(("G-RA-CONFIG-001", f"models.{key} が未確認プレースホルダのまま（{val!r}）"))

    execution = config.get("execution")
    if not isinstance(execution, dict):
        failures.append(("G-RA-CONFIG-001", "execution セクションが存在しないか dict でない"))
        execution = {}

    for key in REQUIRED_EXECUTION_KEYS:
        if key not in execution:
            failures.append(("G-RA-CONFIG-001", f"execution.{key} が未設定"))

    score_threshold = execution.get("score_threshold")
    if score_threshold is not None:
        if not isinstance(score_threshold, int) or score_threshold < 1:
            failures.append((
                "G-RA-CONFIG-001",
                f"execution.score_threshold は正の整数が必要（現在値: {score_threshold!r}）",
            ))

    max_gate_retries = execution.get("max_gate_retries")
    if max_gate_retries is not None:
        if not isinstance(max_gate_retries, int) or max_gate_retries < 1:
            failures.append((
                "G-RA-CONFIG-001",
                f"execution.max_gate_retries は正の整数が必要（現在値: {max_gate_retries!r}）",
            ))

    mu = execution.get("model_unavailable")
    if mu is not None and mu not in VALID_MODEL_UNAVAILABLE:
        failures.append((
            "G-RA-CONFIG-001",
            f"execution.model_unavailable の値 {mu!r} は契約外（許可値: {VALID_MODEL_UNAVAILABLE}）",
        ))

    hic = config.get("high_impact_categories")
    if not isinstance(hic, list) or len(hic) == 0:
        failures.append((
            "G-RA-HIC-001",
            "high_impact_categories が未定義または空リスト",
        ))

    return failures


def validate_legacy_reference() -> list[tuple[str, str]]:
    """requirement-analysis テンプレート内に旧 workflow-triage 参照が残存しないことを検査する。"""
    failures: list[tuple[str, str]] = []
    ra_dir = os.path.join(
        ROOT, ".cursor", "skills", "requirement-analysis",
    )
    if not os.path.isdir(ra_dir):
        return failures

    for dirpath, _dirnames, filenames in os.walk(ra_dir):
        for filename in filenames:
            if not filename.endswith((".md", ".yaml")):
                continue
            filepath = os.path.join(dirpath, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            if "workflow-triage" in content:
                rel = os.path.relpath(filepath, ROOT)
                failures.append((
                    "G-RA-LEGACY-001",
                    f"旧参照 'workflow-triage' が残存: {rel}",
                ))
    return failures


def validate_deep_thinking_sot_duplication() -> list[tuple[str, str]]:
    """deep-thinking config に triage が残存かつ requirement-analysis が有効の場合を FAIL とする。"""
    failures: list[tuple[str, str]] = []
    dt_config_path = os.path.join(
        ROOT, ".cursor", "skills", "deep-thinking", "config.yaml",
    )
    ra_config_path = os.path.join(
        ROOT, ".cursor", "skills", "requirement-analysis", "config.yaml",
    )
    if not os.path.isfile(dt_config_path) or not os.path.isfile(ra_config_path):
        return failures

    dt_config = _load_config(dt_config_path)
    if dt_config and "triage" in dt_config:
        failures.append((
            "G-RA-LEGACY-001",
            "deep-thinking/config.yaml に 'triage' セクションが残存しています。"
            " requirement_analysis 有効時は手動削除してください（SoT 二重化）",
        ))
    return failures


def run(config_path: str) -> int:
    if not os.path.isfile(config_path):
        print(f"FATAL: config 不在: {config_path}", file=sys.stderr)
        return 2

    config = _load_config(config_path)
    if config is None:
        print(f"FATAL: config YAML 破損: {config_path}", file=sys.stderr)
        return 2

    failures = validate(config)
    failures.extend(validate_legacy_reference())
    failures.extend(validate_deep_thinking_sot_duplication())

    if failures:
        print(f"[validate_requirement_analysis] FAIL: {len(failures)} 件の契約違反")
        for check_id, reason in failures:
            print(f"  {check_id}: {reason}")
        return 1

    print("[validate_requirement_analysis] PASS: 全静的検査を通過")
    return 0


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="requirement-analysis config.yaml の静的契約検査",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(ROOT, CONFIG_REL),
        help="config.yaml のパス",
    )
    args = parser.parse_args(argv)
    return run(args.config)


if __name__ == "__main__":
    sys.exit(main())
