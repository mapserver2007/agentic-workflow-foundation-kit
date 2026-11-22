#!/usr/bin/env python3
"""generate.py — 設定スキルの manifest.yaml + templates/ から出力ファイルを決定論生成する。

使い方:
  python3 generate.py --skill-dir <config-skill-dir>           # 生成（出力をリポジトリへ書き出す）
  python3 generate.py --skill-dir <config-skill-dir> --check   # 冪等性ドライラン（書き込まない）

出力モード（manifest.yaml > outputs[].mode）:
  render : テンプレート全展開でファイルを丸ごと生成（直接編集は drift）
  marker : `marker_id` のマーカーブロックを既存ファイルへ upsert（ブロック外は不可侵）
  seed   : 不在時のみ初期生成。既存ファイルは上書きしない（DECISIONS/GOTCHAS や Domain docs 等の追記ログ）。
  split  : Markdown の正本を、見出し単位で機械的に分割した逐語ファイル群（出力ディレクトリ）と、
           索引ファイルを出力する。出力ディレクトリは kit が専有し、再生成のたびに過不足を直す
           （残骸ファイルを削除する）。分割と索引の計算は splitlib.py に集約している。

exit code:
  0 = 生成成功 / --check で全出力が冪等（差分なし）
  1 = --check で差分あり（再生成が必要）
 2 = 致命的エラー（manifest 破損 / テンプレート不在 / 出力パスへの権限拒否 等）
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile

import genlib
import splitlib


EXECUTABLE_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_STRUCTURAL_HEADING_RE = re.compile(r"^##[ \t]+\S")


class SectionMismatch(Exception):
    """構造見出しが対象テキストから順に見つからない（節マージ不可）。"""

    def __init__(self, heading: str, where: str, reason: str | None = None):
        self.heading = heading
        self.where = where
        if reason is None:
            super().__init__(f"構造見出し {heading!r} が {where} に見つかりません")
        else:
            super().__init__(f"構造見出し {heading!r} ({where}): {reason}")


def _fence_mask(lines: list[str]) -> list[bool]:
    """各行がコードフェンスの内側（区切り行を含む）なら True。"""
    mask: list[bool] = []
    open_fence: str | None = None
    for line in lines:
        match = _FENCE_RE.match(line)
        if open_fence is None:
            mask.append(bool(match))
            if match:
                open_fence = match.group(1)
            continue
        mask.append(True)
        stripped = line.strip()
        if (
            match
            and stripped
            and set(stripped) == {open_fence[0]}
            and len(stripped) >= len(open_fence)
        ):
            open_fence = None
    return mask


def structural_headings(text: str) -> list[str]:
    """コードフェンス外の `## ` 見出し行を出現順に返す（行末の改行は除く）。"""
    lines = text.splitlines(keepends=True)
    mask = _fence_mask(lines)
    return [
        line.rstrip("\r\n")
        for line, inside in zip(lines, mask)
        if not inside and _STRUCTURAL_HEADING_RE.match(line)
    ]


def split_structural_sections(
    text: str, headings: list[str], where: str
) -> tuple[str, list[str]]:
    """`headings` を先頭から順に探して分割し、(前文, 節本文リスト) を返す。

    各節は「構造見出し行から次の構造見出し行の直前まで」の生の文字列で、
    連結すると元のテキストに戻る。`headings` に無い `##` は節本文に含める。
    見出しを順に見つけられないときは SectionMismatch を送出する。
    """
    lines = text.splitlines(keepends=True)
    mask = _fence_mask(lines)
    starts: list[int] = []
    cursor = 0
    for heading in headings:
        found = None
        for index in range(cursor, len(lines)):
            if not mask[index] and lines[index].rstrip("\r\n") == heading:
                found = index
                break
        if found is None:
            raise SectionMismatch(heading, where)
        starts.append(found)
        cursor = found + 1
    if not starts:
        return text, []
    preamble = "".join(lines[: starts[0]])
    bounds = starts + [len(lines)]
    sections = [
        "".join(lines[bounds[i]: bounds[i + 1]]) for i in range(len(starts))
    ]
    return preamble, sections


def _heading_counts(text: str, headings: list[str]) -> dict[str, int]:
    """`headings` の各見出しが、コードフェンス外で何回出現するかを数える。"""
    lines = text.splitlines(keepends=True)
    mask = _fence_mask(lines)
    counts = dict.fromkeys(headings, 0)
    for line, inside in zip(lines, mask):
        stripped = line.rstrip("\r\n")
        if not inside and stripped in counts:
            counts[stripped] += 1
    return counts


def merge_seed_sections(
    existing: str, pristine: str, expected: str
) -> tuple[str, list[str]]:
    """投影なしスケルトンのまま残る構造節だけを、投影あり描画の節へ置換する。

    戻り値は (マージ結果, 置換した構造見出しのリスト)。手で書いた節と前文は保持する。
    構造見出しが既存・投影なし・投影ありのいずれかから順に見つからないときは
    SectionMismatch を送出する。投影あり描画で構造見出しの出現数が投影なしと
    異なるとき（投影本文が同名の `##` を含む）も、境界を誤認しないよう SectionMismatch を送出する。
    """
    headings = structural_headings(pristine)
    pristine_counts = _heading_counts(pristine, headings)
    expected_counts = _heading_counts(expected, headings)
    for heading in headings:
        if expected_counts[heading] != pristine_counts[heading]:
            raise SectionMismatch(
                heading,
                "投影あり描画",
                "出現数が投影なしスケルトンと一致しません（投影本文が同名の見出しを含みます）",
            )
    _, pristine_sections = split_structural_sections(pristine, headings, "投影なしスケルトン")
    _, expected_sections = split_structural_sections(expected, headings, "投影あり描画")
    preamble, existing_sections = split_structural_sections(existing, headings, "既存ファイル")
    merged_sections: list[str] = []
    replaced: list[str] = []
    for heading, current, base, projected in zip(
        headings, existing_sections, pristine_sections, expected_sections
    ):
        if current == base and base != projected:
            merged_sections.append(projected)
            replaced.append(heading)
        else:
            merged_sections.append(current)
    return preamble + "".join(merged_sections), replaced


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
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    existing_mode = (
        stat.S_IMODE(os.lstat(path).st_mode)
        if os.path.lexists(path) and not os.path.islink(path)
        else 0o644
    )
    mode = existing_mode | EXECUTABLE_BITS if executable else existing_mode
    fd, temporary = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_join(base: str, rel: str, field_name: str) -> str:
    """manifest 由来の相対パスが意図した base 配下に収まることを保証する。"""
    base_abs = os.path.abspath(base)
    if not isinstance(rel, str) or not rel:
        raise genlib.YamlError(f"{field_name} は非空文字列で指定してください")
    candidate = os.path.abspath(os.path.join(base_abs, rel))
    if os.path.isabs(rel) or os.path.commonpath([base_abs, candidate]) != base_abs:
        raise genlib.YamlError(f"{field_name} が許可範囲外です: {rel}")
    current = base_abs
    relative = os.path.relpath(candidate, base_abs)
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise genlib.YamlError(
                f"{field_name} が symlink を経由しています: {rel}"
            )
    return candidate


# --------------------------------------------------------------------------
# mode: split（出力ディレクトリ + 索引）
# --------------------------------------------------------------------------
_SPLIT_STR_KEYS = ("template", "index_path", "source_dir", "source_key")
_SPLIT_INT_KEYS = ("max_bytes", "min_bytes")


def split_settings(out: dict) -> dict:
    """mode: split のエントリの設定を検証して返す。"""
    rel = out.get("path")
    parts = [p for p in rel.split("/") if p] if isinstance(rel, str) else []
    if not isinstance(rel, str) or not rel.endswith("/") or len(parts) < 2 or ".." in parts:
        raise genlib.YamlError(
            f"mode: split の path は、深さ2以上のディレクトリ（末尾 /）で指定してください: {rel!r}"
        )
    for key in _SPLIT_STR_KEYS:
        if not isinstance(out.get(key), str) or not out[key]:
            raise genlib.YamlError(f"mode: split の {key} は非空文字列が必要です ({rel})")
    for key in _SPLIT_INT_KEYS:
        value = out.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise genlib.YamlError(f"mode: split の {key} は整数が必要です ({rel})")
    check = out.get("placeholder_check")
    if check is not None:
        if not isinstance(check, dict) or not all(
            isinstance(check.get(k), str) and check.get(k) for k in ("path", "heading")
        ):
            raise genlib.YamlError(f"mode: split の placeholder_check は path と heading が必要です ({rel})")
    index_parts = [p for p in out["index_path"].split("/") if p]
    if index_parts[: len(parts)] == parts:
        raise genlib.YamlError(f"mode: split の index_path が出力ディレクトリの内側です ({rel})")
    return {
        "path": rel,
        "template": out["template"],
        "index_path": out["index_path"],
        "source_dir": out["source_dir"],
        "source_key": out["source_key"],
        "max_bytes": out["max_bytes"],
        "min_bytes": out["min_bytes"],
        "placeholder_check": check,
    }


def split_build(root: str, out: dict, manifest: dict) -> tuple:
    """(設定, ソースの相対パス, SplitResult) を返す。入力が契約外なら YamlError / RenderError / SplitError。"""
    cfg = split_settings(out)
    name = genlib._resolve_path(manifest, cfg["source_key"])
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or not name.endswith(".md"):
        raise genlib.YamlError(
            f"{cfg['source_key']} は basename の .md ファイル名が必要です: {name!r}"
        )
    source_rel = cfg["source_dir"].rstrip("/") + "/" + name
    source_abs = _safe_join(root, source_rel, "outputs[].source_dir")
    text = _read(source_abs)
    if text is None:
        raise genlib.YamlError(f"mode: split のソースが存在しません: {source_rel}")
    return cfg, source_rel, splitlib.build(text, source_rel, cfg["max_bytes"], cfg["min_bytes"])


def split_dir_names(dir_abs: str) -> list:
    """出力ディレクトリ直下のファイル名を返す。symlink と下位ディレクトリがあれば YamlError（削除を拒否する）。"""
    if not os.path.lexists(dir_abs):
        return []
    if os.path.islink(dir_abs) or not os.path.isdir(dir_abs):
        raise genlib.YamlError(f"mode: split の出力先がディレクトリではありません: {dir_abs}")
    names = []
    for entry in sorted(os.listdir(dir_abs)):
        path = os.path.join(dir_abs, entry)
        if os.path.islink(path):
            raise genlib.YamlError(f"mode: split の出力ディレクトリに symlink があります: {path}")
        if os.path.isdir(path):
            raise genlib.YamlError(f"mode: split の出力ディレクトリに下位ディレクトリがあります（削除しません）: {path}")
        names.append(entry)
    return names


def split_index_context(manifest: dict, result) -> dict:
    """索引テンプレートの描画用に、manifest の複製へ一時キー `_split` を足す（manifest は変更しない）。"""
    ctx = dict(manifest)
    ctx["_split"] = result.ctx
    return ctx


def _run_split_entry(root: str, rel: str, target_dir: str, template_text: str,
                     manifest: dict, split: tuple, check: bool,
                     changed: list, written: list, skipped: list,
                     permission_errors: list) -> int:
    cfg, _source_rel, result = split
    index_abs = _safe_join(root, cfg["index_path"], "outputs[].index_path")
    expected_index = genlib.render(template_text, split_index_context(manifest, result))
    existing_names = split_dir_names(target_dir)
    to_write = [
        name for name in result.order
        if _read(os.path.join(target_dir, name)) != result.files[name]
    ]
    to_delete = [name for name in existing_names if name not in result.files]
    index_changed = _read(index_abs) != expected_index
    for level, message in result.problems:
        print(f"{'WARN' if level == splitlib.LEVEL_WARN else 'ERROR'}(split {rel}): {message}")
    if check:
        if to_write or to_delete or index_changed:
            why = "新規作成" if not existing_names and _read(index_abs) is None else (
                f"差分あり（書込 {len(to_write)} / 削除 {len(to_delete)} / 索引 {'差分' if index_changed else '一致'}）"
            )
            changed.append((rel, why))
        return 0
    if not (to_write or to_delete or index_changed):
        skipped.append(rel)
        return 0
    try:
        for name in to_write:
            _write(os.path.join(target_dir, name), result.files[name], False)
        for name in to_delete:
            os.unlink(os.path.join(target_dir, name))
        if index_changed:
            _write(index_abs, expected_index, False)
    except PermissionError as exc:
        permission_errors.append((rel, exc))
        return 0
    written.append((rel, f"split: 書込 {len(to_write)} / 削除 {len(to_delete)} / 索引 {'更新' if index_changed else '一致'}"))
    return 0


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
    skipped = []
    permission_errors = []

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

    # `_split`（分割と索引の描画用データ）は、同じ実行内の全テンプレートへ渡す。
    # 例: seed のテンプレートが、正本のプレースホルダの記入欄を `_split.placeholders` から作る。
    # manifest は変更しない（複製に一時キーを足す）。
    render_ctx = split_index_context(manifest, next(iter(split_state.values()))[2]) if split_state else manifest

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

        if mode == "split":
            template_text = _read(template_path)
            if template_text is None:
                print(f"FATAL: テンプレート不在: {template_path}", file=sys.stderr)
                return 2
            try:
                _run_split_entry(
                    root, rel, target_path, template_text, manifest,
                    split_state[rel], check, changed, written, skipped, permission_errors,
                )
            except (genlib.YamlError, genlib.RenderError) as e:
                print(f"FATAL: mode: split の処理失敗 ({rel}): {e}", file=sys.stderr)
                return 2
            continue

        if mode == "seed" and existing is not None:
            skipped.append(rel)
            continue

        template_text = _read(template_path)
        if template_text is None:
            print(f"FATAL: テンプレート不在: {template_path}", file=sys.stderr)
            return 2
        try:
            expected = expected_content(
                out, render_ctx, target_path, template_text, marker_id
            )
        except genlib.RenderError as e:
            print(f"FATAL: 描画失敗 ({rel}): {e}", file=sys.stderr)
            return 2

        if check:
            if existing != expected:
                changed.append((rel, "新規作成" if existing is None else "差分あり"))
            continue

        executable = bool(out.get("executable"))
        if existing == expected:
            if executable:
                try:
                    current_mode = os.stat(target_path).st_mode
                    if current_mode & EXECUTABLE_BITS != EXECUTABLE_BITS:
                        os.chmod(target_path, current_mode | EXECUTABLE_BITS)
                        written.append((rel, "chmod"))
                    else:
                        skipped.append(rel)
                except PermissionError as exc:
                    permission_errors.append((rel, exc))
            else:
                skipped.append(rel)
            continue

        try:
            _write(target_path, expected, executable)
        except PermissionError as exc:
            permission_errors.append((rel, exc))
        else:
            written.append((rel, mode))

    if check:
        if changed:
            print("冪等性ドライラン: 再生成が必要な出力あり")
            for rel, why in changed:
                print(f"  [{why}] {rel}")
            return 1
        print(f"冪等性ドライラン: 全 {len(outputs)} 出力が最新（差分なし）")
        return 0

    if permission_errors:
        for rel, exc in permission_errors:
            print(
                f"FATAL: 出力パスへの権限拒否 ({rel}): {exc}。"
                "差分がある出力だけ権限昇格して再実行してください。",
                file=sys.stderr,
            )
        return 2

    print(
        f"生成完了: {len(written)} 出力 / {len(skipped)} スキップ "
        f"(marker_id={marker_id}, root={root})"
    )
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
