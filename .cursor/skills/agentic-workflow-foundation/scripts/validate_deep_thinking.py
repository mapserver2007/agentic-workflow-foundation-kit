#!/usr/bin/env python3
"""validate_deep_thinking.py — 生成済み config.yaml の静的契約検査。

検査 ID:
  G-DEEP-CONFIG-001 : 必須キー・型・空値
  G-DEEP-MODEL-001  : require_distinct_models 時の A/B モデル重複
  G-DEEP-BUDGET-001 : 再審上限の正の整数検査
  G-DEEP-POLICY-001 : model_unavailable / stop_when の契約値検査

対象外（実行時にのみ観測可能で静的検査では保証不能）:
  - 実モデル割当（Cursor Subagent API が返さない）
  - A/B の相互非参照（プロセス間隔離を外部観測できない）
  - 別プロセス実行（Subagent 起動の内部実装に依存）

exit code:
  0 = 全検査 PASS
  1 = 契約違反あり
  2 = 致命的エラー（ファイル不在 / YAML 破損）
"""
from __future__ import annotations

import argparse
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
    ".cursor", "skills", "deep-thinking", "config.yaml"
)

REQUIRED_MODELS_KEYS = ("analyst_a", "analyst_b")

REQUIRED_EXECUTION_KEYS = (
    "require_distinct_agents",
    "require_distinct_models",
    "model_unavailable",
    "max_rounds",
    "max_rebuttal_turns_per_issue",
    "max_issues_per_round",
    "stop_when",
)

BUDGET_KEYS = ("max_rounds", "max_rebuttal_turns_per_issue", "max_issues_per_round")

VALID_MODEL_UNAVAILABLE = ("ABORT",)
VALID_STOP_WHEN = ("NO_MATERIAL_ISSUES",)


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
        failures.append(("G-DEEP-CONFIG-001", "models セクションが存在しないか dict でない"))
        models = {}

    for key in REQUIRED_MODELS_KEYS:
        val = models.get(key)
        if not val or not isinstance(val, str) or not val.strip():
            failures.append(("G-DEEP-CONFIG-001", f"models.{key} が未設定または空"))

    execution = config.get("execution")
    if not isinstance(execution, dict):
        failures.append(("G-DEEP-CONFIG-001", "execution セクションが存在しないか dict でない"))
        execution = {}

    for key in REQUIRED_EXECUTION_KEYS:
        if key not in execution:
            failures.append(("G-DEEP-CONFIG-001", f"execution.{key} が未設定"))

    a_model = (models.get("analyst_a") or "").strip()
    b_model = (models.get("analyst_b") or "").strip()
    require_distinct = execution.get("require_distinct_models")
    if require_distinct and a_model and b_model and a_model == b_model:
        failures.append((
            "G-DEEP-MODEL-001",
            f"require_distinct_models=true だが A/B が同一モデル: {a_model}",
        ))

    for key in BUDGET_KEYS:
        val = execution.get(key)
        if val is None:
            continue
        if not isinstance(val, int) or val < 1:
            failures.append((
                "G-DEEP-BUDGET-001",
                f"execution.{key} は正の整数が必要（現在値: {val!r}）",
            ))

    mu = execution.get("model_unavailable")
    if mu is not None and mu not in VALID_MODEL_UNAVAILABLE:
        failures.append((
            "G-DEEP-POLICY-001",
            f"execution.model_unavailable の値 {mu!r} は契約外（許可値: {VALID_MODEL_UNAVAILABLE}）",
        ))

    sw = execution.get("stop_when")
    if sw is not None and sw not in VALID_STOP_WHEN:
        failures.append((
            "G-DEEP-POLICY-001",
            f"execution.stop_when の値 {sw!r} は契約外（許可値: {VALID_STOP_WHEN}）",
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

    if failures:
        print(f"[validate_deep_thinking] FAIL: {len(failures)} 件の契約違反")
        for check_id, reason in failures:
            print(f"  {check_id}: {reason}")
        return 1

    print("[validate_deep_thinking] PASS: 全静的検査を通過")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="deep-thinking config.yaml の静的契約検査",
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
