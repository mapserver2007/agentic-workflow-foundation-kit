#!/usr/bin/env python3
"""Design Doc 由来の Domain docs 本文を、書込み前に決定論で検査する（G-DOCFILL-*）。

`domain_docs_apply.py` が組んだ書込み計画（今回置換する本文と、適用後の docs の全文）を受け取り、
Design Doc の標準的な見出し構造から取り出せる事実が落ちていないかを調べる。
標準ライブラリだけで動く。アプリ固有の語は持たない。見出しの役割（`業務フロー`、`データベース設計`、
`API設計`）と、Markdown の構造（表、Mermaid、コードスパン）だけを手掛かりにする。

検査 ID:
  G-DOCFILL-001 FAIL  今回置換する本文に、`[TODO]` と雛形名（偽の図の雛形）が残っていない
  G-DOCFILL-002 WARN  workflows の sequenceDiagram / stateDiagram の本数が設計書以上
  G-DOCFILL-003 WARN  設計書のデータベース設計にあるテーブル名と列名が data-models にある
  G-DOCFILL-004 WARN  設計書の API 設計の「メソッドとパス」表にあるエンドポイントが api にある
  G-DOCFILL-005 WARN  新しい機能仕様に `## エラーハンドリング` がある
  G-DOCFILL-006 FAIL  束縛節（技術ブループリントの適用）で、プレースホルダの行がすべて埋まり、
                      決めた名前が名前決定表とディレクトリツリーに現れ、製品名がツリーに現れ、
                      集約ごとに proto の行（パスが `.proto`）が名前決定表にある
                      （`require_proto` が偽のときは要求しない。既定は要求する。承認済み契約が proto を使うかは apply が決める）

FAIL は呼び出し側（apply）が検証失敗として扱う。WARN は報告だけで、修復を起動しない。
設計書が標準の見出し構造を持たず抽出できない検査は skipped として理由を残す。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

API_FILE = "docs/api.md"
DATA_MODELS_FILE = "docs/data-models.md"
WORKFLOWS_FILE = "docs/workflows.md"
GATE_FILES = (API_FILE, DATA_MODELS_FILE, WORKFLOWS_FILE)

FLOW_HEADING = "業務フロー"
DATABASE_HEADING = "データベース設計"
API_HEADING = "API設計"
ERROR_HANDLING_HEADING = "## エラーハンドリング"

ATX = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
TABLE_NAME_HEADING = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)[（(].+[）)]$")
ENDPOINT = re.compile(r"^([A-Z]+)\s+(/\S*)$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
DIAGRAM_KINDS = ("sequenceDiagram", "stateDiagram")

# kit のテンプレートが過去に持っていた偽の図の雛形。
# 置換本文にあり、Design Doc に同じパターンが無いときだけ、起案が写した残存とみなす。
# Design Doc にある遷移は設計書の語なので持ち込む。`[TODO]` はこの緩和をしない。
SAMPLE_PATTERNS = (
    (re.compile(r"\bENTITY_[A-Z]\b"), "ER 図の雛形名"),
    (re.compile(r"Client\s*->>\s*API\s*:\s*リクエスト"), "sequence 図の雛形"),
    (re.compile(r"Created\s*-->\s*Processing"), "state 図の雛形"),
    (re.compile(r"\[コンポーネント\s*[AB]\]"), "構成図の雛形"),
)


@dataclass
class Report:
    findings: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def fails(self) -> list:
        return [item for item in self.findings if item["level"] == "FAIL"]

    @property
    def warns(self) -> list:
        return [item for item in self.findings if item["level"] == "WARN"]

    def add(self, gate_id: str, level: str, file: str, message: str) -> None:
        self.findings.append({"id": gate_id, "level": level, "file": file, "message": message})

    def skip(self, gate_id: str, reason: str) -> None:
        self.skipped.append({"id": gate_id, "reason": reason})

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "status": "FAIL" if self.fails else "PASS",
            "findings": list(self.findings),
            "skipped": list(self.skipped),
            "metrics": dict(self.metrics),
        }


# --------------------------------------------------------------------------
# Markdown の構造解析（コードフェンスを見出し・表として数えない）
# --------------------------------------------------------------------------
def fence_mask(lines: list) -> list:
    """各行がコードフェンスの行、またはその内側なら True。"""
    mask = []
    marker = ""
    for line in lines:
        stripped = line.rstrip("\r\n")
        match = FENCE.match(stripped)
        if marker:
            mask.append(True)
            if match and match.group(1)[0] == marker[0] and len(match.group(1)) >= len(marker) \
                    and not match.group(2).strip():
                marker = ""
            continue
        if match:
            marker = match.group(1)
            mask.append(True)
            continue
        mask.append(False)
    return mask


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line: int


def parse_headings(text: str) -> list:
    lines = text.splitlines()
    mask = fence_mask(lines)
    found = []
    for index, (line, fenced) in enumerate(zip(lines, mask)):
        if fenced:
            continue
        match = ATX.match(line)
        if match:
            found.append(Heading(len(match.group(1)), match.group(2).strip(), index))
    return found


def _subtree(headings: list, position: int) -> list:
    """position の見出しの配下（より深い見出し）を、次の同階層以上の見出しの手前まで返す。"""
    base = headings[position].level
    members = []
    for heading in headings[position + 1:]:
        if heading.level <= base:
            break
        members.append(heading)
    return members


def _find_heading(headings: list, name: str) -> int:
    for index, heading in enumerate(headings):
        if heading.text == name:
            return index
    return -1


def _split_cells(line: str) -> list:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_separator(cells: list) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", cell) for cell in cells)


def parse_tables(lines: list, mask: list, start: int, end: int) -> list:
    """[start, end) の行から、表（ヘッダ行、本文行）を順に返す。"""
    tables = []
    index = start
    while index < end:
        if mask[index] or not lines[index].lstrip().startswith("|"):
            index += 1
            continue
        block = []
        while index < end and not mask[index] and lines[index].lstrip().startswith("|"):
            block.append(_split_cells(lines[index]))
            index += 1
        if len(block) >= 2 and _is_separator(block[1]):
            tables.append({"header": block[0], "rows": block[2:]})
    return tables


# --------------------------------------------------------------------------
# Design Doc から取り出す事実
# --------------------------------------------------------------------------
def business_flow_children(design_text: str) -> list:
    """`業務フロー` 見出しの直下の子見出し。見出しが無いときは空。"""
    headings = parse_headings(design_text)
    position = _find_heading(headings, FLOW_HEADING)
    if position < 0:
        return []
    child_level = headings[position].level + 1
    return [item.text for item in _subtree(headings, position) if item.level == child_level]


def design_tables(design_text: str) -> list:
    """`データベース設計` 配下の `物理名（業務名）` 見出しと、その直下の表の第1列（列名）。"""
    headings = parse_headings(design_text)
    position = _find_heading(headings, DATABASE_HEADING)
    if position < 0:
        return []
    lines = design_text.splitlines()
    mask = fence_mask(lines)
    result = []
    for member in _subtree(headings, position):
        match = TABLE_NAME_HEADING.match(member.text)
        if not match:
            continue
        index = headings.index(member)
        end = headings[index + 1].line if index + 1 < len(headings) else len(lines)
        tables = parse_tables(lines, mask, member.line + 1, end)
        columns = []
        if tables:
            for row in tables[0]["rows"]:
                if row:
                    name = row[0].strip().strip("`").strip()
                    if name:
                        columns.append(name)
        result.append((match.group(1), columns))
    return result


def design_endpoints(design_text: str) -> list:
    """`API設計` 配下の、ヘッダに「パス」を含む表から (メソッド, パス) を返す。"""
    headings = parse_headings(design_text)
    position = _find_heading(headings, API_HEADING)
    if position < 0:
        return []
    lines = design_text.splitlines()
    mask = fence_mask(lines)
    end = len(lines)
    for heading in headings[position + 1:]:
        if heading.level <= headings[position].level:
            end = heading.line
            break
    found = []
    for table in parse_tables(lines, mask, headings[position].line + 1, end):
        if not any("パス" in cell for cell in table["header"]):
            continue
        for row in table["rows"]:
            for cell in row:
                for span in CODE_SPAN.findall(cell):
                    match = ENDPOINT.match(span.strip())
                    if match and (match.group(1), match.group(2)) not in found:
                        found.append((match.group(1), match.group(2)))
    return found


def mermaid_kinds(text: str) -> list:
    """Mermaid ブロックごとの図の種類（先頭の非空行）。"""
    lines = text.splitlines()
    kinds = []
    index = 0
    while index < len(lines):
        match = FENCE.match(lines[index])
        if not match:
            index += 1
            continue
        marker = match.group(1)
        info = match.group(2).strip().split()
        is_mermaid = bool(info) and info[0] == "mermaid"
        body = []
        index += 1
        while index < len(lines):
            closing = FENCE.match(lines[index])
            if closing and closing.group(1)[0] == marker[0] and len(closing.group(1)) >= len(marker) \
                    and not closing.group(2).strip():
                break
            body.append(lines[index])
            index += 1
        index += 1
        if is_mermaid:
            first = next((row.strip() for row in body if row.strip()), "")
            kinds.append(first.split()[0] if first else "")
    return kinds


def diagram_counts(text: str) -> dict:
    kinds = mermaid_kinds(text)
    return {
        kind: sum(1 for item in kinds if item == kind or item.startswith(f"{kind}-"))
        for kind in DIAGRAM_KINDS
    }


def design_identifiers(design_text: str) -> set:
    """本文のコードスパンにある snake_case の識別子（設計書の語彙の手掛かり）。"""
    lines = design_text.splitlines()
    mask = fence_mask(lines)
    found = set()
    for line, fenced in zip(lines, mask):
        if fenced:
            continue
        for span in CODE_SPAN.findall(line):
            if IDENTIFIER.match(span.strip()):
                found.add(span.strip())
    return found


def contract_vocabulary_hits(design_text: str, guidance_texts: Iterable) -> list:
    """契約 guidance に、設計書のコードスパン識別子が現れたものを返す（報告専用）。"""
    joined = "\n".join(guidance_texts)
    hits = []
    for identifier in sorted(design_identifiers(design_text)):
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])", joined):
            hits.append(identifier)
    return hits


def _word_present(name: str, text: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text) is not None


def _endpoint_present(method: str, path: str, text: str) -> bool:
    path_re = re.compile(rf"(?<![\w/]){re.escape(path)}(?![\w/{{}}\-])")
    method_re = re.compile(rf"(?<![A-Za-z]){re.escape(method)}(?![A-Za-z])")
    for line in text.splitlines():
        if path_re.search(line) and method_re.search(line):
            return True
    return False


# --------------------------------------------------------------------------
# 検査
# --------------------------------------------------------------------------
def evaluate(
    design_text: str,
    *,
    replaced: Mapping,
    final_texts: Mapping,
    spec_documents: Mapping,
    binding: Mapping | None = None,
) -> Report:
    """書込み計画を検査する。

    replaced: 今回置換する本文（ラベル → 本文）。G-DOCFILL-001 の対象。
    final_texts: 適用後の docs の全文（`GATE_FILES` のパス → 本文。ファイルが無ければ空文字）。
    spec_documents: 今回作成・置換する機能仕様の全文（パス → 本文）。G-DOCFILL-005 の対象。
    binding: 束縛節を今回書くときの、適用後の情報（apply が組む）。G-DOCFILL-006 の対象。無ければ検査しない。
    """
    report = Report()
    _check_residue(report, replaced, design_text)
    _check_diagrams(report, design_text, final_texts.get(WORKFLOWS_FILE, ""))
    _check_tables(report, design_text, final_texts.get(DATA_MODELS_FILE, ""))
    _check_endpoints(report, design_text, final_texts.get(API_FILE, ""))
    _check_spec_error_handling(report, spec_documents)
    _check_binding(report, binding)
    return report


def _check_binding(report: Report, binding: Mapping | None) -> None:
    """束縛節の整合。名前の語彙は持たず、apply が渡した名前の一覧だけを使う。"""
    if not binding:
        return
    label = f"{binding['file']}#{binding['section']}"
    rows = binding.get("placeholder_rows") or {}
    unfilled = sorted(name for name, value in rows.items() if not value.strip() or "[TODO]" in value)
    if unfilled:
        report.add(
            "G-DOCFILL-006", "FAIL", label,
            "プレースホルダの具体値が未記入: " + ", ".join(unfilled),
        )
    names_text = binding.get("names_text") or ""
    tree_text = binding.get("tree_text") or ""
    loose = lambda name, text: (  # noqa: E731
        re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text) is not None
    )
    required = list(binding.get("required_names") or [])
    if names_text:
        absent = [name for name in required if not loose(name, names_text)]
        if absent:
            report.add("G-DOCFILL-006", "FAIL", label, "名前決定表に現れない名前: " + ", ".join(absent))
    # proto の分割は集約の単位で決める。集約ごとに、パスが `.proto` の行が名前決定表に要る
    # （従属集約を親の proto に含めるときも、従属集約の行は親の `.proto` を指して残す）。
    # proto の行は、ブループリントが proto を使う契約のときだけ要る。呼び出し側（apply）が、承認済み契約の
    # `api_style` から `require_proto` を決めて渡す（無いときは要求する）。ゲート自身は API 方式を判断しない。
    feature_names = list(binding.get("feature_names") or [])
    if names_text and feature_names and binding.get("require_proto", True):
        with_proto = _proto_row_names(names_text)
        absent = [name for name in feature_names if name not in with_proto]
        if absent:
            report.add(
                "G-DOCFILL-006", "FAIL", label,
                "名前決定表に proto の行が無い集約: " + ", ".join(absent),
            )
    if tree_text:
        wanted = required + ([binding["app"]] if binding.get("app") else [])
        absent = [name for name in wanted if not loose(name, tree_text)]
        if absent:
            report.add(
                "G-DOCFILL-006", "FAIL", label,
                "ディレクトリツリーに現れない名前: " + ", ".join(absent),
            )
    report.metrics["binding"] = {"placeholders": len(rows), "names": len(required)}


def _proto_row_names(names_text: str) -> set[str]:
    """名前決定表のうち、パスが `.proto` で終わる行の実名の集合。列は 種別 / 実名 / パス / 根拠 の順。"""
    found: set[str] = set()
    for line in names_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if len(cells) >= 3 and cells[2].endswith(".proto"):
            found.add(cells[1])
    return found


def _check_residue(report: Report, replaced: Mapping, design_text: str) -> None:
    """雛形は Design Doc に無いときだけ FAIL にする。`[TODO]` は設計書にあっても FAIL。"""
    for label, body in sorted(replaced.items()):
        lines = body.splitlines()
        mask = fence_mask(lines)
        if any("[TODO]" in line and not fenced for line, fenced in zip(lines, mask)):
            report.add("G-DOCFILL-001", "FAIL", label, "コードフェンスの外に `[TODO]` が残っています")
        for pattern, meaning in SAMPLE_PATTERNS:
            if pattern.search(body) and not pattern.search(design_text):
                report.add("G-DOCFILL-001", "FAIL", label, f"{meaning}が残っています（設計書の内容へ置き換える）")


def _check_diagrams(report: Report, design_text: str, workflows_text: str) -> None:
    design = diagram_counts(design_text)
    if not any(design.values()):
        report.skip("G-DOCFILL-002", "設計書に sequenceDiagram / stateDiagram の Mermaid が無い")
        return
    if not workflows_text:
        report.skip("G-DOCFILL-002", f"{WORKFLOWS_FILE} が存在しない")
        return
    docs = diagram_counts(workflows_text)
    report.metrics["diagrams"] = {
        kind: {"design": design[kind], "docs": docs[kind]} for kind in DIAGRAM_KINDS
    }
    for kind in DIAGRAM_KINDS:
        if docs[kind] < design[kind]:
            report.add(
                "G-DOCFILL-002", "WARN", WORKFLOWS_FILE,
                f"{kind} の本数が設計書より少ない（設計書 {design[kind]} / docs {docs[kind]}）。"
                "設計書の図を Mermaid のまま引き継ぐ",
            )


def _check_tables(report: Report, design_text: str, data_models_text: str) -> None:
    tables = design_tables(design_text)
    if not tables:
        report.skip("G-DOCFILL-003", f"設計書に `{DATABASE_HEADING}` の `物理名（業務名）` 見出しが無い")
        return
    if not data_models_text:
        report.skip("G-DOCFILL-003", f"{DATA_MODELS_FILE} が存在しない")
        return
    missing_tables = []
    missing_columns = {}
    for name, columns in tables:
        if not _word_present(name, data_models_text):
            missing_tables.append(name)
            continue
        absent = [column for column in columns if not _word_present(column, data_models_text)]
        if absent:
            missing_columns[name] = absent
    report.metrics["tables"] = {"design": len(tables), "missing": len(missing_tables)}
    if missing_tables:
        report.add(
            "G-DOCFILL-003", "WARN", DATA_MODELS_FILE,
            "設計書のテーブルが無い: " + ", ".join(missing_tables),
        )
    for name, absent in sorted(missing_columns.items()):
        report.add(
            "G-DOCFILL-003", "WARN", DATA_MODELS_FILE,
            f"テーブル {name} の列が無い: " + ", ".join(absent),
        )


def _check_endpoints(report: Report, design_text: str, api_text: str) -> None:
    endpoints = design_endpoints(design_text)
    if not endpoints:
        report.skip("G-DOCFILL-004", f"設計書に `{API_HEADING}` の「メソッドとパス」表が無い")
        return
    if not api_text:
        report.skip("G-DOCFILL-004", f"{API_FILE} が存在しない")
        return
    missing = [f"{method} {path}" for method, path in endpoints if not _endpoint_present(method, path, api_text)]
    report.metrics["endpoints"] = {"design": len(endpoints), "missing": len(missing)}
    if missing:
        report.add("G-DOCFILL-004", "WARN", API_FILE, "設計書のエンドポイントが無い: " + ", ".join(missing))


def _check_spec_error_handling(report: Report, spec_documents: Mapping) -> None:
    if not spec_documents:
        report.skip("G-DOCFILL-005", "今回作成・置換する機能仕様が無い")
        return
    for rel, text in sorted(spec_documents.items()):
        lines = text.splitlines()
        mask = fence_mask(lines)
        has = any(line.rstrip() == ERROR_HANDLING_HEADING and not fenced for line, fenced in zip(lines, mask))
        if not has:
            report.add(
                "G-DOCFILL-005", "WARN", rel,
                f"`{ERROR_HANDLING_HEADING}` がありません。設計書にエラーの記述があれば節を足す",
            )
