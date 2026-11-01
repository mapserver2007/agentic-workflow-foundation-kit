#!/usr/bin/env python3
"""統一設計書の本文品質（B 水準）を機械検査する。validate_design_doc.py から呼ばれる。

検査するのは「構造的な品質の床」であり、記述の意味的な正しさは保証しない。
設計書に evidence: トークンは置かない。数値と名前の裏取りは書く前の調査で行い、本文へは転記しない。
"""
from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

N_A_RE = re.compile(r"^\s*(?:[-*]\s*)?該当なし:[ \t]*(?P<reason>.+?)\s*$", re.MULTILINE)
FRAGMENT_RE = re.compile(r"#L(\d+)(?:-L(\d+))?$")
PIPE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
MIN_N_A_REASON_CHARS = 20
MAX_READ_BYTES = 4 * 1024 * 1024


class QualityError(Exception):
    """本文品質の検査失敗（exit 1 相当）。"""


@dataclass(frozen=True)
class Profile:
    name: str
    scale: float
    total_chars: int
    min_evidence: int
    min_distinct_paths: int
    ref_cap: int
    require_elements: bool
    max_not_applicable: int
    max_confirm_total: int
    min_section9_rows: int


STANDARD = Profile("standard", 1.0, 18000, 0, 0, 99, True, 4, 14, 12)
COMPACT = Profile("compact", 0.4, 5000, 0, 0, 1, False, 8, 24, 3)

# 未確定事項の集約先。ここでの `[要確認]` は 1 節あたり・本文合計の上限に数えない。
CONFIRM_AGGREGATION_SECTION = 24

# 節ごとの最小分量。elements の "a|b" は any-of、複数要素は all-of。
# (min_chars, min_refs, elements) — chars は空白を除いた文字数。
SECTION_RULES: Dict[int, Tuple[int, int, Tuple[str, ...]]] = {
    1: (500, 0, ("list|table",)),
    2: (450, 0, ("list|table",)),
    3: (450, 0, ("list|table",)),
    4: (450, 0, ("fence|table",)),
    5: (500, 0, ("table",)),
    6: (600, 0, ("fence", "table")),
    7: (400, 0, ("fence",)),
    8: (500, 0, ("table",)),
    9: (250, 0, ()),
    10: (400, 0, ("table|list|fence",)),
    11: (400, 0, ("table|list|fence",)),
    12: (400, 0, ("table|list|fence",)),
    13: (400, 0, ("table|list|fence",)),
    14: (400, 0, ("table|list|fence",)),
    15: (400, 0, ("table|list|fence",)),
    16: (450, 0, ("fence|numbered",)),
    17: (400, 0, ("fence|numbered",)),
    18: (450, 0, ("list|fence|table",)),
    19: (450, 0, ("table|list",)),
    20: (400, 0, ("table|list",)),
    21: (600, 0, ("subheading",)),
    22: (400, 0, ("list|table",)),
    23: (250, 0, ()),
    24: (600, 0, ("fence",)),
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


def verify_evidence_ranges(
    source_root: Path,
    all_evidence: Sequence[Tuple[str, Optional[str]]],
) -> None:
    """全 evidence の行範囲が実ファイルの範囲内にあることを検査する（引用文の内容は検査しない）。"""
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


def _section_body(masked: Sequence[str], bounds: Tuple[int, int]) -> List[str]:
    return list(masked[bounds[0] : bounds[1]])


def validate_text_quality(
    masked: Sequence[str],
    raw: Sequence[str],
    fenced: Set[int],
    section_ranges: Dict[int, Tuple[int, int]],
    evidence: Sequence[Tuple[str, int]],
    profile: Profile,
) -> None:
    """text だけで決まる品質の床を検査する。

    evidence は互換のため受け取る。非空なら設計書にトークンが残っている。
    """
    if evidence:
        raise QualityError(
            "設計書に evidence: は書けません。根拠トークンは置かず、観測した事実を本文に書く"
        )

    not_applicable = 0
    confirm_total = 0
    total_chars = 0
    for section in range(1, 25):
        start, end = section_ranges[section]
        body = _section_body(masked, (start, end))
        total_chars += _nonspace(body)
        text = "\n".join(body)
        n_a = [m.group("reason") for m in N_A_RE.finditer(text)]
        if section not in (9, CONFIRM_AGGREGATION_SECTION):
            confirm = text.count("[要確認]")
            confirm_total += confirm
            if confirm > 2:
                raise QualityError(
                    f"§{section} の [要確認] が {confirm} 件です（1 節 2 件まで。"
                    f"未確定事項は §{CONFIRM_AGGREGATION_SECTION} に優先度の高い順で集約してください）"
                )
        min_chars, _min_refs, elements = SECTION_RULES[section]
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
        if profile.require_elements:
            for requirement in elements:
                if not any(_has_element(kind, body, raw, start, end, fenced) for kind in requirement.split("|")):
                    label = " または ".join(ELEMENT_LABELS[kind] for kind in requirement.split("|"))
                    raise QualityError(f"§{section} に {label} が必要です（B 水準の構造要件）")
    if not_applicable > profile.max_not_applicable:
        raise QualityError(f"該当なし の節が {not_applicable} 節です（上限 {profile.max_not_applicable}）。実装から読み取れる設計を書いてください")
    if confirm_total > profile.max_confirm_total:
        raise QualityError(
            f"[要確認] が本文で {confirm_total} 件です（§{CONFIRM_AGGREGATION_SECTION} を除き上限 {profile.max_confirm_total}）。"
            f"未確定事項は §{CONFIRM_AGGREGATION_SECTION} に優先度の高い順で集約してください"
        )
    section9_body = _section_body(masked, section_ranges[9])
    rows9 = max(data_row_count(section9_body), 1)
    if "\n".join(section9_body).count("[要確認]") * 4 > rows9:
        raise QualityError("§9 の方針列で [要確認] が行数の 25% を超えています。manifest・CI・Dockerfile を読み直して宣言値を拾ってください")
    if total_chars < profile.total_chars:
        raise QualityError(f"本文の分量が不足しています（§1〜§24 で {total_chars} 文字 < {profile.total_chars} 文字）")


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
