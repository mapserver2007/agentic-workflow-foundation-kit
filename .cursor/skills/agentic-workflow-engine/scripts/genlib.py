#!/usr/bin/env python3
"""genlib.py — agentic workflow 基盤の生成/監査エンジン共有ライブラリ。

責務（How エンジンの土台）:
  - 最小 YAML サブセットのローダ（`load_manifest`）— PyYAML 非依存（標準ライブラリのみ）
  - テンプレート描画（`render`）— `{{path}}` スカラ展開、`{{#if}}…{{else}}…{{/if}}` 条件分岐、`{{#each}}…{{/each}}` ブロック反復
  - fingerprint（`sha256_file`）/ スキル・リポジトリルートのパス解決
  - 例外（`YamlError` / `RenderError`）

`generate.py` / `audit.py`（および設定スキル固有スクリプト）はすべて本モジュールを
共有し、同一の解析・描画ロジックで決定論性を担保する。

対応する YAML サブセット（manifest.yaml はこの範囲で記述する）:
  - block style のみ（flow `{}` / `[]` 不可）
  - インデントは半角スペース2
  - スカラ: 文字列（裸 / `"..."` / `'...'`）・整数・真偽値（true/false）
  - マッピング（`key: value` / ネスト）/ シーケンス（`- item` / `- key: value`）
  - 行頭・行中（` #`）コメント / 空行
  - 複数行ブロックスカラ（`|`）はサポート対象外（現行 manifest は不使用）

テンプレート構文:
  - `{{ dotted.path }}`           : マニフェスト上のスカラを文字列展開
  - `{{#if dotted.path}} … {{else}} … {{/if}}` : 条件分岐（ネスト可）。
        パスの値が truthy（非 None / 非 False / 非空リスト / 非空文字列）なら
        if ブロックを、そうでなければ else ブロック（省略可）を展開する
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
# project 継承（inherits_project）
# --------------------------------------------------------------------------
def deep_merge(base, override):
    """base に override を再帰マージして新しい値を返す（override 優先）。

    両者が dict のときのみ再帰的にキー単位でマージし、それ以外（スカラ / リスト）は
    override の値で置換する。リストはマージせず置換（設定の意図を素直に反映）。
    """
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = deep_merge(result[key], value) if key in result else value
        return result
    return override


def apply_inherited_project(manifest: dict, skill_dir: str) -> dict:
    """`inherits_project` があれば親 manifest の `project` を子へマージした manifest を返す。

    - `inherits_project` はリポジトリルートからの親設定スキルディレクトリの相対パス。
    - 共有 SoT は親の `project.*`、子の `project.*` が上書き（子優先 deep-merge）。
    - `inherits_project` がなければ manifest をそのまま返す（非破壊）。
    親 manifest が読めない場合は `YamlError` を送出する（呼び出し側で exit 2 とする）。
    """
    parent_rel = manifest.get("inherits_project")
    if not parent_rel:
        return manifest
    root = root_from_skill_dir(skill_dir)
    parent_manifest_path = os.path.join(root, parent_rel, "manifest.yaml")
    parent = load_manifest(parent_manifest_path)
    parent_project = parent.get("project") or {}
    child_project = manifest.get("project") or {}
    merged = dict(manifest)
    merged["project"] = deep_merge(parent_project, child_project)
    return merged


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
    """(indent, content) のリストへ。空行・コメントのみの行は捨てる。
    `|` ブロックリテラルは後続のインデントされた行群を結合してスカラー値に変換する。
    """
    raw_lines = text.split("\n")
    tokens = []
    i = 0
    while i < len(raw_lines):
        line = _strip_inline_comment(raw_lines[i])
        if line.strip() == "":
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        # `|` ブロックリテラル検出: "key: |" パターン
        if content.endswith(": |") or content == "|":
            block_indent = None
            block_lines = []
            j = i + 1
            while j < len(raw_lines):
                bline = raw_lines[j]
                # 空行はブロック内の改行として保持
                if bline.strip() == "":
                    block_lines.append("")
                    j += 1
                    continue
                b_indent = len(bline) - len(bline.lstrip(" "))
                if block_indent is None:
                    if b_indent <= indent:
                        break
                    block_indent = b_indent
                if b_indent < block_indent:
                    break
                block_lines.append(bline[block_indent:])
                j += 1
            # 末尾の空行を除去
            while block_lines and block_lines[-1] == "":
                block_lines.pop()
            block_text = "\n".join(block_lines)
            if content.endswith(": |"):
                key_part = content[:-2].strip()
                tokens.append((indent, f"{key_part}: {_block_quote(block_text)}"))
            else:
                tokens.append((indent, _block_quote(block_text)))
            i = j
        else:
            tokens.append((indent, content))
            i += 1
    return tokens


def _block_quote(text: str) -> str:
    """ブロックリテラルテキストを内部表現（ダブルクォート付き）に変換する。"""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


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
_IF_OPEN_RE = re.compile(r"\{\{#if\s+([^\}]+?)\}\}")
# ブロックトークン（{{#if}} / {{else}} / {{/if}} / {{#each}} / {{/each}}）が
# 行内で単独（前後が空白のみ）の場合、その行の空白と改行を畳む
# （Handlebars の standalone 規則）。テンプレートはこの挙動を前提に記述されている
# （例: `{{/each}}- 次の項目` のように非単独行は畳まれない）。
_STANDALONE_RE = re.compile(
    r"(?m)^[ \t]*("
    r"\{\{#each\s+[^\}]+?\}\}|\{\{/each\}\}"
    r"|\{\{#if\s+[^\}]+?\}\}|\{\{else\}\}|\{\{/if\}\}"
    r")[ \t]*\r?\n"
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


def _is_truthy(value) -> bool:
    """Handlebars 互換の truthiness 判定。"""
    if value is None or value is False:
        return False
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, str):
        return len(value) > 0
    return True


def _process_ifs(text: str, root: dict) -> str:
    """{{#if path}}…{{else}}…{{/if}} ブロックを再帰的に展開する（ネスト対応）。"""
    while True:
        m = _IF_OPEN_RE.search(text)
        if not m:
            break
        path = m.group(1).strip()
        start = m.start()
        body_start = m.end()

        depth = 1
        pos = body_start
        else_pos = None
        endif_end = None
        while depth > 0 and pos < len(text):
            next_if = text.find("{{#if ", pos)
            next_endif = text.find("{{/if}}", pos)
            if next_endif == -1:
                raise RenderError(f"{{{{#if {path}}}}} に対応する {{{{/if}}}} がない")
            if depth == 1 and else_pos is None:
                next_else = text.find("{{else}}", pos)
                if next_else != -1 and next_else < next_endif and (next_if == -1 or next_else < next_if):
                    else_pos = next_else
            if next_if != -1 and next_if < next_endif:
                depth += 1
                pos = next_if + 6
                continue
            if depth == 1 and else_pos is None:
                next_else = text.find("{{else}}", pos)
                if next_else != -1 and next_else < next_endif:
                    else_pos = next_else
            depth -= 1
            if depth == 0:
                endif_end = next_endif + len("{{/if}}")
            else:
                pos = next_endif + len("{{/if}}")

        if endif_end is None:
            raise RenderError(f"{{{{#if {path}}}}} に対応する {{{{/if}}}} がない")

        try:
            value = _resolve_path(root, path)
            truthy = _is_truthy(value)
        except RenderError:
            truthy = False

        if else_pos is not None:
            if_body = text[body_start:else_pos]
            else_body = text[else_pos + len("{{else}}"):next_endif]
        else:
            if_body = text[body_start:next_endif]
            else_body = ""

        text = text[:start] + (if_body if truthy else else_body) + text[endif_end:]
    return text


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
    conditionals_resolved = _process_ifs(normalized, root)
    expanded = _EACH_RE.sub(each_sub, conditionals_resolved)
    return _render_scalars(expanded, root, item=None, index=None)
