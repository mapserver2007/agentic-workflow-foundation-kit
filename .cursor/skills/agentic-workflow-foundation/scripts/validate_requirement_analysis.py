#!/usr/bin/env python3
"""validate_requirement_analysis.py — 生成済み requirement-analysis 契約の静的検査。

検査 ID:
  G-RA-CONFIG-001 : 必須キー（models.* / execution.*）の存在・型・非空
  G-RA-LEGACY-001 : workflow-triage 文字列が requirement-analysis テンプレートに含まれない
  G-RA-HIC-001    : high_impact_categories が定義されている
  G-RA-DEEP-BRIEF-001 : deep-brief.md の存在と固定見出し

本スクリプトは config.yaml と deep-brief.md の静的検査を担当する。
ランタイム検査（digest 結合 ack / AC 相互参照 / provenance / Memo 構造）は
gate-artifact.py / gate-report.py が担当する（QUALITY_GATE.md §1.7 参照）。

exit code:
  0 = 全検査 PASS
  1 = 契約違反あり
  2 = 致命的エラー（読み込み不能 / YAML 破損）
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import validate_common as vc  # noqa: E402
from validate_common import ROOT  # noqa: E402

CONFIG_REL = os.path.join(
    ".cursor", "skills", "requirement-analysis", "config.yaml"
)
DEEP_BRIEF_REL = os.path.join(
    ".cursor", "skills", "requirement-analysis", "references", "deep-brief.md"
)

REQUIRED_MODELS_KEYS = ("normalize", "depth_triage", "standard_investigation")
REQUIRED_DEEP_BRIEF_HEADINGS = (
    "## 必須ブリーフ要素",
    "## 検査次元インベントリ",
)

PLACEHOLDER_MARKERS = ("[要確認]",)

REQUIRED_EXECUTION_KEYS = (
    "score_threshold",
    "max_gate_retries",
    "model_unavailable",
)


def validate(config: dict) -> list[tuple[str, str]]:
    """config dict を検査し、(検査ID, 理由) のリストを返す。空なら全 PASS。"""
    failures, _models, execution = vc.check_models_and_execution(
        config, "G-RA-CONFIG-001", REQUIRED_MODELS_KEYS, REQUIRED_EXECUTION_KEYS,
        placeholder_markers=PLACEHOLDER_MARKERS,
    )

    for key in ("score_threshold", "max_gate_retries"):
        failures.extend(vc.check_positive_int(execution, key, "G-RA-CONFIG-001"))
    failures.extend(vc.check_model_unavailable(execution, "G-RA-CONFIG-001"))

    hic = config.get("high_impact_categories")
    if not isinstance(hic, list) or len(hic) == 0:
        failures.append((
            "G-RA-HIC-001",
            "high_impact_categories が未定義または空リスト",
        ))

    return failures


def validate_legacy_reference(root: str | None = None) -> list[tuple[str, str]]:
    """requirement-analysis テンプレート内に旧 workflow-triage 参照が残存しないことを検査する。"""
    failures: list[tuple[str, str]] = []
    scan_root = os.path.abspath(root or ROOT)
    ra_dir = os.path.join(
        scan_root, ".cursor", "skills", "requirement-analysis",
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
                rel = os.path.relpath(filepath, scan_root)
                failures.append((
                    "G-RA-LEGACY-001",
                    f"旧参照 'workflow-triage' が残存: {rel}",
                ))
    return failures


def validate_deep_thinking_sot_duplication(
    root: str | None = None,
) -> list[tuple[str, str]]:
    """deep-thinking config に triage が残存かつ requirement-analysis が有効の場合を FAIL とする。"""
    failures: list[tuple[str, str]] = []
    scan_root = os.path.abspath(root or ROOT)
    dt_config_path = os.path.join(
        scan_root, ".cursor", "skills", "deep-thinking", "config.yaml",
    )
    ra_config_path = os.path.join(
        scan_root, ".cursor", "skills", "requirement-analysis", "config.yaml",
    )
    if not os.path.isfile(dt_config_path) or not os.path.isfile(ra_config_path):
        return failures

    dt_config = vc.load_config(dt_config_path)
    if dt_config and "triage" in dt_config:
        failures.append((
            "G-RA-LEGACY-001",
            "deep-thinking/config.yaml に 'triage' セクションが残存しています。"
            " requirement_analysis 有効時は手動削除してください（SoT 二重化）",
        ))
    return failures


def validate_deep_brief(path: str) -> list[tuple[str, str]]:
    """deep-brief.md の存在と固定見出しを検査する。読み込み不能時は OSError を送出する。"""
    if not os.path.exists(path):
        return [("G-RA-DEEP-BRIEF-001", f"deep-brief.md が不在: {path}")]

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    return [
        ("G-RA-DEEP-BRIEF-001", f"deep-brief.md の必須見出しが欠落: {heading}")
        for heading in REQUIRED_DEEP_BRIEF_HEADINGS
        if heading not in content
    ]


def run(
    config_path: str,
    deep_brief_path: str | None = None,
    root: str | None = None,
) -> int:
    config, rc = vc.load_config_or_fatal(config_path)
    if config is None:
        return rc

    scan_root = os.path.abspath(root or ROOT)
    failures = validate(config)
    failures.extend(validate_legacy_reference(scan_root))
    failures.extend(validate_deep_thinking_sot_duplication(scan_root))
    deep_brief_path = deep_brief_path or os.path.join(scan_root, DEEP_BRIEF_REL)
    try:
        failures.extend(validate_deep_brief(deep_brief_path))
    except OSError as exc:
        print(
            f"FATAL: deep-brief 読み込み不能: {deep_brief_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    return vc.report("validate_requirement_analysis", failures)


def main(argv=None) -> int:
    parser = vc.make_parser("requirement-analysis config.yaml の静的契約検査", CONFIG_REL)
    parser.add_argument(
        "--deep-brief",
        default=os.path.join(ROOT, DEEP_BRIEF_REL),
        help="deep-brief.md のパス",
    )
    args = parser.parse_args(argv)
    return run(args.config, args.deep_brief)


if __name__ == "__main__":
    sys.exit(main())
