#!/usr/bin/env python3
"""generate.py — 設定スキルの manifest.yaml + templates/ から出力ファイルを決定論生成する。

使い方:
  python3 generate.py --skill-dir <config-skill-dir>           # 生成（出力をリポジトリへ書き出す）
  python3 generate.py --skill-dir <config-skill-dir> --check   # 冪等性ドライラン（書き込まない）

出力モード（manifest.yaml > outputs[].mode）:
  render : テンプレート全展開でファイルを丸ごと生成（直接編集は drift）
  marker : `marker_id` のマーカーブロックを既存ファイルへ upsert（ブロック外は不可侵）
  seed   : 不在時のみ初期生成。既存ファイルは上書きしない（DECISIONS/GOTCHAS 等の追記ログ）。
           outputs[].pristine_drop_keys があるときだけ、指定キーを除いて描画した
           「投影なしスケルトン」を基準に、既存ファイルを次の順で扱う。
             1. 既存 == 投影あり描画 → 何もしない。
             2. 既存 == 投影なしスケルトン → ファイル全体を投影あり描画へ置換する。
             3. それ以外 → 構造節マージ。構造節は、投影なしスケルトンの `## ` 見出し
                （コードフェンス外）を出現順に境界とした「見出し行から次の構造見出し
                直前まで」のバイト列である。本文が投影なしスケルトンのまま残っている
                節だけを投影あり描画の節へ置換し、手で書いた節と前文は保持する。
                構造見出しが既存ファイルから順に見つからないときは、そのファイルを
                変更せず `見出し構成不一致` を報告する。
           既知の制約: 投影だけが出す追加見出し（投影本文中の `##` や条件付き節）は
           構造境界にならず、直前の構造節の本文に含まれる。その塊は、直前の節が
           置換されるときだけ挿入される。節境界に管理マーカーは使わない。

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


EXECUTABLE_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_STRUCTURAL_HEADING_RE = re.compile(r"^##[ \t]+\S")


class SectionMismatch(Exception):
    """構造見出しが対象テキストから順に見つからない（節マージ不可）。"""

    def __init__(self, heading: str, where: str):
        self.heading = heading
        self.where = where
        super().__init__(f"構造見出し {heading!r} が {where} に見つかりません")


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


def merge_seed_sections(
    existing: str, pristine: str, expected: str
) -> tuple[str, list[str]]:
    """投影なしスケルトンのまま残る構造節だけを、投影あり描画の節へ置換する。

    戻り値は (マージ結果, 置換した構造見出しのリスト)。手で書いた節と前文は保持する。
    構造見出しが既存・投影なし・投影ありのいずれかから順に見つからないときは
    SectionMismatch を送出する。
    """
    headings = structural_headings(pristine)
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
            drop_keys = out.get("pristine_drop_keys") or []
            if not drop_keys:
                skipped.append(rel)
                continue
            template_text = _read(template_path)
            if template_text is None:
                print(f"FATAL: テンプレート不在: {template_path}", file=sys.stderr)
                return 2
            pristine_manifest = {
                key: value for key, value in manifest.items() if key not in drop_keys
            }
            try:
                expected = expected_content(
                    out, manifest, target_path, template_text, marker_id
                )
                pristine = genlib.render(template_text, pristine_manifest)
            except genlib.RenderError as e:
                print(f"FATAL: 描画失敗 ({rel}): {e}", file=sys.stderr)
                return 2
            if existing == expected:
                skipped.append(rel)
                continue
            if existing == pristine:
                # 投影なしスケルトンそのもの: 見出しの有無によらずファイル全体を置換する。
                new_content = expected
                replaced_labels = [(rel, "pristine置換")]
            else:
                try:
                    new_content, replaced = merge_seed_sections(existing, pristine, expected)
                except SectionMismatch as e:
                    print(f"見出し構成不一致: {rel}（{e}。ファイルは変更しません）")
                    skipped.append(rel)
                    continue
                if new_content == existing:
                    skipped.append(rel)
                    continue
                replaced_labels = [
                    (f"{rel}#{heading.lstrip('#').strip()}", "section置換")
                    for heading in replaced
                ]
            if check:
                changed.extend((label, why) for label, why in replaced_labels)
                continue
            try:
                _write(target_path, new_content, bool(out.get("executable")))
            except PermissionError as exc:
                permission_errors.append((rel, exc))
            else:
                written.append((rel, replaced_labels[0][1]))
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
