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
  - dual-thinking の A/B 独立性（Subagent 起動の内部実装に依存）

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
    ".cursor", "skills", "agent-kaizen", "config.yaml"
)

REQUIRED_MODELS_KEYS = ("depth_triage", "standard_analysis")

REQUIRED_EXECUTION_KEYS = (
    "score_threshold",
    "model_unavailable",
)

VALID_MODEL_UNAVAILABLE = ("ABORT",)

CANONICAL_PERSPECTIVES = frozenset({
    "SOT", "IDEM", "REND", "SAFE", "FAIL", "EXEC", "FLOW", "ARTF", "FEAT",
    "XPLAT", "CONC", "SESS", "NAME", "TEST", "WRAP", "RSLV", "ENVP", "NDST",
})


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
        failures.append(("G-AK-CONFIG-001", "models セクションが存在しないか dict でない"))
        models = {}

    for key in REQUIRED_MODELS_KEYS:
        val = models.get(key)
        if not val or not isinstance(val, str) or not val.strip():
            failures.append(("G-AK-CONFIG-001", f"models.{key} が未設定または空"))

    execution = config.get("execution")
    if not isinstance(execution, dict):
        failures.append(("G-AK-CONFIG-001", "execution セクションが存在しないか dict でない"))
        execution = {}

    for key in REQUIRED_EXECUTION_KEYS:
        if key not in execution:
            failures.append(("G-AK-CONFIG-001", f"execution.{key} が未設定"))

    score_threshold = execution.get("score_threshold")
    if score_threshold is not None:
        if (
            isinstance(score_threshold, bool)
            or not isinstance(score_threshold, int)
            or score_threshold < 1
        ):
            failures.append((
                "G-AK-THRESHOLD-001",
                f"execution.score_threshold は正の整数が必要（現在値: {score_threshold!r}）",
            ))

    mu = execution.get("model_unavailable")
    if mu is not None and mu not in VALID_MODEL_UNAVAILABLE:
        failures.append((
            "G-AK-POLICY-001",
            f"execution.model_unavailable の値 {mu!r} は契約外（許可値: {VALID_MODEL_UNAVAILABLE}）",
        ))

    hip = config.get("high_impact_perspectives")
    if not isinstance(hip, list) or len(hip) == 0:
        failures.append((
            "G-AK-PERSP-001",
            "high_impact_perspectives が未定義または空リスト",
        ))
    elif isinstance(hip, list):
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
    if not os.path.isfile(config_path):
        print(f"FATAL: config 不在: {config_path}", file=sys.stderr)
        return 2

    config = _load_config(config_path)
    if config is None:
        print(f"FATAL: config YAML 破損: {config_path}", file=sys.stderr)
        return 2

    failures = validate(config)

    if failures:
        print(f"[validate_agent_kaizen] FAIL: {len(failures)} 件の契約違反")
        for check_id, reason in failures:
            print(f"  {check_id}: {reason}")
        return 1

    print("[validate_agent_kaizen] PASS: 全静的検査を通過")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="agent-kaizen config.yaml の静的契約検査",
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
