#!/usr/bin/env python3
"""静的契約 validator（deep-thinking / agent-kaizen / requirement-analysis）の共有部。

3本の validator が同一の `models` / `execution` 検査、config 読み込み、結果出力、CLI 骨格を
個別に持っていたため、ここへ集約する。検査 ID とメッセージは各 validator が決める。
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

VALID_MODEL_UNAVAILABLE = ("ABORT",)

Failure = tuple[str, str]


def load_config(path: str) -> dict | None:
    try:
        return genlib.load_manifest(path)
    except genlib.YamlError:
        return None


def is_positive_int(value: object) -> bool:
    """bool を除く 1 以上の整数。"""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def check_models_and_execution(
    config: dict,
    check_id: str,
    models_keys: tuple[str, ...],
    execution_keys: tuple[str, ...],
    placeholder_markers: tuple[str, ...] = (),
) -> tuple[list[Failure], dict, dict]:
    """`models` / `execution` セクションの存在・必須キー・空値を検査する。

    戻り値は (failures, models, execution)。セクションが dict でない場合は空 dict を返し、
    後続の検査が継続できるようにする。
    """
    failures: list[Failure] = []

    models = config.get("models")
    if not isinstance(models, dict):
        failures.append((check_id, "models セクションが存在しないか dict でない"))
        models = {}
    for key in models_keys:
        val = models.get(key)
        if not val or not isinstance(val, str) or not val.strip():
            failures.append((check_id, f"models.{key} が未設定または空"))
        elif val.strip() in placeholder_markers:
            failures.append((check_id, f"models.{key} が未確認プレースホルダのまま（{val!r}）"))

    execution = config.get("execution")
    if not isinstance(execution, dict):
        failures.append((check_id, "execution セクションが存在しないか dict でない"))
        execution = {}
    for key in execution_keys:
        if key not in execution:
            failures.append((check_id, f"execution.{key} が未設定"))

    return failures, models, execution


def check_positive_int(execution: dict, key: str, check_id: str) -> list[Failure]:
    val = execution.get(key)
    if val is None or is_positive_int(val):
        return []
    return [(check_id, f"execution.{key} は正の整数が必要（現在値: {val!r}）")]


def check_model_unavailable(execution: dict, check_id: str) -> list[Failure]:
    mu = execution.get("model_unavailable")
    if mu is None or mu in VALID_MODEL_UNAVAILABLE:
        return []
    return [(
        check_id,
        f"execution.model_unavailable の値 {mu!r} は契約外（許可値: {VALID_MODEL_UNAVAILABLE}）",
    )]


def load_config_or_fatal(config_path: str) -> tuple[dict | None, int]:
    """config を読む。不在・YAML 破損は FATAL を出力して (None, 2) を返す。"""
    if not os.path.isfile(config_path):
        print(f"FATAL: config 不在: {config_path}", file=sys.stderr)
        return None, 2
    config = load_config(config_path)
    if config is None:
        print(f"FATAL: config YAML 破損: {config_path}", file=sys.stderr)
        return None, 2
    return config, 0


def report(tool: str, failures: list[Failure]) -> int:
    """検査結果を出力し、exit code（0=PASS / 1=契約違反）を返す。"""
    if failures:
        print(f"[{tool}] FAIL: {len(failures)} 件の契約違反")
        for check_id, reason in failures:
            print(f"  {check_id}: {reason}")
        return 1
    print(f"[{tool}] PASS: 全静的検査を通過")
    return 0


def make_parser(description: str, config_rel: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        default=os.path.join(ROOT, config_rel),
        help="config.yaml のパス",
    )
    return parser
