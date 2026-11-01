#!/usr/bin/env python3
"""リバース生成した技術スタック統一設計書の MUST 契約を検証する。"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, List, Sequence, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from inspect_local_repository import (  # noqa: E402
    InspectionError,
    RepositoryInspection,
    _safe_git,
    inspect_repository,
)
import document_quality as dq  # noqa: E402

PART_SECTIONS: Dict[int, Tuple[int, int]] = {
    1: (1, 5),
    2: (6, 8),
    3: (9, 15),
    4: (16, 23),
    5: (24, 24),
}
APPENDIX_IDS = ("A", "B", "C", "D", "E")
REQUIRED_FRONTMATTER = (
    "status",
    "title",
    "generated_at",
    "source_repository",
    "source_ref",
    "source_revision",
    "stack_slug",
)
STACK_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PART_ROLE_LABELS = {1: "なぜ", 2: "何を", 3: "具体", 4: "どう動かす", 5: "意思決定"}
APPENDIX_RESPONSIBILITY_TOKENS = {
    "A": "比較",
    "B": "根拠",
    "C": "用語",
    "D": "参照",
    "E": "チェックリスト",
}

# reference/evidence-signals.md の同名リストと同期し、fixture test で一致を検査する。
EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "out",
        "target",
        "coverage",
        ".cache",
        ".next",
        ".nuxt",
        ".venv",
        "venv",
        "__pycache__",
    }
)
EXCLUDED_FILE_NAMES = frozenset(
    {
        ".netrc",
        ".git-credentials",
        "credentials",
        "credentials.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)
EXCLUDED_FILE_PREFIXES = (".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
EXCLUDED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".der", ".crt", ".cer")
BINARY_EXTENSIONS = frozenset(
    {
        ".7z",
        ".a",
        ".avi",
        ".bin",
        ".bmp",
        ".class",
        ".dll",
        ".dylib",
        ".eot",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".mov",
        ".mp3",
        ".mp4",
        ".o",
        ".otf",
        ".pdf",
        ".png",
        ".pyc",
        ".so",
        ".tar",
        ".tiff",
        ".ttf",
        ".wav",
        ".webp",
        ".woff",
        ".woff2",
        ".xz",
        ".zip",
    }
)

# evidence token の完全な字句規則。引用あり・なしを同じ正規表現で扱う。
EVIDENCE_TOKEN_RE = re.compile(
    r"evidence:\s+(?:"
    r"`(?P<quoted_path>[^\s`;,|)#]+)(?P<quoted_fragment>#L\d+(?:-L\d+)?)?`"
    r"|(?P<plain_path>[^\s`;,|)#]+)(?P<plain_fragment>#L\d+(?:-L\d+)?)?"
    r")(?=$|[\s;,|)])"
)
DECLARATION_RE = re.compile(r"(?m)^\s*(?:[-*]\s*)?(?:\[要確認\]|該当なし):[ \t]*(?P<reason>[^\r\n]*)$")
PART_RE = re.compile(r"^##\s+Part\s+([1-5])(?:\s*[:：].*)?\s*$")
APPENDIX_H2_RE = re.compile(r"^##\s+Appendix(?:\s*[:：].*)?\s*$")
SECTION_RE = re.compile(r"^###\s+(\d+)\.\s*(.*)$")
APPENDIX_H3_RE = re.compile(r"^###\s+Appendix\s+([A-E])(?:\s*[:：].*)?\s*$")
TOC_H2_RE = re.compile(r"^##\s+目次\s*$")
TOC_SECTION_RE = re.compile(r"^\s*(?:[-*]\s*)?(\d+)\.\s+\[[^\]]+\]\((#[^)]+)\)\s*$")
TOC_APPENDIX_RE = re.compile(
    r"^\s*(?:[-*]\s*)?\[\s*Appendix\s+([A-E])(?:\s*[:：][^\]]*)?\]\((#[^)]+)\)\s*$"
)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
PLACEHOLDER_RE = re.compile(r"^(?:<[^>]*>|TODO|TBD|\.\.\.)$", re.IGNORECASE)


class ValidationError(Exception):
    """検証失敗。code は CLI の exit code に対応する。"""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Frontmatter:
    status: str
    title: str
    generated_at: str
    source_repository: str
    source_ref: str
    source_revision: str
    stack_slug: str
    end_line: int


@dataclass(frozen=True)
class Evidence:
    path: str
    fragment: str | None
    line_number: int


@dataclass(frozen=True)
class ValidationResult:
    frontmatter: Frontmatter
    inspection: RepositoryInspection | None
    evidence_count: int


def _parse_frontmatter(lines: Sequence[str]) -> Frontmatter:
    if not lines or lines[0] != "---":
        raise ValidationError("ファイル先頭に frontmatter がありません")
    values: Dict[str, str] = {}
    end = None
    for index in range(1, len(lines)):
        line = lines[index]
        if line == "---":
            end = index
            break
        if ":" not in line:
            raise ValidationError("frontmatter は key: value 形式で記述してください")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in values:
            raise ValidationError("frontmatter に重複キーがあります")
        values[key] = value
    if end is None:
        raise ValidationError("frontmatter の終端がありません")
    for key in REQUIRED_FRONTMATTER:
        if key not in values:
            raise ValidationError("frontmatter の必須キーが不足しています")
    if values["status"] != "reverse-draft":
        raise ValidationError("frontmatter status は reverse-draft 必須です")
    decoded: Dict[str, str] = {}
    for key in ("title", "generated_at", "source_repository", "source_ref", "source_revision", "stack_slug"):
        try:
            value = json.loads(values[key])
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValidationError(f"frontmatter {key} は JSON 文字列リテラル必須です") from exc
        if not isinstance(value, str):
            raise ValidationError(f"frontmatter {key} は JSON 文字列リテラル必須です")
        decoded[key] = value
    if not re.fullmatch(r"[0-9a-f]{40}", decoded["source_revision"]):
        raise ValidationError("source_revision は小文字の 40 桁 hex 必須です")
    if not decoded["title"].strip():
        raise ValidationError("frontmatter title は非空の JSON 文字列リテラル必須です")
    if not DATE_RE.fullmatch(decoded["generated_at"]):
        raise ValidationError("frontmatter generated_at は YYYY-MM-DD の JSON 文字列リテラル必須です")
    if len(decoded["stack_slug"]) > 63 or not STACK_SLUG_RE.fullmatch(decoded["stack_slug"]):
        raise ValidationError("stack_slug は1〜63文字の lowercase kebab-case 必須です")
    return Frontmatter(
        status=values["status"],
        title=decoded["title"],
        generated_at=decoded["generated_at"],
        source_repository=decoded["source_repository"],
        source_ref=decoded["source_ref"],
        source_revision=decoded["source_revision"].lower(),
        stack_slug=decoded["stack_slug"],
        end_line=end,
    )


def _mask_markdown(lines: Sequence[str]) -> Tuple[List[str], Set[int]]:
    """fenced code block と HTML comment を空行化する。"""
    masked: List[str] = []
    fenced_lines: Set[int] = set()
    fence_char = ""
    fence_length = 0
    in_comment = False
    for index, original in enumerate(lines):
        line = original
        if fence_char:
            fenced_lines.add(index)
            stripped = line.lstrip()
            marker = re.match(re.escape(fence_char) + r"+", stripped)
            if (
                marker is not None
                and len(marker.group(0)) >= fence_length
                and not stripped[marker.end() :].strip()
            ):
                fence_char, fence_length = "", 0
            masked.append("")
            continue
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            fenced_lines.add(index)
            masked.append("")
            continue
        output: List[str] = []
        cursor = 0
        while cursor < len(line):
            if in_comment:
                close = line.find("-->", cursor)
                if close < 0:
                    cursor = len(line)
                    break
                cursor = close + 3
                in_comment = False
                continue
            opening = line.find("<!--", cursor)
            if opening < 0:
                output.append(line[cursor:])
                break
            output.append(line[cursor:opening])
            cursor = opening + 4
            in_comment = True
        masked.append("".join(output))
    return masked, fenced_lines


def _heading_anchor(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    return "#" + re.sub(r"[-\s]+", "-", normalized).strip("-")


def _require_separator_before(masked: Sequence[str], line: int, label: str) -> None:
    previous = line - 1
    while previous >= 0 and not masked[previous].strip():
        previous -= 1
    if previous < 0 or masked[previous].strip() != "---":
        raise ValidationError(f"{label} の直前には単独行 --- の区切りが必要です")


def _toc_span(masked: Sequence[str], frontmatter_end: int) -> Tuple[int, int]:
    matches = [
        index
        for index, line in enumerate(masked[frontmatter_end + 1 :], start=frontmatter_end + 1)
        if TOC_H2_RE.match(line)
    ]
    if len(matches) != 1:
        raise ValidationError("## 目次 は Part 1 より前に 1 つ必要です")
    start = matches[0]
    end = next(
        (index for index in range(start + 1, len(masked)) if masked[index].startswith("## ")),
        len(masked),
    )
    if end == len(masked) or not PART_RE.match(masked[end]):
        raise ValidationError("目次の直後には Part 1 を置いてください")
    _require_separator_before(masked, start, "目次")
    _require_separator_before(masked, end, "Part 1")
    return start, end


def _validate_toc(
    masked: Sequence[str],
    start: int,
    end: int,
    section_lines: Dict[int, int],
    appendix_lines: Dict[str, int],
) -> None:
    section_links: Dict[int, str] = {}
    appendix_links: Dict[str, str] = {}
    for line in masked[start + 1 : end]:
        if SECTION_RE.match(line) or APPENDIX_H3_RE.match(line):
            raise ValidationError("目次内に本文構造として見える見出しを置けません")
        section_match = TOC_SECTION_RE.match(line)
        if section_match:
            number = int(section_match.group(1))
            if number in section_links:
                raise ValidationError("目次の節リンクが重複しています")
            section_links[number] = section_match.group(2)
            continue
        appendix_match = TOC_APPENDIX_RE.match(line)
        if appendix_match:
            appendix_id = appendix_match.group(1)
            if appendix_id in appendix_links:
                raise ValidationError("目次の Appendix リンクが重複しています")
            appendix_links[appendix_id] = appendix_match.group(2)
    if sorted(section_links) != list(range(1, 25)):
        raise ValidationError("目次には §1〜§24 の番号付きリンクが必要です")
    if tuple(appendix_links) != APPENDIX_IDS:
        raise ValidationError("目次には Appendix A〜E のリンクが必要です")
    for section, line in section_lines.items():
        if section_links[section] != _heading_anchor(masked[line][4:]):
            raise ValidationError(f"目次の §{section} リンクが本文見出しと一致しません")
    for appendix_id, line in appendix_lines.items():
        if appendix_links[appendix_id] != _heading_anchor(masked[line][4:]):
            raise ValidationError(f"目次の Appendix {appendix_id} リンクが本文見出しと一致しません")


def _validate_structure(masked: Sequence[str], frontmatter_end: int) -> Tuple[Dict[int, int], Dict[str, int]]:
    part_lines: Dict[int, int] = {}
    section_lines: Dict[int, int] = {}
    appendix_lines: Dict[str, int] = {}
    appendix_h2: List[int] = []
    current_part: int | None = None
    seen_appendix = False
    toc_start, toc_end = _toc_span(masked, frontmatter_end)
    for index, line in enumerate(masked[frontmatter_end + 1 :], start=frontmatter_end + 1):
        if toc_start < index < toc_end:
            continue
        part_match = PART_RE.match(line)
        if part_match:
            part = int(part_match.group(1))
            if part in part_lines:
                raise ValidationError("Part 見出しが重複しています")
            if seen_appendix:
                raise ValidationError("Part は Appendix より前に置いてください")
            label = PART_ROLE_LABELS[part]
            if f"({label})" not in line and f"（{label}）" not in line:
                raise ValidationError(f"Part {part} には役割ラベル {label} が必要です")
            part_lines[part] = index
            current_part = part
            continue
        if APPENDIX_H2_RE.match(line):
            appendix_h2.append(index)
            current_part = None
            seen_appendix = True
            continue
        section_match = SECTION_RE.match(line)
        if section_match:
            section = int(section_match.group(1))
            if section < 1 or section > 24:
                continue
            if section_match.group(1) != str(section):
                raise ValidationError("節番号は先頭ゼロなしの10進表記にしてください")
            if section in section_lines:
                raise ValidationError("節見出しが重複しています")
            expected_part = next(
                part for part, bounds in PART_SECTIONS.items() if bounds[0] <= section <= bounds[1]
            )
            if current_part != expected_part:
                raise ValidationError(f"§{section} の所属 Part が対応表と一致しません")
            section_lines[section] = index
            continue
        appendix_match = APPENDIX_H3_RE.match(line)
        if appendix_match:
            appendix_id = appendix_match.group(1)
            if appendix_id in appendix_lines:
                raise ValidationError("Appendix 節が重複しています")
            if not seen_appendix or current_part is not None:
                raise ValidationError("Appendix A〜E は Part の外に置いてください")
            appendix_lines[appendix_id] = index
            if APPENDIX_RESPONSIBILITY_TOKENS[appendix_id] not in line:
                raise ValidationError(
                    f"Appendix {appendix_id} には責務トークン "
                    f"{APPENDIX_RESPONSIBILITY_TOKENS[appendix_id]} が必要です"
                )

    if sorted(part_lines) != [1, 2, 3, 4, 5] or [part_lines[p] for p in range(1, 6)] != sorted(part_lines.values()):
        raise ValidationError("Part 1〜5 は欠落なく昇順に置いてください")
    if len(appendix_h2) != 1 or appendix_h2[0] <= part_lines[5]:
        raise ValidationError("単一の ## Appendix を Part 5 の後に置いてください")
    if sorted(section_lines) != list(range(1, 25)):
        raise ValidationError("§1〜§24 が不足しています")
    if [section_lines[s] for s in range(1, 25)] != sorted(section_lines.values()):
        raise ValidationError("§1〜§24 は昇順に置いてください")
    if tuple(appendix_lines) != APPENDIX_IDS:
        raise ValidationError("Appendix A〜E は欠落なく昇順に置いてください")
    if [appendix_lines[a] for a in APPENDIX_IDS] != sorted(appendix_lines.values()):
        raise ValidationError("Appendix A〜E は昇順に置いてください")
    if appendix_lines["A"] <= appendix_h2[0]:
        raise ValidationError("Appendix A〜E は ## Appendix 配下に置いてください")
    for part in range(2, 6):
        _require_separator_before(masked, part_lines[part], f"Part {part}")
    for section in range(1, 25):
        if section not in {1, 6, 9, 16, 24}:
            _require_separator_before(masked, section_lines[section], f"§{section}")
    _require_separator_before(masked, appendix_h2[0], "Appendix")
    for appendix_id in APPENDIX_IDS[1:]:
        _require_separator_before(masked, appendix_lines[appendix_id], f"Appendix {appendix_id}")
    _validate_toc(masked, toc_start, toc_end, section_lines, appendix_lines)
    return section_lines, appendix_lines


def _body_ranges(
    masked: Sequence[str],
    section_lines: Dict[int, int],
    appendix_lines: Dict[str, int],
) -> Tuple[Dict[int, Tuple[int, int]], Dict[str, Tuple[int, int]]]:
    headings: List[Tuple[int, str, str]] = []
    headings.extend((line, "section", str(section)) for section, line in section_lines.items())
    headings.extend((line, "appendix", appendix_id) for appendix_id, line in appendix_lines.items())
    for index, line in enumerate(masked):
        if PART_RE.match(line) or APPENDIX_H2_RE.match(line):
            headings.append((index, "boundary", ""))
    headings.sort()
    section_ranges: Dict[int, Tuple[int, int]] = {}
    appendix_ranges: Dict[str, Tuple[int, int]] = {}
    for position, (line, kind, identifier) in enumerate(headings):
        if kind == "boundary":
            continue
        end = headings[position + 1][0] if position + 1 < len(headings) else len(masked)
        while end > line + 1 and masked[end - 1].strip() in {"", "---"}:
            end -= 1
        if kind == "section":
            section_ranges[int(identifier)] = (line + 1, end)
        else:
            appendix_ranges[identifier] = (line + 1, end)
    return section_ranges, appendix_ranges


def _valid_reason(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and not PLACEHOLDER_RE.fullmatch(stripped)


def _extract_evidence(masked: Sequence[str]) -> List[Evidence]:
    evidence: List[Evidence] = []
    for line_number, line in enumerate(masked, start=1):
        cursor = 0
        while True:
            marker = line.find("evidence:", cursor)
            if marker < 0:
                break
            match = EVIDENCE_TOKEN_RE.match(line, marker)
            if match is None:
                raise ValidationError(f"evidence の書式が不正です（line {line_number}）")
            path = match.group("quoted_path") or match.group("plain_path")
            fragment = match.group("quoted_fragment") or match.group("plain_fragment")
            evidence.append(Evidence(path, fragment, line_number))
            cursor = match.end()
    return evidence


def _section_has_declaration(body: str, evidence_lines: Set[int], start_line: int) -> bool:
    for line_number in evidence_lines:
        if start_line <= line_number:
            relative = line_number - start_line
            if relative < len(body.splitlines()):
                return True
    return any(_valid_reason(match.group("reason")) for match in DECLARATION_RE.finditer(body))


def _validate_bodies(
    masked: Sequence[str],
    section_ranges: Dict[int, Tuple[int, int]],
    appendix_ranges: Dict[str, Tuple[int, int]],
    evidence: Sequence[Evidence],
) -> None:
    evidence_zero_based = {item.line_number - 1 for item in evidence}
    ref_lines = {index for index, line in enumerate(masked) if dq.REF_RE.search(line)}
    for section in range(1, 25):
        start, end = section_ranges[section]
        body_lines = masked[start:end]
        body = "\n".join(body_lines)
        if not body.strip():
            raise ValidationError(f"§{section} の本文が空です")
        local_evidence = any(start <= line < end for line in evidence_zero_based | ref_lines)
        valid_reason = any(_valid_reason(match.group("reason")) for match in DECLARATION_RE.finditer(body))
        if not local_evidence and not valid_reason:
            raise ValidationError(f"§{section} に有効な宣言がありません")
    for appendix_id in APPENDIX_IDS:
        start, end = appendix_ranges[appendix_id]
        if not "\n".join(masked[start:end]).strip():
            raise ValidationError(f"Appendix {appendix_id} の本文が空です")


def _split_table_row(line: str) -> List[str]:
    stripped = line.strip()
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _validate_section9(
    raw_lines: Sequence[str],
    section_ranges: Dict[int, Tuple[int, int]],
    fenced_lines: Set[int],
) -> None:
    structural_heading_lines = {bounds[0] - 1 for bounds in section_ranges.values()}
    for index, line in enumerate(raw_lines):
        if re.match(r"^\s*###\s+\d+\.", line) and index not in structural_heading_lines:
            raise ValidationError("mask 対象内に番号付き節見出しを置けません")
    start, end = section_ranges[9]
    body = list(raw_lines[start:end])
    if any(line.strip() == "---" for line in body):
        raise ValidationError("§9 内に --- 行を置けません")
    if any(line.lstrip().startswith("###") for line in body):
        raise ValidationError("§9 内に追加の ### 行を置けません")
    blockquotes = [line for line in body if line.strip().startswith(">")]
    if len(blockquotes) > 1:
        raise ValidationError("§9 の > 行は 0 または 1 行です")
    pipe_indexes = [index for index, line in enumerate(body) if line.strip().startswith("|")]
    if not pipe_indexes:
        raise ValidationError("§9 の技術スタック表がありません")
    if pipe_indexes != list(range(pipe_indexes[0], pipe_indexes[-1] + 1)):
        raise ValidationError("§9 の行頭パイプ行は単一の連続表にしてください")
    rows: List[List[str]] = []
    for index in pipe_indexes:
        line = body[index].strip()
        if not line.endswith("|"):
            raise ValidationError("§9 の表行は終端パイプが必要です")
        cells = _split_table_row(line)
        if len(cells) != 4:
            raise ValidationError("§9 の表は全行ちょうど 4 セル必要です")
        if any('"' in cell and "'" in cell for cell in cells):
            raise ValidationError("§9 の同一セルに二種類の引用符を併用できません")
        rows.append(cells)
    if rows[0] != ["レイヤ", "技術", "バージョン方針", "備考"]:
        raise ValidationError("§9 のヘッダが契約と一致しません")
    if len(rows) < 3 or not all(cell and set(cell) <= set("-: ") for cell in rows[1]):
        raise ValidationError("§9 の separator またはデータ行が不足しています")
    data_rows = rows[2:]
    if not data_rows:
        raise ValidationError("§9 はデータ行を 1 件以上必要とします")
    for cells in data_rows:
        layer, technology, policy, _note = cells
        if not layer or not technology or "レイヤ" in layer:
            raise ValidationError("§9 のレイヤ・技術列が不正です")
        if "観測" in policy:
            raise ValidationError("§9 のバージョン方針列に 観測 を置けません")
        if not (policy == "[要確認]" or policy == "—" or re.fullmatch(r"宣言:\s*\S.*", policy)):
            raise ValidationError("§9 のバージョン方針列が契約外です")


def _tracked_files(source_root: Path) -> Set[str]:
    try:
        result = _safe_git(
            source_root,
            ["ls-files", "-z"],
            git_executable="git",
            env=None,
        )
    except InspectionError as exc:
        raise ValidationError("source root の tracked files を取得できません", 2) from exc
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }


def _is_excluded(path: PurePosixPath) -> bool:
    parts = path.parts
    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return True
    name = parts[-1]
    lower_name = name.lower()
    if lower_name in EXCLUDED_FILE_NAMES:
        return True
    if any(lower_name.startswith(prefix) for prefix in EXCLUDED_FILE_PREFIXES):
        return True
    if any(lower_name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return True
    return PurePosixPath(lower_name).suffix in BINARY_EXTENSIONS


def is_excluded_evidence_path(path: PurePosixPath) -> bool:
    """survey など他 helper が同じ除外規則を共有するための公開入口。"""
    return _is_excluded(path)


def _validate_evidence_path_syntax(evidence: Sequence[Evidence]) -> None:
    for item in evidence:
        value = item.path
        if (
            not value
            or "\x00" in value
            or "\\" in value
            or value.startswith(("/", "~"))
            or re.match(r"^[A-Za-z]:", value)
        ):
            raise ValidationError("evidence は安全な相対 POSIX path 必須です")
        pure = PurePosixPath(value)
        if pure.is_absolute() or ".." in pure.parts or "." in pure.parts or _is_excluded(pure):
            raise ValidationError("evidence path が許可範囲外です")


def _validate_evidence_files(
    evidence: Sequence[Evidence],
    source_root: Path,
    tracked: Set[str],
) -> None:
    root_real = os.path.realpath(source_root)
    for item in evidence:
        value = item.path
        pure = PurePosixPath(value)
        if value not in tracked:
            raise ValidationError("evidence は tracked file との完全一致が必要です")
        current = source_root
        try:
            for component in pure.parts:
                current = current / component
                metadata = os.lstat(current)
                if stat.S_ISLNK(metadata.st_mode):
                    raise ValidationError("evidence の経路に symlink を使用できません")
        except OSError as exc:
            raise ValidationError("evidence file を安全に参照できません") from exc
        if os.path.commonpath((root_real, os.path.realpath(current))) != root_real:
            raise ValidationError("evidence file が source root 外です")
        if not stat.S_ISREG(os.lstat(current).st_mode):
            raise ValidationError("evidence は通常ファイル必須です")


def _validate_provenance(frontmatter: Frontmatter, inspection: RepositoryInspection) -> None:
    if (
        frontmatter.status != "reverse-draft"
        or frontmatter.source_repository != inspection.source_repository
        or frontmatter.source_ref != inspection.source_ref
        or frontmatter.source_revision != inspection.source_revision
    ):
        raise ValidationError("frontmatter の来歴が現在の worktree と一致しません")


def _validate_non_inclusion(text: str, inspection: RepositoryInspection) -> None:
    forbidden_values = {
        inspection.source_root,
        inspection.source_root_realpath,
    }
    home = os.path.expanduser("~")
    if home != "/":
        forbidden_values.add(home)
    if inspection.raw_origin != inspection.source_repository:
        forbidden_values.add(inspection.raw_origin)
    if any(value and value in text for value in forbidden_values):
        raise ValidationError("設計書にローカル path または raw origin が混入しています")
    if re.search(r"(?:git@github\.com:|ssh://)", text, re.IGNORECASE):
        raise ValidationError("設計書に SSH URL が混入しています")
    if re.search(r"://[^/\s:@]+(?::[^/\s@]*)?@", text):
        raise ValidationError("設計書に userinfo 付き URL が混入しています")
    prefixes = ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_", "AKIA", "-----BEGIN ")
    if any(prefix in text for prefix in prefixes):
        raise ValidationError("設計書に credential token の疑いがある値が混入しています")


def review_counts(text: str) -> Tuple[int, int, int, int]:
    """mask 後の有効な本文からレビュー用件数を数える。"""
    masked, _fenced_lines = _mask_markdown(text.splitlines())
    return (
        sum(1 for line in masked if "宣言:" in line),
        sum(line.count("[要確認]") for line in masked),
        sum(1 for line in masked if "該当なし:" in line),
        len(_extract_evidence(masked)),
    )


def validate_text(
    text: str,
    *,
    source_root: str | None = None,
    syntax_only: bool = False,
    quality: bool = True,
    survey_dir: str | None = None,
    profile: str = "auto",
) -> ValidationResult:
    lines = text.splitlines()
    frontmatter = _parse_frontmatter(lines)
    masked, fenced_lines = _mask_markdown(lines)
    section_lines, appendix_lines = _validate_structure(masked, frontmatter.end_line)
    section_ranges, appendix_ranges = _body_ranges(masked, section_lines, appendix_lines)
    evidence = _extract_evidence(masked)
    _validate_evidence_path_syntax(evidence)
    _validate_bodies(masked, section_ranges, appendix_ranges, evidence)
    _validate_section9(lines, section_ranges, fenced_lines)

    ledger: List[dq.LedgerRow] = []
    if quality and syntax_only:
        selected = dq.select_profile("standard" if profile == "auto" else profile, None)
        try:
            ledger = dq.validate_text_quality(
                masked, lines, fenced_lines, section_ranges, appendix_ranges,
                {item.line_number - 1 for item in evidence}, selected, EVIDENCE_TOKEN_RE,
            )
        except dq.QualityError as exc:
            raise ValidationError(str(exc)) from exc
    if syntax_only:
        return ValidationResult(frontmatter, None, len(evidence))
    if source_root is None:
        raise ValidationError("--source-root は必須です", 2)
    if quality and survey_dir is None:
        raise ValidationError("--survey-dir は必須です（全量読解の survey を先に実行し、check を通してください）", 2)
    try:
        inspection = inspect_repository(source_root)
    except InspectionError as exc:
        raise ValidationError(str(exc), exc.code) from exc
    _validate_provenance(frontmatter, inspection)
    _validate_non_inclusion(text, inspection)
    tracked = _tracked_files(Path(source_root))
    _validate_evidence_files(evidence, Path(source_root), tracked)
    if quality:
        assert survey_dir is not None
        try:
            from survey_repository import load_inventory_stats

            stats = load_inventory_stats(survey_dir)
        except (OSError, ValueError, KeyError) as exc:
            raise ValidationError("survey の inventory.json を読み取れません（survey を先に実行してください）", 2) from exc
        selected = dq.select_profile(profile, stats["readable"])
        try:
            ledger = dq.validate_text_quality(
                masked, lines, fenced_lines, section_ranges, appendix_ranges,
                {item.line_number - 1 for item in evidence}, selected, EVIDENCE_TOKEN_RE,
            )
            dq.verify_evidence_ranges_and_quotes(
                Path(source_root), ledger, [(item.path, item.fragment) for item in evidence]
            )
            dq.validate_coverage_line(masked, survey_dir, source_root)
        except dq.QualityError as exc:
            raise ValidationError(str(exc)) from exc
    return ValidationResult(frontmatter, inspection, len(evidence))


def validate_bytes(
    document_bytes: bytes,
    *,
    source_root: str | None = None,
    syntax_only: bool = False,
    quality: bool = True,
    survey_dir: str | None = None,
    profile: str = "auto",
) -> ValidationResult:
    try:
        text = document_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("設計書は UTF-8 必須です", 2) from exc
    return validate_text(
        text,
        source_root=source_root,
        syntax_only=syntax_only,
        quality=quality,
        survey_dir=survey_dir,
        profile=profile,
    )


def validate_document(
    document_path: str,
    *,
    source_root: str | None = None,
    syntax_only: bool = False,
    quality: bool = True,
    survey_dir: str | None = None,
    profile: str = "auto",
) -> ValidationResult:
    try:
        document_bytes = Path(document_path).read_bytes()
    except OSError as exc:
        raise ValidationError("設計書を読み取れません", 2) from exc
    return validate_bytes(
        document_bytes,
        source_root=source_root,
        syntax_only=syntax_only,
        quality=quality,
        survey_dir=survey_dir,
        profile=profile,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document")
    parser.add_argument("--source-root")
    parser.add_argument("--syntax-only", action="store_true")
    parser.add_argument("--survey-dir", help="survey_repository.py survey の出力先（品質検査と調査範囲照合に必須）")
    parser.add_argument("--profile", choices=("auto", "standard", "compact"), default="auto")
    parser.add_argument(
        "--structure-only",
        action="store_true",
        help="本文品質（B 水準）を検査しない旧契約。構造・来歴・証跡の存在だけを見る。publish には使えない",
    )
    args = parser.parse_args(argv)
    if args.syntax_only and args.source_root is not None:
        print("[validate_design_doc] ERROR: --syntax-only は来歴引数と併用できません", file=sys.stderr)
        return 2
    try:
        result = validate_document(
            args.document,
            source_root=args.source_root,
            syntax_only=args.syntax_only,
            quality=not args.structure_only,
            survey_dir=args.survey_dir,
            profile=args.profile,
        )
    except ValidationError as exc:
        print(f"[validate_design_doc] ERROR: {exc}", file=sys.stderr)
        return exc.code
    print(f"[validate_design_doc] PASS: evidence={result.evidence_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
