#!/usr/bin/env python3
"""shard note の `## 証跡候補` を集め、逐語検証済みの台帳候補を作る / 候補文書の台帳を同期する。

`collect` : 全 note の証跡候補を検証し、ID を安定採番して ledger-candidates.md / .json を書く。
`sync`    : `[[path#L行 :: 主張]]` マーカーを `[E<n>]` へ解決し（候補に無ければ実ファイルの行から逐語引用を作る）、
            参照されている `[E<n>]` だけを Appendix B の台帳表へ書き出す（未参照行は除く）。

対象 worktree には書き込まない。検証できない候補（実在しない path・範囲外・非逐語）は捨てて報告する。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import document_quality as dq  # noqa: E402
from validate_design_doc import _is_excluded, _tracked_files  # noqa: E402

CANDIDATE_RE = re.compile(r"^(?P<path>[^#\s`]+)(?P<fragment>#L\d+(?:-L\d+)?)?$")
SECTION_RE = re.compile(r"^## 証跡候補\s*$")
LEDGER_HEADER_LINE = "| ID | 証跡 | 引用 | 裏付け |"
MARKER_RE = re.compile(r"\[\[(?P<path>[^\]#:\s]+)(?P<fragment>#L\d+(?:-L\d+)?)?(?:\s*::\s*(?P<claim>[^\]]+))?\]\]")
SECTION_HEADING_RE = re.compile(r"^###\s+(?:(\d+)\.|Appendix\s+([A-E]))")


class LedgerError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _cells(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_candidates(note_text: str) -> List[Tuple[str, Optional[str], str, str]]:
    rows: List[Tuple[str, Optional[str], str, str]] = []
    in_section = False
    for line in note_text.splitlines():
        if line.startswith("## "):
            in_section = bool(SECTION_RE.match(line))
            continue
        if not in_section or not line.strip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 3 or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell):
            continue
        if cells[0].lower().startswith(("path", "証跡")) or cells[0] in ("ID", "id"):
            continue
        first = cells[0].replace("evidence:", "").strip().strip("`").strip()
        match = CANDIDATE_RE.match(first)
        if match is None:
            continue
        quote = cells[1].strip()
        if len(quote) >= 2 and quote[0] == "`" and quote[-1] == "`":
            quote = quote[1:-1].strip()
        claim = " ".join(cell for cell in cells[2:] if cell).replace("|", "¦")
        rows.append((match.group("path"), match.group("fragment"), quote, claim))
    return rows


def verify_candidate(source_root: Path, tracked: set, path: str, fragment: Optional[str], quote: str) -> Optional[str]:
    """問題があれば理由を返す。"""
    pure = PurePosixPath(path)
    if path not in tracked:
        return "tracked file ではない"
    if pure.is_absolute() or ".." in pure.parts or _is_excluded(pure):
        return "除外対象または不正な path"
    if "`" in quote or "|" in quote or not (dq.MIN_QUOTE_CHARS <= len(quote) <= dq.MAX_QUOTE_CHARS):
        return "引用が不正（長さ・`|`・バッククォート）"
    row = dq.LedgerRow(0, path, fragment, quote, "-", 0)
    try:
        dq.verify_evidence_ranges_and_quotes(source_root, [row], [(path, fragment)])
    except dq.QualityError as exc:
        return str(exc)
    return None


def collect(source_root: str, survey_dir: str) -> Dict[str, int]:
    root = Path(source_root)
    directory = Path(survey_dir)
    tracked = _tracked_files(root)
    json_path = directory / "ledger-candidates.json"
    existing: Dict[str, dict] = {}
    if json_path.is_file():
        existing = json.loads(json_path.read_text(encoding="utf-8"))
    next_id = max((entry["id"] for entry in existing.values()), default=0) + 1
    accepted = rejected = 0
    reasons: List[str] = []
    sources: List[Tuple[str, List[Tuple[str, Optional[str], str, str]]]] = [
        (note.name, parse_candidates(note.read_text(encoding="utf-8")))
        for note in sorted((directory / "notes").glob("*.note.md"))
    ]
    for origin, candidates in sources:
        for path, fragment, quote, claim in candidates:
            key = f"{path}{fragment or ''}\t{quote}"
            if key in existing:
                continue
            problem = verify_candidate(root, tracked, path, fragment, quote)
            if problem is not None:
                rejected += 1
                reasons.append(f"{origin}: {path}{fragment or ''}: {problem}")
                continue
            existing[key] = {"id": next_id, "path": path, "fragment": fragment, "quote": quote, "claim": claim, "note": origin}
            next_id += 1
            accepted += 1
    json_path.write_text(json.dumps(existing, ensure_ascii=False, indent=0), encoding="utf-8")
    lines = [LEDGER_HEADER_LINE, "| --- | --- | --- | --- |"]
    for entry in sorted(existing.values(), key=lambda item: item["id"]):
        lines.append(
            f"| E{entry['id']} | evidence: {entry['path']}{entry['fragment'] or ''} | `{entry['quote']}` | {entry['claim']} |"
        )
    (directory / "ledger-candidates.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (directory / "ledger-rejected.txt").write_text("\n".join(reasons) + "\n", encoding="utf-8")
    return {"total": len(existing), "accepted": accepted, "rejected": rejected}


def _ledger_span(lines: Sequence[str]) -> Tuple[int, int]:
    """Appendix B 配下の台帳表（ヘッダ行〜表末尾）の [start, end) を返す。"""
    in_b = False
    start = -1
    for index, line in enumerate(lines):
        if re.match(r"^###\s+Appendix\s+B\b", line):
            in_b = True
            continue
        if in_b and re.match(r"^###\s+Appendix\s+[C-E]\b", line):
            break
        if in_b and line.strip() == LEDGER_HEADER_LINE:
            start = index
            end = index + 1
            while end < len(lines) and lines[end].strip().startswith("|"):
                end += 1
            return start, end
    raise LedgerError("Appendix B に台帳ヘッダ行（| ID | 証跡 | 引用 | 裏付け |）がありません")


def _derive_quote(source_root: Path, path: str, fragment: str) -> str:
    """指定行範囲の最初の非空行から、`|` とバッククォートを含まない逐語の部分文字列を作る。"""
    match = dq.FRAGMENT_RE.search(fragment)
    assert match is not None
    first = int(match.group(1))
    last = int(match.group(2) or match.group(1))
    lines = (source_root / path).read_text(encoding="utf-8", errors="replace").split("\n")
    for line in lines[first - 1 : last]:
        text = line.strip()
        if not text:
            continue
        segments = [segment.strip() for segment in re.split(r"[|`]", text) if segment.strip()]
        best = max(segments, key=len, default="")
        quote = best[: dq.MAX_QUOTE_CHARS - 20].strip()
        if len(quote) >= dq.MIN_QUOTE_CHARS:
            return quote
    raise LedgerError(f"{path}{fragment} から引用を作れません（空行のみ、または短すぎます）")


def resolve_markers(text: str, source_root: Path, directory: Path) -> str:
    """`[[path#L行 :: 主張]]` を `[E<n>]` へ置換する。候補に無ければ実ファイルの行から逐語引用を作って採番する。"""
    json_path = directory / "ledger-candidates.json"
    existing: Dict[str, dict] = json.loads(json_path.read_text(encoding="utf-8")) if json_path.is_file() else {}
    by_location: Dict[str, int] = {}
    by_location_claim: Dict[Tuple[str, str], int] = {}
    quotes: Dict[str, str] = {}
    for entry in existing.values():
        location = f"{entry['path']}{entry['fragment'] or ''}"
        by_location.setdefault(location, entry["id"])
        by_location_claim[(location, entry["claim"])] = entry["id"]
        quotes.setdefault(location, entry["quote"])
    next_id = max((entry["id"] for entry in existing.values()), default=0) + 1
    tracked = _tracked_files(source_root)
    section = "?"
    out_lines: List[str] = []
    for line in text.split("\n"):
        heading = SECTION_HEADING_RE.match(line)
        if heading:
            section = heading.group(1) or f"Appendix {heading.group(2)}"
        if line.strip().startswith("|") and ("| ID |" in line or re.match(r"^\|\s*E\d+\s*\|", line)):
            out_lines.append(line)
            continue

        def replace(match: "re.Match[str]") -> str:
            nonlocal next_id
            path, fragment = match.group("path"), match.group("fragment")
            if fragment is None:
                raise LedgerError(f"[[{path}]] には #L<行> が必要です")
            location = f"{path}{fragment}"
            explicit = match.group("claim")
            if explicit is None and location in by_location:
                return f"[E{by_location[location]}]"
            claim = (explicit or f"§{section} の根拠").strip().replace("|", "¦")
            if (location, claim) in by_location_claim:
                return f"[E{by_location_claim[(location, claim)]}]"
            quote = quotes.get(location) or (_derive_quote(source_root, path, fragment) if path in tracked else "")
            problem = verify_candidate(source_root, tracked, path, fragment, quote)
            if problem is not None:
                raise LedgerError(f"[[{location}]] を台帳化できません: {problem}")
            entry_id = next_id
            next_id += 1
            existing[f"{location}\t{quote}\t{claim}"] = {"id": entry_id, "path": path, "fragment": fragment, "quote": quote, "claim": claim, "note": "marker"}
            by_location.setdefault(location, entry_id)
            by_location_claim[(location, claim)] = entry_id
            quotes.setdefault(location, quote)
            return f"[E{entry_id}]"

        out_lines.append(MARKER_RE.sub(replace, line))
    json_path.write_text(json.dumps(existing, ensure_ascii=False, indent=0), encoding="utf-8")
    return "\n".join(out_lines)


def sync(document: str, survey_dir: str, source_root: Optional[str] = None) -> Dict[str, int]:
    directory = Path(survey_dir)
    text = Path(document).read_text(encoding="utf-8")
    if source_root is not None and MARKER_RE.search(text):
        text = resolve_markers(text, Path(source_root), directory)
    entries = {f"E{entry['id']}": entry for entry in json.loads((directory / "ledger-candidates.json").read_text(encoding="utf-8")).values()}
    lines = text.split("\n")
    start, end = _ledger_span(lines)
    body = "\n".join(lines[:start] + lines[end:])
    referenced = sorted({int(number) for number in dq.REF_RE.findall(body)})
    unknown = [number for number in referenced if f"E{number}" not in entries]
    if unknown:
        raise LedgerError("台帳候補に無い参照があります: " + ", ".join(f"[E{n}]" for n in unknown[:10]))
    table = [LEDGER_HEADER_LINE, "| --- | --- | --- | --- |"]
    for number in referenced:
        entry = entries[f"E{number}"]
        table.append(f"| E{number} | evidence: {entry['path']}{entry['fragment'] or ''} | `{entry['quote']}` | {entry['claim']} |")
    lines[start:end] = table
    Path(document).write_text("\n".join(lines), encoding="utf-8")
    return {"ledger_rows": len(referenced)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect_parser = sub.add_parser("collect")
    collect_parser.add_argument("--source-root", required=True)
    collect_parser.add_argument("--survey-dir", default="tmp/tech-stack-survey")
    sync_parser = sub.add_parser("sync")
    sync_parser.add_argument("document")
    sync_parser.add_argument("--survey-dir", default="tmp/tech-stack-survey")
    sync_parser.add_argument("--source-root", help="[[path#L行]] マーカーを台帳化するために必要")
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            result = collect(args.source_root, args.survey_dir)
            print(f"[collect_ledger] PASS: total={result['total']} accepted={result['accepted']} rejected={result['rejected']}")
        else:
            result = sync(args.document, args.survey_dir, args.source_root)
            print(f"[collect_ledger] PASS: ledger_rows={result['ledger_rows']}")
    except (LedgerError, OSError, ValueError, KeyError) as exc:
        print(f"[collect_ledger] ERROR: {exc}", file=sys.stderr)
        return getattr(exc, "code", 2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
