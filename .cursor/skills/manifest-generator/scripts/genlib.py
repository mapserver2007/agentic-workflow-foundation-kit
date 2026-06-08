#!/usr/bin/env python3
"""genlib.py — agentic workflow 基盤の生成/監査エンジン共有ライブラリ。

責務（How エンジンの土台）:
  - 最小 YAML サブセットのローダ（`load_manifest`）— PyYAML 非依存（標準ライブラリのみ）
  - テンプレート描画（`render`）— `{{path}}` スカラ展開と `{{#each}}…{{/each}}` ブロック反復
  - fingerprint（`sha256_file`）/ スキル・リポジトリルートのパス解決
  - 例外（`YamlError` / `RenderError`）

`generate.py` / `audit.py` / `check_design_drift.py` はすべて本モジュールを共有し、
同一の解析・描画ロジックで決定論性を担保する。

対応する YAML サブセット（manifest.yaml はこの範囲で記述する）:
  - block style のみ（flow `{}` / `[]` 不可）
  - インデントは半角スペース2
  - スカラ: 文字列（裸 / `"..."` / `'...'`）・整数・真偽値（true/false）
  - マッピング（`key: value` / ネスト）/ シーケンス（`- item` / `- key: value`）
  - 行頭・行中（` #`）コメント / 空行
  - 複数行ブロックスカラ（`|`）はサポート対象外（現行 manifest は不使用）

テンプレート構文:
  - `{{ dotted.path }}`           : マニフェスト上のスカラを文字列展開
  - `{{#each dotted.path}} … {{/each}}` : リストを反復（ネスト不可）。本体で
        `{{this}}`（スカラ要素） / `{{this.field}}`（マップ要素のフィールド） /
        `{{@index}}`（1始まりの連番）が使える
  - 二重括弧 `{{ }}` のみ置換対象。bash の `${...}` や JSON の単一 `{ }` は温存する
"""
from __future__ import annotations

import hashlib
import os
import re


class YamlError(Exception):
    """manifest.yaml の解析失敗。"""


class RenderError(Exception):
    """テンプレート描画時の未解決参照・構文エラー。"""


# --------------------------------------------------------------------------
# パス解決 / fingerprint
# --------------------------------------------------------------------------
def sha256_file(path: str) -> str:
    """ファイル内容の sha256 16進ダイジェストを返す。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def skill_dir_of(file_path: str) -> str:
    """`<skill>/scripts/<x>.py` の `__file__` から `<skill>` ディレクトリを返す。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(file_path)))


def root_from_skill_dir(skill_dir: str) -> str:
    """`<root>/.cursor/skills/<name>` からリポジトリルート `<root>` を返す。"""
    skill_dir = os.path.abspath(skill_dir)
    return os.path.dirname(os.path.dirname(os.path.dirname(skill_dir)))


# --------------------------------------------------------------------------
# 最小 YAML ローダ
# --------------------------------------------------------------------------
_MAPPING_RE = re.compile(r"[^\s:#]+:(\s|$)")


def _strip_inline_comment(line: str) -> str:
    """引用符の外にある `#` 以降をコメントとして除去する（行頭コメント含む）。"""
    out = []
    quote = None
    prev = ""
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        else:
            if ch in ('"', "'"):
                quote = ch
                out.append(ch)
            elif ch == "#" and (prev == "" or prev.isspace()):
                break
            else:
                out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def _tokenize(text: str):
    """(indent, content) のリストへ。空行・コメントのみの行は捨てる。"""
    tokens = []
    for raw in text.split("\n"):
        line = _strip_inline_comment(raw)
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip(" "))
        tokens.append((indent, line.strip()))
    return tokens


def _unquote(s: str) -> str:
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def _parse_scalar(val: str):
    if val == "" or val in ("null", "~"):
        return None
    if val in ("true", "false"):
        return val == "true"
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    return _unquote(val)


def _split_kv(content: str):
    idx = content.find(":")
    if idx == -1:
        return content, "", False
    key = _unquote(content[:idx].strip())
    val = content[idx + 1:].strip()
    return key, val, True


def _looks_like_mapping(inner: str) -> bool:
    if not inner:
        return False
    if inner[0] in ('"', "'"):
        return False
    return bool(_MAPPING_RE.match(inner))


def _parse_node(tokens, i, indent):
    content = tokens[i][1]
    if content == "-" or content.startswith("- "):
        return _parse_seq(tokens, i, indent)
    return _parse_map(tokens, i, indent)


def _parse_map(tokens, i, indent):
    result = {}
    n = len(tokens)
    while i < n:
        ind, content = tokens[i]
        if ind != indent:
            if ind < indent:
                break
            raise YamlError(f"予期しないインデント {ind}: {content!r}")
        key, val, has = _split_kv(content)
        if not has:
            raise YamlError(f"マッピングを期待: {content!r}")
        if val != "":
            result[key] = _parse_scalar(val)
            i += 1
        elif i + 1 < n and tokens[i + 1][0] > indent:
            child, i = _parse_node(tokens, i + 1, tokens[i + 1][0])
            result[key] = child
        else:
            result[key] = None
            i += 1
    return result, i


def _parse_seq(tokens, i, indent):
    items = []
    n = len(tokens)
    while i < n:
        ind, content = tokens[i]
        if ind != indent or not (content == "-" or content.startswith("- ")):
            break
        after = content[1:]
        spaces = len(after) - len(after.lstrip(" "))
        inner = after.lstrip(" ")
        content_indent = indent + 1 + spaces
        if inner == "":
            if i + 1 < n and tokens[i + 1][0] > indent:
                child, i = _parse_node(tokens, i + 1, tokens[i + 1][0])
                items.append(child)
            else:
                items.append(None)
                i += 1
        elif _looks_like_mapping(inner):
            sub = [(content_indent, inner)]
            j = i + 1
            while j < n and tokens[j][0] >= content_indent:
                sub.append(tokens[j])
                j += 1
            child, _ = _parse_map(sub, 0, content_indent)
            items.append(child)
            i = j
        else:
            items.append(_parse_scalar(inner))
            i += 1
    return items, i


def parse_yaml(text: str):
    tokens = _tokenize(text)
    if not tokens:
        return {}
    node, _ = _parse_node(tokens, 0, tokens[0][0])
    return node


def load_manifest(path: str) -> dict:
    """manifest.yaml を読み込み dict を返す。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise YamlError(f"manifest 読込失敗: {path}: {e}") from e
    try:
        data = parse_yaml(text)
    except YamlError:
        raise
    except Exception as e:  # noqa: BLE001
        raise YamlError(f"manifest 解析失敗: {path}: {e}") from e
    if not isinstance(data, dict):
        raise YamlError(f"manifest のトップレベルがマッピングでない: {path}")
    return data


# --------------------------------------------------------------------------
# テンプレート描画
# --------------------------------------------------------------------------
_EACH_RE = re.compile(r"\{\{#each\s+([^\}]+?)\}\}(.*?)\{\{/each\}\}", re.DOTALL)
_VAR_RE = re.compile(r"\{\{\s*([^\}]+?)\s*\}\}")
# ブロックトークン（{{#each}} / {{/each}}）が行内で単独（前後が空白のみ）の場合、
# その行の空白と改行を畳む（Handlebars の standalone 規則）。テンプレートはこの挙動を
# 前提に記述されている（例: `{{/each}}- 次の項目` のように非単独行は畳まれない）。
_STANDALONE_RE = re.compile(
    r"(?m)^[ \t]*(\{\{#each\s+[^\}]+?\}\}|\{\{/each\}\})[ \t]*\r?\n"
)


def _scalar_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _resolve_path(root: dict, path: str):
    cur = root
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise RenderError(f"未解決の参照: {path}")
    return cur


def _render_scalars(text: str, root: dict, item=None, index=None) -> str:
    def sub(m):
        expr = m.group(1).strip()
        if expr.startswith("#") or expr.startswith("/"):
            return m.group(0)
        if expr == "this":
            return _scalar_str(item)
        if expr.startswith("this."):
            cur = item
            for part in expr[5:].split("."):
                if not isinstance(cur, dict) or part not in cur:
                    raise RenderError(f"未解決の参照: {expr}")
                cur = cur[part]
            return _scalar_str(cur)
        if expr == "@index":
            if index is None:
                raise RenderError("@index は #each ブロック外では使用できない")
            return str(index)
        return _scalar_str(_resolve_path(root, expr))

    return _VAR_RE.sub(sub, text)


def render(text: str, root: dict) -> str:
    """テンプレート文字列を manifest dict で描画する。"""

    def each_sub(m):
        path = m.group(1).strip()
        body = m.group(2)
        items = _resolve_path(root, path)
        if items is None:
            items = []
        if not isinstance(items, list):
            raise RenderError(f"#each の対象がリストでない: {path}")
        return "".join(
            _render_scalars(body, root, item=item, index=idx + 1)
            for idx, item in enumerate(items)
        )

    normalized = _STANDALONE_RE.sub(lambda m: m.group(1), text)
    expanded = _EACH_RE.sub(each_sub, normalized)
    return _render_scalars(expanded, root, item=None, index=None)
