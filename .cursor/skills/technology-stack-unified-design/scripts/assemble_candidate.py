#!/usr/bin/env python3
"""部品ディレクトリの *.md を結合し、候補文書を組み立てて台帳同期と検証まで行う。

部品の規約（ファイル名の昇順に結合する）:
  00-*.md   導入部。`# タイトル` と導入の箇条書き。調査範囲行は `{{COVERAGE}}` と書く（survey check の値で置換する）
  以降      `## Part N: ...` / `### N. ...` / `## Appendix` / `### Appendix X: ...` を含む本文。境界の `---` は部品側に書く
frontmatter・調査範囲行・`## 目次`（番号付きリンク）はこのスクリプトが自動生成する。
Appendix B には空の台帳表（ヘッダ行と区切り行）を置く。`[[path#L行 :: 主張]]` マーカーと `[E<n>]` は
collect_ledger.py sync で台帳へ解決される（ledger-candidates.json がある場合に実行）。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collect_ledger as ledger_mod  # noqa: E402
import inspect_local_repository as inspect_mod  # noqa: E402
import survey_repository as survey_mod  # noqa: E402
import validate_design_doc as validate_mod  # noqa: E402

PLACEHOLDER = "{{COVERAGE}}"


class AssembleError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def build_toc(body: str) -> str:
    toc: List[str] = ["## 目次", ""]
    for line in body.split("\n"):
        part = re.match(r"^##\s+Part\s+(\d)", line)
        if part:
            toc.extend(["", f"### Part {part.group(1)}"])
            continue
        if re.match(r"^##\s+Appendix\s*$", line):
            toc.extend(["", "### Appendix"])
            continue
        section = re.match(r"^###\s+(\d+)\.\s*(.*)$", line)
        if section:
            toc.append(f"{section.group(1)}. [{section.group(2)}]({validate_mod._heading_anchor(line[4:])})")
            continue
        appendix = re.match(r"^###\s+(Appendix\s+([A-E])(?:\s*[:：].*)?)\s*$", line)
        if appendix:
            toc.append(f"* [{appendix.group(1)}]({validate_mod._heading_anchor(line[4:])})")
    text = "\n".join(toc)
    return text.replace("## 目次\n\n\n### Part 1", "## 目次\n\n### Part 1")


def assemble(
    parts_dir: str,
    source_root: str,
    survey_dir: str,
    out: str,
    *,
    title: str,
    slug: str,
    generated_at: Optional[str] = None,
    validate: bool = True,
) -> str:
    parts = [p for p in sorted(Path(parts_dir).glob("[0-9]*.md"))]
    if len(parts) < 2:
        raise AssembleError("部品が不足しています（00-*.md の導入部と本文の部品が必要です）", 2)
    texts = [p.read_text(encoding="utf-8").rstrip("\n") for p in parts]
    if PLACEHOLDER not in texts[0]:
        raise AssembleError(f"導入部（{parts[0].name}）に {PLACEHOLDER} がありません")
    try:
        inspection = inspect_mod.inspect_repository(source_root)
        coverage = survey_mod.check_survey(survey_dir, source_root).line()
    except (inspect_mod.InspectionError, survey_mod.SurveyError) as exc:
        raise AssembleError(str(exc), getattr(exc, "code", 1)) from exc
    intro = texts[0].replace(PLACEHOLDER, coverage)
    body = "\n\n".join(texts[1:])
    front = "\n".join(
        [
            "---",
            "status: reverse-draft",
            f"title: {json.dumps(title, ensure_ascii=False)}",
            f"generated_at: {json.dumps(generated_at or datetime.date.today().isoformat())}",
            f"source_repository: {json.dumps(inspection.source_repository, ensure_ascii=False)}",
            f"source_ref: {json.dumps(inspection.source_ref, ensure_ascii=False)}",
            f"source_revision: {json.dumps(inspection.source_revision)}",
            f"stack_slug: {json.dumps(slug)}",
            "---",
            "",
        ]
    )
    text = front + intro + "\n\n---\n\n" + build_toc(body) + "\n\n---\n\n" + body + "\n"
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    if (Path(survey_dir) / "ledger-candidates.json").is_file() or ledger_mod.MARKER_RE.search(text):
        try:
            ledger_mod.sync(os.fspath(out_path), survey_dir, source_root)
        except ledger_mod.LedgerError as exc:
            raise AssembleError(str(exc)) from exc
    if validate:
        try:
            validate_mod.validate_document(os.fspath(out_path), source_root=source_root, survey_dir=survey_dir)
        except validate_mod.ValidationError as exc:
            raise AssembleError(str(exc), exc.code) from exc
    return os.fspath(out_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parts-dir", default="tmp/draft")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--survey-dir", default="tmp/tech-stack-survey")
    parser.add_argument("--out", default="tmp/tech-stack-reverse-candidate.md")
    parser.add_argument("--title", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--generated-at")
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = assemble(
            args.parts_dir, args.source_root, args.survey_dir, args.out,
            title=args.title, slug=args.slug, generated_at=args.generated_at, validate=not args.no_validate,
        )
    except AssembleError as exc:
        print(f"[assemble_candidate] ERROR: {exc}", file=sys.stderr)
        return exc.code
    print(f"[assemble_candidate] PASS: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
