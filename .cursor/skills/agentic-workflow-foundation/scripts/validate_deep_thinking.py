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

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import validate_common as vc  # noqa: E402

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

VALID_STOP_WHEN = ("NO_MATERIAL_ISSUES",)


def validate(config: dict) -> list[tuple[str, str]]:
    """config dict を検査し、(検査ID, 理由) のリストを返す。空なら全 PASS。"""
    failures, models, execution = vc.check_models_and_execution(
        config, "G-DEEP-CONFIG-001", REQUIRED_MODELS_KEYS, REQUIRED_EXECUTION_KEYS,
    )

    a_model = (models.get("analyst_a") or "").strip()
    b_model = (models.get("analyst_b") or "").strip()
    require_distinct = execution.get("require_distinct_models")
    if require_distinct and a_model and b_model and a_model == b_model:
        failures.append((
            "G-DEEP-MODEL-001",
            f"require_distinct_models=true だが A/B が同一モデル: {a_model}",
        ))

    for key in BUDGET_KEYS:
        failures.extend(vc.check_positive_int(execution, key, "G-DEEP-BUDGET-001"))

    failures.extend(vc.check_model_unavailable(execution, "G-DEEP-POLICY-001"))

    sw = execution.get("stop_when")
    if sw is not None and sw not in VALID_STOP_WHEN:
        failures.append((
            "G-DEEP-POLICY-001",
            f"execution.stop_when の値 {sw!r} は契約外（許可値: {VALID_STOP_WHEN}）",
        ))

    return failures


def run(config_path: str) -> int:
    config, rc = vc.load_config_or_fatal(config_path)
    if config is None:
        return rc
    return vc.report("validate_deep_thinking", validate(config))


def main(argv=None) -> int:
    parser = vc.make_parser("deep-thinking config.yaml の静的契約検査", CONFIG_REL)
    args = parser.parse_args(argv)
    return run(args.config)


if __name__ == "__main__":
    sys.exit(main())
