#!/usr/bin/env python3
"""audit.py — 設定スキルの出力が冪等かつ設計書必須要件を満たすか監査する。

検査:
  (1) 冪等性: 各 outputs[] が manifest + templates の再生成結果と一致するか
        render : 出力 == 再描画結果（不一致 = 直接編集 = drift）
        marker : マーカーブロックが再 upsert で不変か（ブロック内編集 = drift）
        seed   : ファイルが存在するか（内容は追記ログなので比較しない）
        split  : 出力ディレクトリの各ファイルと索引が再生成結果と一致するか。さらに次を検査する
                 連結一致（ヘッダ行を除いて連結すると正本と一致）/ 残骸ファイルなし /
                 サイズ上限 / § 参照切れ / 索引の網羅 / プレースホルダの照合（placeholder_check）
  (2) 必須要件: outputs[].required_sections の文字列が出力に含まれるか（split は索引ファイル）
  (3) WARN    : `[要確認]` が残存する出力（Phase 1.5 対話の未確定。PASS だが要対応）

使い方:
  python3 audit.py --skill-dir <config-skill-dir>
  python3 audit.py --skill-dir <config-skill-dir> --skip-seed-required-sections

既定では seed を含む全 outputs[] の required_sections を検査する。
--skip-seed-required-sections は、consumer updater が適用対象外の既存 seed を
「存在」のみ監査するときに限って使用する。

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
import splitlib
from generate import (
    _read,
    _safe_join,
    _upsert_marker,
    split_build,
    split_dir_names,
    split_index_context,
)

PENDING_MARK = "[要確認]"


def _audit_split(root: str, rel: str, out: dict, target_dir: str, template_text: str,
                 manifest: dict, split: tuple) -> tuple:
    """mode: split の検査。(失敗メッセージのリスト, 警告メッセージのリスト) を返す。"""
    cfg, _source_rel, result = split
    fails = []
    warns = []
    if not os.path.isdir(target_dir):
        return ["出力ディレクトリ不在"], []
    names = split_dir_names(target_dir)

    # 残骸
    extra = [n for n in names if n not in result.files]
    if extra:
        fails.append(f"残骸ファイル（再生成結果にないファイル）: {extra}")

    # 各ファイルの一致（drift）
    missing_files = []
    actual = {}
    for name in result.order:
        content = _read(os.path.join(target_dir, name))
        if content is None:
            missing_files.append(name)
            continue
        actual[name] = content
        if content != result.files[name]:
            fails.append(f"drift（再生成結果と不一致 = 直接編集）: {name}")
    if missing_files:
        fails.append(f"出力ファイル不在: {missing_files}")

    # 連結一致（ヘッダ行を除いて順に連結すると、正本と一致する）
    if not missing_files:
        try:
            joined = "".join(splitlib.strip_header(actual[n]) for n in result.order)
        except ValueError as e:
            fails.append(f"連結できません: {e}")
        else:
            if joined != result.body:
                fails.append("分割ファイルを連結した内容が正本と一致しません")

    # 分割と索引の検査（サイズ上限、§ 参照切れ、索引の網羅、書式契約）
    for level, message in result.problems:
        (fails if level == splitlib.LEVEL_FAIL else warns).append(message)

    # プレースホルダの照合
    check = cfg.get("placeholder_check")
    if check and result.placeholders:
        binding = _read(_safe_join(root, check["path"], "outputs[].placeholder_check.path"))
        section = splitlib.section_text(binding, check["heading"]) if binding is not None else ""
        if not section.strip():
            fails.append(f"束縛節「{check['heading']}」が {check['path']} にありません")
        else:
            lacking = [p for p in result.placeholders if p not in section]
            if lacking:
                fails.append(f"束縛節に記入欄のないプレースホルダ: {lacking}")

    # 索引ファイル
    index_abs = _safe_join(root, cfg["index_path"], "outputs[].index_path")
    index_text = _read(index_abs)
    if index_text is None:
        fails.append(f"索引ファイル不在: {cfg['index_path']}")
    else:
        expected_index = genlib.render(template_text, split_index_context(manifest, result))
        if index_text != expected_index:
            fails.append(f"drift（索引が再生成結果と不一致 = 直接編集）: {cfg['index_path']}")
        lacking = [s for s in (out.get("required_sections") or []) if s not in index_text]
        if lacking:
            fails.append(f"必須要件欠落（索引）: {lacking}")
    return fails, warns


def run(skill_dir: str, *, skip_seed_required_sections: bool = False) -> int:
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
    split_warnings = []
    ok = 0

    # mode: split は先に計算する（1つの manifest に1エントリまで）
    split_state = {}
    for out in outputs:
        if not isinstance(out, dict) or out.get("mode", "render") != "split":
            continue  # 不正な要素は、下のループの定義エラー処理に任せる
        if split_state:
            print("FATAL: mode: split のエントリは1つまでです", file=sys.stderr)
            return 2
        try:
            split_state[out["path"]] = split_build(root, out, manifest)
        except (TypeError, KeyError, genlib.YamlError, genlib.RenderError, splitlib.SplitError) as e:
            print(f"FATAL: mode: split の入力エラー: {e}", file=sys.stderr)
            return 2

    # `_split` は、同じ実行内の全テンプレートへ渡す（generate.py と同じ）。manifest は変更しない。
    render_ctx = split_index_context(manifest, next(iter(split_state.values()))[2]) if split_state else manifest

    for out in outputs:
        try:
            rel = out["path"]
            mode = out.get("mode", "render")
            target_path = _safe_join(root, rel, "outputs[].path")
            template_path = _safe_join(templates_dir, out["template"], "outputs[].template")
        except (TypeError, KeyError, genlib.YamlError) as e:
            print(f"FATAL: outputs[] 定義エラー: {e}", file=sys.stderr)
            return 2
        try:
            template_text = _read(template_path)
        except genlib.YamlError as e:
            print(f"FATAL: {e}", file=sys.stderr)
            return 2
        if template_text is None:
            print(f"FATAL: テンプレート不在: {template_path}", file=sys.stderr)
            return 2

        if mode == "split":
            try:
                fails, warns = _audit_split(
                    root, rel, out, target_path, template_text, manifest, split_state[rel]
                )
            except (genlib.YamlError, genlib.RenderError) as e:
                print(f"FATAL: mode: split の検査失敗 ({rel}): {e}", file=sys.stderr)
                return 2
            split_warnings.extend((rel, m) for m in warns)
            if fails:
                failures.extend((rel, m) for m in fails)
                continue
            ok += 1
            continue

        try:
            existing = _read(target_path)
        except genlib.YamlError as e:
            print(f"FATAL: {e}", file=sys.stderr)
            return 2
        if existing is None:
            failures.append((rel, "出力ファイル不在"))
            continue

        try:
            if mode == "render":
                expected = genlib.render(template_text, render_ctx)
                if existing != expected:
                    failures.append((rel, "drift（再生成結果と不一致 = 直接編集）"))
                    continue
            elif mode == "marker":
                body = genlib.render(template_text, render_ctx)
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

        missing = []
        if not (skip_seed_required_sections and mode == "seed"):
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
    if split_warnings:
        print(f"  WARN(split): {len(split_warnings)} 件（書式契約の警告。PASS だが要対応）")
        for rel, message in split_warnings:
            print(f"    - {rel}: {message}")
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
    parser.add_argument(
        "--skip-seed-required-sections",
        action="store_true",
        help="consumer updater 用: seed は存在のみ検査し、required_sections を検査しない",
    )
    args = parser.parse_args(argv)
    return run(
        args.skill_dir,
        skip_seed_required_sections=args.skip_seed_required_sections,
    )


if __name__ == "__main__":
    sys.exit(main())
