#!/usr/bin/env python3
"""validate_agent_kaizen.py — 生成済み config.yaml の静的契約検査。

検査 ID:
  G-AK-CONFIG-001 : 必須キー・型・空値
  G-AK-THRESHOLD-001 : score_threshold の正の整数検査
  G-AK-POLICY-001 : model_unavailable の契約値検査
  G-AK-PERSP-001  : high_impact_perspectives の非空・正規 ID・重複検査

対象外（実行時にのみ観測可能で静的検査では保証不能）:
  - 実モデル割当（Cursor Subagent API が返さない）
  - Subagent が検査対象を変更しないこと（プロセス間隔離を外部観測できない）
  - deep-thinking の A/B 独立性（Subagent 起動の内部実装に依存）

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
    ".cursor", "skills", "agent-kaizen", "config.yaml"
)

REQUIRED_MODELS_KEYS = ("depth_triage", "standard_analysis")

REQUIRED_EXECUTION_KEYS = (
    "score_threshold",
    "model_unavailable",
)

CANONICAL_PERSPECTIVES = frozenset({
    "SOT", "IDEM", "REND", "SAFE", "FAIL", "EXEC", "FLOW", "ARTF", "FEAT",
    "XPLAT", "CONC", "SESS", "NAME", "TEST", "WRAP", "RSLV", "ENVP", "NDST",
})


def validate(config: dict) -> list[tuple[str, str]]:
    """config dict を検査し、(検査ID, 理由) のリストを返す。空なら全 PASS。"""
    failures, _models, execution = vc.check_models_and_execution(
        config, "G-AK-CONFIG-001", REQUIRED_MODELS_KEYS, REQUIRED_EXECUTION_KEYS,
    )

    failures.extend(vc.check_positive_int(execution, "score_threshold", "G-AK-THRESHOLD-001"))
    failures.extend(vc.check_model_unavailable(execution, "G-AK-POLICY-001"))

    hip = config.get("high_impact_perspectives")
    if not isinstance(hip, list) or len(hip) == 0:
        failures.append((
            "G-AK-PERSP-001",
            "high_impact_perspectives が未定義または空リスト",
        ))
    else:
        seen: set[str] = set()
        for item in hip:
            if not isinstance(item, str) or not item.strip():
                failures.append((
                    "G-AK-PERSP-001",
                    f"high_impact_perspectives に空または非文字列の要素: {item!r}",
                ))
                continue
            normalized = item.strip()
            if normalized not in CANONICAL_PERSPECTIVES:
                failures.append((
                    "G-AK-PERSP-001",
                    f"high_impact_perspectives の値 {normalized!r} は正規 ID でない"
                    f"（許可値: {sorted(CANONICAL_PERSPECTIVES)}）",
                ))
            if normalized in seen:
                failures.append((
                    "G-AK-PERSP-001",
                    f"high_impact_perspectives に重複: {normalized!r}",
                ))
            seen.add(normalized)

    return failures


def run(config_path: str) -> int:
    config, rc = vc.load_config_or_fatal(config_path)
    if config is None:
        return rc
    return vc.report("validate_agent_kaizen", validate(config))


def main(argv=None) -> int:
    parser = vc.make_parser("agent-kaizen config.yaml の静的契約検査", CONFIG_REL)
    args = parser.parse_args(argv)
    return run(args.config)


if __name__ == "__main__":
    sys.exit(main())
