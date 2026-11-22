#!/usr/bin/env python3
"""splitlib.py — `mode: split` の分割と索引の計算（generate.py と audit.py が共有する）。

責務:
  - Markdown の正本（frontmatter 付き）を、コードフェンスの外の見出し単位で機械的に分割する。
    人や LLM の判断を挟まず、本文は逐語のまま出力する（`{{...}}` も加工しない）。
  - 分割ファイル、索引の描画用データ（`_split`）、書式契約の違反・警告を返す。

generate.py と audit.py は同じ `build()` を呼ぶ。決定論性は、この1つの実装の共有で担保する。
標準ライブラリのみ（Python 3.9 以上）。

分割アルゴリズム（構造だけで決める。節番号と内容に依存しない）:
  1. フェンスの外の見出しだけを解析する。番号ではなく見出しレベルを使う。
  2. 再帰的に分割する。節の合計サイズが上限以下ならその節を1ファイルにする。
     上限を超えるなら、1段深い見出しで分ける。
  3. 本文が下限未満の親節は、先頭の子に結合する。
  4. 下限未満の小さな兄弟節は、同じ親の隣の節と結合する（結合後が上限以下のときだけ）。
  5. 末端節が1つで上限を超える場合は、途中で切らない。違反として報告する。
"""
from __future__ import annotations

import re

SUPPORTED_HEADER_FORMAT = "<!-- split {n:02d}/{total:02d} of {source} (generated; do not edit) -->"
HEADER_RE = re.compile(r"^<!-- split \d+/\d+ of \S+ \(generated; do not edit\) -->$")

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(\S.*?)[ \t]*$")
_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*[a-z]?)\.?(?=\s|$)")
_TITLE_NUM_RE = re.compile(r"^\d+(?:\.\d+)*[a-z]?\.?\s*")
REF_RE = re.compile(r"§(\d+(?:\.\d+)*[a-z]?)")
_RANGE_RE = re.compile(r"§\d+(?:\.\d+)*[a-z]?\s*[〜~–—-]\s*§?\d")
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\n]+\}\}")
INDEX_HEADER_CELLS = ("タスク種別", "必読節")
ALWAYS_ROW_NAME = "常時"

LEVEL_FAIL = "fail"
LEVEL_WARN = "warn"


class SplitError(Exception):
    """入力・設定が契約外で、分割を作れない（致命的）。"""


# --------------------------------------------------------------------------
# 行・frontmatter・見出し
# --------------------------------------------------------------------------
def split_lines(text: str) -> list:
    """改行を含めたまま行に分ける（連結すると元のテキストに戻る。`\\n` だけを区切りにする）。"""
    return re.findall(r"[^\n]*\n|[^\n]+", text)


def parse_frontmatter(lines: list) -> tuple:
    """先頭の `---` で囲まれた frontmatter を (dict, 本文の開始行) で返す。無ければ ({}, 0)。"""
    if not lines or lines[0].rstrip("\r\n").strip() != "---":
        return {}, 0
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n").strip() == "---":
            meta = {}
            for raw in lines[1:i]:
                line = raw.rstrip("\r\n")
                if ":" not in line or line.startswith((" ", "\t", "#", "-")):
                    continue
                key, value = line.split(":", 1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                meta[key.strip()] = value
            return meta, i + 1
    return {}, 0


def _headings(lines: list, body_start: int) -> list:
    """フェンスの外の見出しを (行番号, レベル, 見出しテキスト) で返す。"""
    out = []
    fence = None
    for i in range(body_start, len(lines)):
        line = lines[i].rstrip("\r\n")
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                continue
        else:
            stripped = line.strip()
            if m and stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                fence = None
            continue
        h = _HEADING_RE.match(line)
        if h:
            out.append((i, len(h.group(1)), h.group(2)))
    return out


class Node:
    def __init__(self, level: int, title: str, start: int):
        self.level = level
        self.title = title
        self.start = start
        self.end = 0
        self.own_end = 0
        self.children = []
        self.parent = None
        m = _NUM_RE.match(title)
        self.num = m.group(1) if m else None


def parse_nodes(lines: list, body_start: int) -> list:
    nodes = []
    root = Node(0, "<root>", body_start)
    stack = [root]
    for (i, lvl, title) in _headings(lines, body_start):
        node = Node(lvl, title, i)
        while stack and stack[-1].level >= lvl:
            stack.pop()
        node.parent = stack[-1]
        stack[-1].children.append(node)
        stack.append(node)
        nodes.append(node)
    for k, node in enumerate(nodes):
        node.end = len(lines)
        for later in nodes[k + 1:]:
            if later.level <= node.level:
                node.end = later.start
                break
        node.own_end = node.children[0].start if node.children else node.end
    return nodes


def _byte_size(chunk_lines: list) -> int:
    return len("".join(chunk_lines).encode("utf-8"))


# --------------------------------------------------------------------------
# 分割
# --------------------------------------------------------------------------
class Chunk:
    def __init__(self, line_idx: list, nodes: list, mergeable: bool = True):
        self.line_idx = list(line_idx)  # 本文の行番号（連続）
        self.nodes = list(nodes)
        self.mergeable = mergeable

    def size(self, lines: list) -> int:
        return _byte_size([lines[i] for i in self.line_idx])


def _range(a: int, b: int) -> list:
    return list(range(a, b))


def _split(node: Node, lines: list, max_bytes: int, min_bytes: int, violations: list) -> list:
    whole = _range(node.start, node.end)
    if _byte_size([lines[i] for i in whole]) <= max_bytes:
        return [Chunk(whole, [node])]
    if not node.children:
        violations.append((node.title, _byte_size([lines[i] for i in whole]), "leaf_over_max"))
        return [Chunk(whole, [node], mergeable=False)]
    pre = Chunk(_range(node.start, node.own_end), [node])
    items = []
    for child in node.children:
        child_chunks = _split(child, lines, max_bytes, min_bytes, violations)
        single = len(child_chunks) == 1
        for ch in child_chunks:
            ch.mergeable = single and ch.mergeable
            items.append(ch)
    if pre.size(lines) < min_bytes:
        first = items[0]
        first.line_idx = pre.line_idx + first.line_idx
        first.nodes = pre.nodes + first.nodes
        if first.size(lines) > max_bytes:
            violations.append((node.title, first.size(lines), "preamble_merge_over_max"))
    else:
        if pre.size(lines) > max_bytes:
            violations.append((node.title, pre.size(lines), "preamble_over_max"))
        items.insert(0, pre)
    out = []
    cur = None
    for item in items:
        if cur is None:
            cur = item
            continue
        small = cur.size(lines) < min_bytes or item.size(lines) < min_bytes
        if cur.mergeable and item.mergeable and small and cur.size(lines) + item.size(lines) <= max_bytes:
            cur.line_idx += item.line_idx
            cur.nodes += item.nodes
        else:
            out.append(cur)
            cur = item
    if cur is not None:
        out.append(cur)
    return out


def _slug(chunk: Chunk, index: int) -> str:
    for node in chunk.nodes:
        if node.num:
            return "s" + node.num.replace(".", "-")
    return "intro" if index == 0 else "x"


# --------------------------------------------------------------------------
# 索引表・参照・プレースホルダ
# --------------------------------------------------------------------------
def _in_table(lines: list, body_start: int) -> tuple:
    """索引表（ヘッダ行の先頭2セルが「タスク種別」「必読節」）の (開始行, 終了行, 行リスト)。無ければ (None, None, [])。"""
    fence = None
    for i in range(body_start, len(lines)):
        line = lines[i].rstrip("\r\n")
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                continue
        else:
            stripped = line.strip()
            if m and stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                fence = None
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if tuple(cells[:2]) != INDEX_HEADER_CELLS:
            continue
        rows = []
        j = i + 2  # ヘッダ行と区切り行の次から
        while j < len(lines) and lines[j].startswith("|"):
            rows.append([c.strip() for c in lines[j].rstrip("\r\n").strip().strip("|").split("|")])
            j += 1
        return i, j, rows
    return None, None, []


def _covered(node_by_num: dict, num: str, listed: list) -> bool:
    """節 num が、listed の節またはその子孫に含まれるか（見出しの階層で判定する）。"""
    node = node_by_num.get(num)
    if node is None:
        return False
    listed_nodes = {id(node_by_num[s]) for s in listed if s in node_by_num}
    cur = node
    while cur is not None:
        if id(cur) in listed_nodes:
            return True
        cur = cur.parent
    return False


def _own_text(lines: list, node: Node, skip: tuple) -> str:
    out = []
    for k in range(node.start, node.own_end):
        if skip[0] is not None and skip[0] <= k < skip[1]:
            continue
        out.append(lines[k])
    return "".join(out)


def _subtree_text(lines: list, node: Node, skip: tuple) -> str:
    out = []
    for k in range(node.start, node.end):
        if skip[0] is not None and skip[0] <= k < skip[1]:
            continue
        out.append(lines[k])
    return "".join(out)


def _compact_numbers(numbers: list) -> str:
    nums = sorted(set(numbers))
    parts = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"{nums[i]:02d}-{nums[j]:02d}")
        else:
            parts.extend(f"{n:02d}" for n in nums[i:j + 1])
        i = j + 1
    return ",".join(parts)


# --------------------------------------------------------------------------
# 結果
# --------------------------------------------------------------------------
class SplitResult:
    def __init__(self):
        self.files = {}  # ファイル名 -> 内容（ヘッダ行を含む）
        self.order = []  # ファイル名の出現順
        self.body = ""  # 連結の期待値（frontmatter と先頭の空行を除いた本文）
        self.violations = []  # (見出し, バイト数, 種別)
        self.problems = []  # (レベル, メッセージ)
        self.placeholders = []  # `{{...}}` の一覧（出現順）
        self.ctx = {}  # 索引テンプレートへ渡す `_split`


def build(text: str, source_rel: str, max_bytes: int, min_bytes: int) -> SplitResult:
    """正本のテキストから、分割ファイルと索引の描画用データを作る（決定論）。"""
    if max_bytes <= 0 or min_bytes < 0 or min_bytes >= max_bytes:
        raise SplitError(f"サイズの上限・下限が不正です: max={max_bytes} min={min_bytes}")
    lines = split_lines(text)
    meta, body_start = parse_frontmatter(lines)
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    result = SplitResult()
    result.body = "".join(lines[body_start:])
    nodes = parse_nodes(lines, body_start)
    if not nodes:
        raise SplitError("見出しが1つもありません。分割できません")
    top = [n for n in nodes if n.parent is not None and n.parent.level == 0]
    chunks = []
    for node in top:
        chunks.extend(_split(node, lines, max_bytes, min_bytes, result.violations))
    # 先頭の見出しより前の本文（空行を除く）は、最初のチャンクの先頭へ付ける
    if nodes[0].start > body_start and chunks:
        chunks[0].line_idx = _range(body_start, nodes[0].start) + chunks[0].line_idx

    total = len(chunks)
    width = max(2, len(str(total)))
    names = []
    for index, chunk in enumerate(chunks):
        names.append(f"{index + 1:0{width}d}_{_slug(chunk, index)}.md")
    for index, chunk in enumerate(chunks):
        header = SUPPORTED_HEADER_FORMAT.format(n=index + 1, total=total, source=source_rel)
        content = header + "\n\n" + "".join(lines[i] for i in chunk.line_idx)
        result.files[names[index]] = content
        result.order.append(names[index])

    node_by_num = {}
    for node in nodes:
        if node.num and node.num not in node_by_num:
            node_by_num[node.num] = node
    tbl_start, tbl_end, rows = _in_table(lines, body_start)
    skip = (tbl_start, tbl_end)

    bounds = [(ch.line_idx[0], ch.line_idx[-1] + 1) for ch in chunks]

    def chunk_idx_for(node: Node) -> set:
        """節（見出しと、子の節すべて）の行範囲と重なるチャンクの添字。"""
        return {i for i, (lo, hi) in enumerate(bounds) if lo < node.end and hi > node.start}

    def chunk_of_heading(node: Node) -> int:
        """節の見出し行を含むチャンクの添字。"""
        for i, (lo, hi) in enumerate(bounds):
            if lo <= node.start < hi:
                return i
        return -1

    # --- 参照切れ ---
    unresolved = set()
    for node in nodes:
        for ref in REF_RE.findall(_own_text(lines, node, skip)):
            if ref not in node_by_num:
                unresolved.add(ref)
    if unresolved:
        result.problems.append((LEVEL_FAIL, "存在しない節への § 参照: " + ", ".join("§" + r for r in sorted(unresolved))))
    ranges = [m.group(0) for m in _RANGE_RE.finditer(result.body)]
    if ranges:
        result.problems.append((LEVEL_WARN, "範囲指定の § 参照は契約外の書式です: " + ", ".join(sorted(set(ranges)))))
    unnumbered = [n.title for n in nodes if n.level >= 2 and not n.num]
    if unnumbered:
        result.problems.append((LEVEL_WARN, "節番号のない見出し（参照できません）: " + ", ".join(unnumbered)))

    # --- 違反 ---
    for title, size, kind in result.violations:
        result.problems.append((LEVEL_FAIL, f"サイズ上限を超える節: {title}（{size} バイト、上限 {max_bytes}）。ブループリントで節を分けてください [{kind}]"))

    # --- 索引表 ---
    tasks = []
    covered_files = set()
    if tbl_start is None:
        result.problems.append((LEVEL_FAIL, "索引表（ヘッダ行が「タスク種別」「必読節」の Markdown 表）がありません"))
    else:
        for cells in rows:
            if len(cells) < 2:
                result.problems.append((LEVEL_FAIL, f"索引表の行が不正です: {cells}"))
                continue
            name = cells[0]
            starts = REF_RE.findall(cells[1])
            refs = REF_RE.findall(cells[2]) if len(cells) > 2 else []
            for s in starts + refs:
                if s not in node_by_num:
                    result.problems.append((LEVEL_FAIL, f"索引表の行「{name}」が存在しない節を指しています: §{s}"))
            direct = set()
            for s in starts:
                if s in node_by_num:
                    direct |= set(REF_RE.findall(_subtree_text(lines, node_by_num[s], skip)))
            missing = sorted(
                r for r in direct
                if r in node_by_num and not _covered(node_by_num, r, starts + refs)
            )
            if missing:
                result.problems.append((LEVEL_WARN, f"索引表の行「{name}」の参照先に、必読節の直接の参照先がありません: " + ", ".join("§" + m for m in missing)))
            sel = set()
            for s in starts + refs:
                if s in node_by_num:
                    sel |= chunk_idx_for(node_by_num[s])
            covered_files |= sel
            tasks.append({
                "name": name,
                "starts": ", ".join("§" + s for s in starts),
                "refs": ", ".join("§" + r for r in refs) if refs else "—",
                "files": _compact_numbers([i + 1 for i in sel]),
            })
        uncovered = [i + 1 for i in range(total) if i not in covered_files]
        if uncovered:
            result.problems.append((LEVEL_FAIL, "どの索引行にも属さないファイルがあります（新設節の取りこぼし）: " + ", ".join(names[i - 1] for i in uncovered)))

    # --- 目次（番号のある節。参照先は、その節の本文だけから抽出する） ---
    toc = []
    for node in nodes:
        if not node.num:
            continue
        own_refs = []
        for r in REF_RE.findall(_own_text(lines, node, skip)):
            if r in node_by_num and r not in own_refs:
                own_refs.append(r)
        at = chunk_of_heading(node)
        toc.append({
            "num": node.num,
            "title": _TITLE_NUM_RE.sub("", node.title),
            "file": f"{at + 1:0{width}d}" if at >= 0 else "",
            "file_name": names[at] if at >= 0 else "",
            "refs": ", ".join("§" + r for r in own_refs) if own_refs else "—",
        })

    # --- プレースホルダ ---
    seen = []
    for m in PLACEHOLDER_RE.finditer(result.body):
        if m.group(0) not in seen:
            seen.append(m.group(0))
    result.placeholders = seen

    title = nodes[0].title if nodes[0].level == 1 else meta.get("title", "")
    result.ctx = {
        "source": source_rel,
        "title": title,
        "version": meta.get("version", ""),
        "status": meta.get("status", ""),
        "file_count": total,
        "total_bytes": sum(len(c.encode("utf-8")) for c in result.files.values()),
        "toc": toc,
        "tasks": tasks,
        "placeholders": list(seen),
        "placeholders_line": ", ".join(f"`{p}`" for p in seen),
        "warnings": [msg for level, msg in result.problems if level == LEVEL_WARN],
    }
    return result


# --------------------------------------------------------------------------
# audit 用の補助
# --------------------------------------------------------------------------
def strip_header(content: str) -> str:
    """ファイル先頭のヘッダ行と、続く空行1行を除いた本文を返す。ヘッダが契約の書式でなければ ValueError。"""
    lines = split_lines(content)
    if len(lines) < 2 or not HEADER_RE.match(lines[0].rstrip("\r\n")) or lines[1].strip():
        raise ValueError("先頭のヘッダ行が契約の書式ではありません")
    return "".join(lines[2:])


def section_text(text: str, heading: str) -> str:
    """`## <heading>` の節本文（次の `## ` 見出しの直前まで。フェンスの中は見出しとみなさない）。無ければ空文字。"""
    lines = split_lines(text)
    fence = None
    inside = False
    out = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                if inside:
                    out.append(raw)
                continue
        else:
            stripped = line.strip()
            if m and stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                fence = None
            if inside:
                out.append(raw)
            continue
        h = _HEADING_RE.match(line)
        if h and len(h.group(1)) == 2:
            if inside:
                break
            if h.group(2) == heading:
                inside = True
                continue
        if inside:
            out.append(raw)
    return "".join(out)
