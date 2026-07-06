#!/usr/bin/env python3
"""generate.py — 設定スキルの manifest.yaml + templates/ から出力ファイルを決定論生成する。

使い方:
  python3 generate.py --skill-dir <config-skill-dir>           # 生成（出力をリポジトリへ書き出す）
  python3 generate.py --skill-dir <config-skill-dir> --check   # 冪等性ドライラン（書き込まない）

出力モード（manifest.yaml > outputs[].mode）:
  render : テンプレート全展開でファイルを丸ごと生成（直接編集は drift）
  marker : `marker_id` のマーカーブロックを既存ファイルへ upsert（ブロック外は不可侵）
  seed   : 不在時のみ初期生成。既存ファイルは上書きしない（DECISIONS/GOTCHAS 等の追記ログ）

exit code:
  0 = 生成成功 / --check で全出力が冪等（差分なし）
  1 = --check で差分あり（再生成が必要）
  2 = 致命的エラー（manifest 破損 / テンプレート不在 等）
"""
from __future__ import annotations

import argparse
import os
import stat
import sys

import genlib


def _marker_block(marker_id: str, body: str) -> str:
    start = f"# >>> {marker_id} managed >>>"
    end = f"# <<< {marker_id} managed <<<"
    if not body.endswith("\n"):
        body += "\n"
    return f"{start}\n{body}{end}\n"


def _upsert_marker(existing: str, marker_id: str, body: str) -> str:
    block = _marker_block(marker_id, body)
    start = f"# >>> {marker_id} managed >>>"
    end = f"# <<< {marker_id} managed <<<"
    si = existing.find(start)
    ei = existing.find(end)
    if si != -1 and ei != -1 and ei > si:
        region_start = existing.rfind("\n", 0, si) + 1
        nl = existing.find("\n", ei)
        region_end = len(existing) if nl == -1 else nl + 1
        return existing[:region_start] + block + existing[region_end:]
    if existing and not existing.endswith("\n"):
        existing += "\n"
    return existing + block


def _read(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path: str, content: str, executable: bool) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    if executable:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _safe_join(base: str, rel: str, field_name: str) -> str:
    """manifest 由来の相対パスが意図した base 配下に収まることを保証する。"""
    base_abs = os.path.abspath(base)
    if not isinstance(rel, str) or not rel:
        raise genlib.YamlError(f"{field_name} は非空文字列で指定してください")
    candidate = os.path.abspath(os.path.join(base_abs, rel))
    if os.path.isabs(rel) or os.path.commonpath([base_abs, candidate]) != base_abs:
        raise genlib.YamlError(f"{field_name} が許可範囲外です: {rel}")
    return candidate


def expected_content(out: dict, root_ctx: dict, target_path: str,
                     template_text: str, marker_id: str) -> str:
    """出力の「あるべき内容」を返す（render/seed=全展開, marker=upsert 結果）。"""
    mode = out.get("mode", "render")
    if mode in ("render", "seed"):
        return genlib.render(template_text, root_ctx)
    if mode == "marker":
        body = genlib.render(template_text, root_ctx)
        existing = _read(target_path) or ""
        return _upsert_marker(existing, marker_id, body)
    raise genlib.RenderError(f"未知の mode: {mode}")


def run(skill_dir: str, check: bool) -> int:
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

    changed = []
    written = []
    for out in outputs:
        try:
            rel = out["path"]
            target_path = _safe_join(root, rel, "outputs[].path")
            template_path = _safe_join(templates_dir, out["template"], "outputs[].template")
        except (TypeError, KeyError, genlib.YamlError) as e:
            print(f"FATAL: outputs[] 定義エラー: {e}", file=sys.stderr)
            return 2
        existing = _read(target_path)
        mode = out.get("mode", "render")

        if mode == "seed" and existing is not None:
            continue

        template_text = _read(template_path)
        if template_text is None:
            print(f"FATAL: テンプレート不在: {template_path}", file=sys.stderr)
            return 2
        try:
            expected = expected_content(
                out, manifest, target_path, template_text, marker_id
            )
        except genlib.RenderError as e:
            print(f"FATAL: 描画失敗 ({rel}): {e}", file=sys.stderr)
            return 2

        if check:
            if existing != expected:
                changed.append((rel, "新規作成" if existing is None else "差分あり"))
            continue

        _write(target_path, expected, bool(out.get("executable")))
        written.append((rel, mode))

    if check:
        if changed:
            print("冪等性ドライラン: 再生成が必要な出力あり")
            for rel, why in changed:
                print(f"  [{why}] {rel}")
            return 1
        print(f"冪等性ドライラン: 全 {len(outputs)} 出力が最新（差分なし）")
        return 0

    print(f"生成完了: {len(written)} 出力 (marker_id={marker_id}, root={root})")
    for rel, mode in written:
        print(f"  [{mode}] {rel}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="manifest + templates から出力を決定論生成")
    parser.add_argument("--skill-dir", required=True, help="設定スキルのディレクトリ")
    parser.add_argument("--check", action="store_true", help="書き込まず冪等性のみ検査")
    args = parser.parse_args(argv)
    return run(args.skill_dir, args.check)


if __name__ == "__main__":
    sys.exit(main())
