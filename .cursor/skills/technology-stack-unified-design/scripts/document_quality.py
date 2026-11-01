#!/usr/bin/env python3
"""統一設計書の本文品質（B 水準）を機械検査する。validate_design_doc.py から呼ばれる。

検査するのは「構造的な品質の床」であり、記述の意味的な正しさは保証しない。
ただし証跡台帳の引用は対象 worktree の実ファイルに逐語で実在することを検査する（幻覚防止）。
"""
from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

LEDGER_HEADER = ["ID", "証跡", "引用", "裏付け"]
REF_RE = re.compile(r"\[E(\d+)\]")
LEDGER_ID_RE = re.compile(r"^E(\d+)$")
N_A_RE = re.compile(r"^\s*(?:[-*]\s*)?該当なし:[ \t]*(?P<reason>.+?)\s*$", re.MULTILINE)
FRAGMENT_RE = re.compile(r"#L(\d+)(?:-L(\d+))?$")
PIPE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
MIN_QUOTE_CHARS = 3
MAX_QUOTE_CHARS = 120
MIN_N_A_REASON_CHARS = 20
MAX_READ_BYTES = 4 * 1024 * 1024


class QualityError(Exception):
    """本文品質の検査失敗（exit 1 相当）。"""


@dataclass(frozen=True)
class Profile:
    name: str
    scale: float
    total_chars: int
    min_ledger_rows: int
    min_distinct_paths: int
    ref_cap: int
    require_elements: bool
    max_not_applicable: int
    max_confirm_total: int
    min_comparison_rows: int
    min_glossary_rows: int
    min_reference_items: int
    min_checklist_rows: int
    min_section9_rows: int


STANDARD = Profile("standard", 1.0, 18000, 40, 25, 99, True, 4, 14, 3, 8, 8, 8, 12)
COMPACT = Profile("compact", 0.4, 5000, 8, 5, 1, False, 8, 24, 2, 3, 3, 3, 3)

# 節ごとの最小分量。elements の "a|b" は any-of、複数要素は all-of。
# (min_chars, min_refs, elements) — chars は空白を除いた文字数。
SECTION_RULES: Dict[int, Tuple[int, int, Tuple[str, ...]]] = {
    1: (500, 2, ("list|table",)),
    2: (450, 2, ("list|table",)),
    3: (450, 2, ("list|table",)),
    4: (450, 2, ("fence|table",)),
    5: (500, 4, ("table",)),
    6: (600, 3, ("fence", "table")),
    7: (400, 2, ("fence",)),
    8: (500, 3, ("table",)),
    9: (250, 0, ()),
    10: (400, 3, ("table|list|fence",)),
    11: (400, 3, ("table|list|fence",)),
    12: (400, 3, ("table|list|fence",)),
    13: (400, 3, ("table|list|fence",)),
    14: (400, 3, ("table|list|fence",)),
    15: (400, 3, ("table|list|fence",)),
    16: (450, 2, ("fence|numbered",)),
    17: (400, 2, ("fence|numbered",)),
    18: (450, 3, ("list|fence|table",)),
    19: (450, 3, ("table|list",)),
    20: (400, 2, ("table|list",)),
    21: (600, 3, ("subheading",)),
    22: (400, 2, ("list|table",)),
    23: (250, 1, ()),
    24: (600, 2, ("fence",)),
}

ELEMENT_LABELS = {
    "table": "表",
    "fence": "fenced code（図・ツリー・フロー）",
    "list": "箇条書き",
    "numbered": "番号付き手順",
    "subheading": "#### 小見出し（2 件以上）",
}


def select_profile(name: str, readable_files: Optional[int]) -> Profile:
    if name == "standard":
        return STANDARD
    if name == "compact":
        return COMPACT
    if readable_files is not None and readable_files < 60:
        return COMPACT
    return STANDARD


def _nonspace(lines: Sequence[str]) -> int:
    return sum(len(re.sub(r"\s+", "", line)) for line in lines if line.strip() != "---")


def _is_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(SEPARATOR_CELL_RE.match(cell.strip()) for cell in cells)


def _split_row(line: str) -> List[str]:
    stripped = line.strip()
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def table_blocks(lines: Sequence[str]) -> List[List[List[str]]]:
    """masked 行から連続する表を取り出す。各表は行（セル配列）のリスト（separator 含む）。"""
    blocks: List[List[List[str]]] = []
    current: List[List[str]] = []
    for line in lines:
        if PIPE_ROW_RE.match(line):
            current.append(_split_row(line))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return [block for block in blocks if len(block) >= 3 and _is_separator(block[1])]


def data_row_count(lines: Sequence[str]) -> int:
    return sum(len(block) - 2 for block in table_blocks(lines))


def _list_items(lines: Sequence[str]) -> int:
    return sum(1 for line in lines if re.match(r"^\s*[-*]\s+\S", line))


def _numbered_items(lines: Sequence[str]) -> int:
    return sum(1 for line in lines if re.match(r"^\s*\d+[.)]\s+\S", line))


def _subheadings(lines: Sequence[str]) -> int:
    return sum(1 for line in lines if re.match(r"^####\s+\S", line))


def _fence_content_lines(raw: Sequence[str], start: int, end: int, fenced: Set[int]) -> int:
    """fence の開閉行を除いた内容行数。"""
    count = 0
    for index in range(start, end):
        if index in fenced and raw[index].strip() and not re.match(r"^\s*(`{3,}|~{3,})", raw[index]):
            count += 1
    return count


def _has_element(kind: str, masked_body: Sequence[str], raw: Sequence[str], start: int, end: int, fenced: Set[int]) -> bool:
    if kind == "table":
        return data_row_count(masked_body) >= 2
    if kind == "fence":
        return _fence_content_lines(raw, start, end, fenced) >= 3
    if kind == "list":
        return _list_items(masked_body) >= 3
    if kind == "numbered":
        return _numbered_items(masked_body) >= 3
    if kind == "subheading":
        return _subheadings(masked_body) >= 2
    return False


@dataclass(frozen=True)
class LedgerRow:
    entry_id: int
    path: str
    fragment: Optional[str]
    quote: str
    claim: str
    line_index: int


def _strip_quote(cell: str) -> str:
    value = cell.strip()
    if len(value) >= 2 and value[0] == "`" and value[-1] == "`":
        value = value[1:-1]
    return value.strip()


def parse_ledger(
    masked: Sequence[str],
    appendix_b: Tuple[int, int],
    evidence_token_re: "re.Pattern[str]",
) -> List[LedgerRow]:
    start, end = appendix_b
    rows: List[LedgerRow] = []
    seen_header = False
    for index in range(start, end):
        line = masked[index]
        if not PIPE_ROW_RE.match(line):
            continue
        cells = _split_row(line)
        if cells == LEDGER_HEADER:
            seen_header = True
            continue
        if _is_separator(cells):
            continue
        if not seen_header:
            continue
        if len(cells) != 4:
            raise QualityError(f"Appendix B の台帳行は 4 セル必要です（引用に | を含めないでください）: {line.strip()[:60]}")
        id_match = LEDGER_ID_RE.match(cells[0])
        if id_match is None:
            raise QualityError(f"Appendix B の台帳 ID は E<数字> 形式にしてください: {cells[0]}")
        tokens = list(evidence_token_re.finditer(cells[1]))
        if len(tokens) != 1 or "evidence:" not in cells[1]:
            raise QualityError(f"台帳 {cells[0]} の証跡セルには evidence: を 1 件だけ置いてください")
        token = tokens[0]
        path = token.group("quoted_path") or token.group("plain_path")
        fragment = token.group("quoted_fragment") or token.group("plain_fragment")
        quote = _strip_quote(cells[2])
        claim = cells[3].strip()
        if not (MIN_QUOTE_CHARS <= len(quote) <= MAX_QUOTE_CHARS):
            raise QualityError(f"台帳 {cells[0]} の引用は {MIN_QUOTE_CHARS}〜{MAX_QUOTE_CHARS} 文字にしてください")
        if not claim:
            raise QualityError(f"台帳 {cells[0]} の裏付け（主張）が空です")
        rows.append(LedgerRow(int(id_match.group(1)), path, fragment, quote, claim, index))
    if not seen_header:
        raise QualityError("Appendix B に台帳表（ヘッダ: ID | 証跡 | 引用 | 裏付け）がありません")
    ids = [row.entry_id for row in rows]
    if len(ids) != len(set(ids)):
        raise QualityError("Appendix B の台帳 ID が重複しています")
    return rows


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def verify_evidence_ranges_and_quotes(
    source_root: Path,
    ledger: Sequence[LedgerRow],
    all_evidence: Sequence[Tuple[str, Optional[str]]],
) -> None:
    """全 evidence の行範囲の実在と、台帳引用の逐語実在を検査する。"""
    cache: Dict[str, List[str]] = {}

    def lines_of(path: str) -> List[str]:
        if path not in cache:
            full = source_root / path
            try:
                metadata = os.lstat(full)
                if stat.S_ISLNK(metadata.st_mode) or metadata.st_size > MAX_READ_BYTES:
                    raise QualityError(f"evidence {path} を検査できません（symlink または大きすぎます）")
                data = full.read_bytes()
            except OSError as exc:
                raise QualityError(f"evidence {path} を読み取れません") from exc
            cache[path] = data.decode("utf-8", errors="replace").split("\n")
        return cache[path]

    def bounds(path: str, fragment: Optional[str]) -> Tuple[int, int]:
        lines = lines_of(path)
        total = len(lines) - (1 if lines and lines[-1] == "" else 0)
        if fragment is None:
            return 1, max(total, 1)
        match = FRAGMENT_RE.search(fragment)
        assert match is not None
        first = int(match.group(1))
        last = int(match.group(2) or match.group(1))
        if first < 1 or last < first or last > total:
            raise QualityError(f"evidence {path}{fragment} の行範囲が実ファイルの範囲（1〜{total}）外です")
        return first, last

    for path, fragment in all_evidence:
        bounds(path, fragment)
    for row in ledger:
        first, last = bounds(row.path, row.fragment)
        window = _normalize("\n".join(lines_of(row.path)[first - 1 : last]))
        if _normalize(row.quote) not in window:
            raise QualityError(
                f"台帳 E{row.entry_id} の引用が {row.path}"
                f"{row.fragment or ''} の本文に逐語で存在しません（ファイルを開いてコピーしてください）"
            )


def _section_body(masked: Sequence[str], bounds: Tuple[int, int]) -> List[str]:
    return list(masked[bounds[0] : bounds[1]])


def validate_text_quality(
    masked: Sequence[str],
    raw: Sequence[str],
    fenced: Set[int],
    section_ranges: Dict[int, Tuple[int, int]],
    appendix_ranges: Dict[str, Tuple[int, int]],
    evidence_lines: Set[int],
    profile: Profile,
    evidence_token_re: "re.Pattern[str]",
) -> List[LedgerRow]:
    """text だけで決まる品質の床を検査し、台帳行を返す。"""
    ledger = parse_ledger(masked, appendix_ranges["B"], evidence_token_re)
    ledger_lines = {row.line_index for row in ledger}
    ids = {row.entry_id for row in ledger}
    referenced: Set[int] = set()
    undefined: Set[int] = set()
    section_ref_counts: Dict[int, int] = {}
    for index, line in enumerate(masked):
        if index in ledger_lines:
            continue
        for match in REF_RE.finditer(line):
            number = int(match.group(1))
            referenced.add(number)
            if number not in ids:
                undefined.add(number)
    if undefined:
        raise QualityError("台帳に無い証跡参照があります: " + ", ".join(f"[E{n}]" for n in sorted(undefined)[:8]))
    unused = sorted(ids - referenced)
    if unused:
        raise QualityError("本文から参照されていない台帳行があります: " + ", ".join(f"E{n}" for n in unused[:8]))
    if len(ledger) < profile.min_ledger_rows:
        raise QualityError(f"Appendix B の台帳が {len(ledger)} 件です（{profile.name} 水準は {profile.min_ledger_rows} 件以上）")
    distinct = {row.path for row in ledger}
    if len(distinct) < profile.min_distinct_paths:
        raise QualityError(
            f"台帳の証跡ファイルが {len(distinct)} 種類です（{profile.name} 水準は {profile.min_distinct_paths} 種類以上。広く裏取りしてください）"
        )

    not_applicable = 0
    confirm_total = 0
    total_chars = 0
    for section in range(1, 25):
        start, end = section_ranges[section]
        body = _section_body(masked, (start, end))
        total_chars += _nonspace(body)
        for offset, line in enumerate(body):
            if section != 9 and line.strip().startswith("evidence:"):
                raise QualityError(
                    f"§{section} に evidence: だけの行があります。本文は [E<n>] 参照にし、根拠は Appendix B 台帳へ集約してください"
                )
        refs = sum(len(REF_RE.findall(line)) for line in body)
        refs += sum(1 for number in evidence_lines if start <= number < end)
        section_ref_counts[section] = refs
        text = "\n".join(body)
        n_a = [m.group("reason") for m in N_A_RE.finditer(text)]
        if section != 9:
            confirm = text.count("[要確認]")
            confirm_total += confirm
            if confirm > 2:
                raise QualityError(f"§{section} の [要確認] が {confirm} 件です（1 節 2 件まで。未確定事項は Appendix E へ集約してください）")
        min_chars, min_refs, elements = SECTION_RULES[section]
        if n_a:
            if any(len(reason) < MIN_N_A_REASON_CHARS for reason in n_a):
                raise QualityError(f"§{section} の 該当なし の根拠は {MIN_N_A_REASON_CHARS} 文字以上で、探した対象を具体的に書いてください")
            not_applicable += 1
            continue
        if section == 9:
            rows = data_row_count(body)
            if rows < profile.min_section9_rows:
                raise QualityError(f"§9 の技術表が {rows} 行です（{profile.name} 水準は {profile.min_section9_rows} 行以上）")
        if _nonspace(body) < int(min_chars * profile.scale):
            raise QualityError(
                f"§{section} の分量が不足しています（{_nonspace(body)} 文字 < {int(min_chars * profile.scale)} 文字）。"
                "事実の列挙ではなく、設計としての構造・理由・境界を書いてください"
            )
        need_refs = min(min_refs, profile.ref_cap)
        if refs < need_refs:
            raise QualityError(f"§{section} の証跡参照が {refs} 件です（{need_refs} 件以上。[E<n>] で台帳へ紐付けてください）")
        if profile.require_elements:
            for requirement in elements:
                if not any(_has_element(kind, body, raw, start, end, fenced) for kind in requirement.split("|")):
                    label = " または ".join(ELEMENT_LABELS[kind] for kind in requirement.split("|"))
                    raise QualityError(f"§{section} に {label} が必要です（B 水準の構造要件）")
    if not_applicable > profile.max_not_applicable:
        raise QualityError(f"該当なし の節が {not_applicable} 節です（上限 {profile.max_not_applicable}）。実装から読み取れる設計を書いてください")
    if confirm_total > profile.max_confirm_total:
        raise QualityError(f"[要確認] が本文で {confirm_total} 件です（上限 {profile.max_confirm_total}）。未確定事項は Appendix E に優先度付きで集約してください")
    section9_body = _section_body(masked, section_ranges[9])
    rows9 = max(data_row_count(section9_body), 1)
    if "\n".join(section9_body).count("[要確認]") * 4 > rows9:
        raise QualityError("§9 の方針列で [要確認] が行数の 25% を超えています。manifest・CI・Dockerfile を読み直して宣言値を拾ってください")
    if total_chars < profile.total_chars:
        raise QualityError(f"本文の分量が不足しています（§1〜§24 で {total_chars} 文字 < {profile.total_chars} 文字）")
    _validate_appendices(masked, appendix_ranges, profile)
    return ledger


def _validate_appendices(masked: Sequence[str], appendix_ranges: Dict[str, Tuple[int, int]], profile: Profile) -> None:
    body_a = _section_body(masked, appendix_ranges["A"])
    if data_row_count(body_a) < profile.min_comparison_rows:
        raise QualityError(f"Appendix A の比較表が {profile.min_comparison_rows} 行未満です（観点 × 選択肢の表で比較してください）")
    body_c = _section_body(masked, appendix_ranges["C"])
    if data_row_count(body_c) < profile.min_glossary_rows:
        raise QualityError(f"Appendix C の用語表が {profile.min_glossary_rows} 行未満です")
    body_d = _section_body(masked, appendix_ranges["D"])
    if _list_items(body_d) + data_row_count(body_d) < profile.min_reference_items:
        raise QualityError(f"Appendix D の参照が {profile.min_reference_items} 件未満です")
    body_e = _section_body(masked, appendix_ranges["E"])
    blocks = table_blocks(body_e)
    rows = [row for block in blocks for row in block[2:]]
    if len(rows) < profile.min_checklist_rows:
        raise QualityError(f"Appendix E のチェックリスト表が {profile.min_checklist_rows} 行未満です")
    if not any("優先度" in cell for block in blocks for cell in block[0]):
        raise QualityError("Appendix E の表には 優先度 列が必要です")
    bad = [row for row in rows if not re.match(r"^P[0-3]\b", row[0])]
    if bad:
        raise QualityError("Appendix E の各行の先頭列は優先度（P0〜P3）で始めてください")


def validate_coverage_line(masked: Sequence[str], survey_dir: str, source_root: str) -> None:
    from survey_repository import SurveyError, check_survey

    try:
        coverage = check_survey(survey_dir, source_root)
    except SurveyError as exc:
        raise QualityError(str(exc)) from exc
    wanted = coverage.line()
    if not any(wanted in line for line in masked):
        raise QualityError(
            "本文に survey が算出した 調査範囲 行がありません。次の 1 行を導入部（目次より前）へ逐語で置いてください: " + wanted
        )
