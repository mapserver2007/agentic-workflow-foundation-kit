#!/usr/bin/env python3
"""audit.py — 設定スキルの出力が冪等かつ設計書必須要件を満たすか監査する。

検査:
  (1) 冪等性: 各 outputs[] が manifest + templates の再生成結果と一致するか
        render : 出力 == 再描画結果（不一致 = 直接編集 = drift）
        marker : マーカーブロックが再 upsert で不変か（ブロック内編集 = drift）
        seed   : ファイルが存在するか（内容は追記ログなので比較しない）
  (2) 必須要件: outputs[].required_sections の文字列が出力に含まれるか
  (3) WARN    : `[要確認]` が残存する出力（Phase 1.5 対話の未確定。PASS だが要対応）

使い方:
  python3 audit.py --skill-dir <config-skill-dir>

exit code（QUALITY_GATE 3段階に準拠）:
  0 = 冪等 + 必須要件充足（`[要確認]` 残存は WARN だが PASS）
  1 = drift / 必須要件欠落 / 出力ファイル不在
  2 = 致命的エラー（manifest 破損 / テンプレート不在 / 描画失敗）
"""
from __future__ import annotations

import argparse
import os
import sys

import genlib
from generate import _read, _upsert_marker

PENDING_MARK = "[要確認]"


def run(skill_dir: str) -> int:
    skill_dir = os.path.abspath(skill_dir)
    manifest_path = os.path.join(skill_dir, "manifest.yaml")
    templates_dir = os.path.join(skill_dir, "templates")
    try:
        manifest = genlib.load_manifest(manifest_path)
        manifest = genlib.apply_inherited_project(manifest, skill_dir)
    except genlib.YamlError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2

    root = genlib.root_from_skill_dir(skill_dir)
    marker_id = manifest.get("marker_id", "managed")
    outputs = manifest.get("outputs") or []

    failures = []
    warnings = []
    ok = 0

    for out in outputs:
        rel = out["path"]
        mode = out.get("mode", "render")
        target_path = os.path.join(root, rel)
        template_path = os.path.join(templates_dir, out["template"])
        template_text = _read(template_path)
        if template_text is None:
            print(f"FATAL: テンプレート不在: {template_path}", file=sys.stderr)
            return 2

        existing = _read(target_path)
        if existing is None:
            failures.append((rel, "出力ファイル不在"))
            continue

        try:
            if mode == "render":
                expected = genlib.render(template_text, manifest)
                if existing != expected:
                    failures.append((rel, "drift（再生成結果と不一致 = 直接編集）"))
                    continue
            elif mode == "marker":
                body = genlib.render(template_text, manifest)
                if _upsert_marker(existing, marker_id, body) != existing:
                    failures.append((rel, "drift（マーカーブロックが再生成と不一致）"))
                    continue
            elif mode == "seed":
                pass  # 存在のみ検査
            else:
                print(f"FATAL: 未知の mode ({rel}): {mode}", file=sys.stderr)
                return 2
        except genlib.RenderError as e:
            print(f"FATAL: 描画失敗 ({rel}): {e}", file=sys.stderr)
            return 2

        missing = [s for s in (out.get("required_sections") or []) if s not in existing]
        if missing:
            failures.append((rel, f"必須要件欠落: {missing}"))
            continue

        if PENDING_MARK in existing:
            warnings.append(rel)
        ok += 1

    print(f"監査: {len(outputs)} 出力 (marker_id={marker_id}, root={root})")
    print(f"  PASS: {ok}")
    if warnings:
        print(f"  WARN: {len(warnings)} 出力に {PENDING_MARK} 残存（Phase 1.5 対話で確定すること）")
        for rel in warnings:
            print(f"    - {rel}")
    if failures:
        print(f"  FAIL: {len(failures)}")
        for rel, why in failures:
            print(f"    - {rel}: {why}")
        return 1
    print("OK: 全出力が冪等かつ必須要件を充足。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="出力の冪等性 + 必須要件を監査")
    parser.add_argument("--skill-dir", required=True, help="設定スキルのディレクトリ")
    args = parser.parse_args(argv)
    return run(args.skill_dir)


if __name__ == "__main__":
    sys.exit(main())
