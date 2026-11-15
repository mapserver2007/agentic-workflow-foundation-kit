#!/usr/bin/env python3
"""Design Doc の自動検知と固定済み投影の状態判定を行う。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
import design_doc_projection as dp  # noqa: E402

DESIGN_DOC_PATHS = (
    Path("designs/docs/designdoc.md"),
    Path("designs/docs/design-doc.md"),
)


def detect_design_doc(root: Path) -> Path | None:
    matches = [root / relative for relative in DESIGN_DOC_PATHS if (root / relative).is_file()]
    if len(matches) > 1:
        joined = ", ".join(path.relative_to(root).as_posix() for path in matches)
        raise dp.SchemaError(f"Design Doc が複数存在します: {joined}")
    return matches[0] if matches else None


def resolve_projection(
    manifest_path: Path,
    *,
    allow_unpinned: bool,
) -> tuple[Path | None, dict | None]:
    """状態表を検査し、検出した Design Doc と固定済み投影を返す。"""
    if not manifest_path.is_file():
        raise dp.SchemaError(f"manifest が存在しません: {manifest_path}")
    root = manifest_path.parent
    design_doc = detect_design_doc(root)
    manifest = dp._load_yaml(manifest_path)
    pinned = manifest.get("design_doc")

    if design_doc is None:
        if pinned is not None:
            raise dp.SchemaError("固定済み design_doc の入力ファイルが消失しています")
        return None, None

    if pinned is None:
        if allow_unpinned:
            return design_doc, None
        raise dp.ProjectionError(
            "Design Doc を検出しましたが投影が未起案です: "
            f"{design_doc.relative_to(root).as_posix()}。"
            "draft を起案して validate → apply を実行してください"
        )
    if not isinstance(pinned, dict):
        raise dp.SchemaError("manifest.design_doc は mapping である必要があります")
    dp.validate(pinned, manifest_path, design_doc, require_approval=True)
    return design_doc, pinned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Design Doc 投影の状態を解決する")
    parser.add_argument("--manifest", type=Path, default=ROOT / "manifest.yaml")
    parser.add_argument("--check", action="store_true", help="read-only 状態検査")
    args = parser.parse_args(argv)
    try:
        design_doc, projection = resolve_projection(
            args.manifest,
            allow_unpinned=False,
        )
        if design_doc is None:
            print("PASS: Design Doc なし（スケルトン生成）")
        else:
            print(
                "PASS: Design Doc 投影 READY "
                f"path={design_doc.relative_to(args.manifest.parent).as_posix()} "
                f"digest={projection['digest']}"
            )
        return 0
    except dp.ProjectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (
        dp.SchemaError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        AttributeError,
        OSError,
        re.error,
    ) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
