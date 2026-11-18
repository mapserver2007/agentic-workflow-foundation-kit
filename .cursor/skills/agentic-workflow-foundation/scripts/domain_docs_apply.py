#!/usr/bin/env python3
"""Design Doc 由来の Domain docs 本文を、結果ファイルから決定論的に適用する。

domain-docs スキルの subagent は docs を直接編集せず、`tmp/domain-docs-result.yaml`
だけを返す。本スクリプトが所有権表・根拠見出し・整合性を検証し、全ファイルを atomic に書く。

使い方:
  domain_docs_apply.py state [--refresh]
      Design Doc の検知・状態判定・対象節の列挙。`tmp/domain-docs-targets.yaml` を書く。
  domain_docs_apply.py apply
      fill-only で適用する。本文が器と完全一致する節だけを埋める。
      `docs/api.md` の契約節（`domain_docs.api_sections`）は、kit の引用を残して `[TODO]` だけを置き換える。
  domain_docs_apply.py apply --refresh
      埋め済みの節との diff と plan digest を表示する（書込みなし）。
  domain_docs_apply.py apply --refresh --approve <digest>
      承認済みの計画だけを適用する。
  domain_docs_apply.py apply --refresh --decline
      docs を変更せず、現在の Design Doc を既読にする（fingerprint のみ更新）。
  domain_docs_apply.py pin
      root manifest の design_doc ブロックを2キーで書く（旧形式の移行にも使う）。

exit code:
  0 = 成功 / 対象なし / refresh の計画表示
  1 = 検証失敗（結果ファイルを直して再実行する）
  2 = 致命的（入力が曖昧・消失、書込み失敗）
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ENGINE_DIR = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(HERE))
import generate  # noqa: E402
import genlib  # noqa: E402
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from yaml_emitter import dump_yaml, dump_yaml_text  # noqa: E402

SKILL_DIR = HERE.parent
SEED_MANIFEST = SKILL_DIR / "manifest.yaml"
TEMPLATES_DIR = SKILL_DIR / "templates"

DESIGN_DOC_PATHS = (
    Path("designs/docs/designdoc.md"),
    Path("designs/docs/design-doc.md"),
)
TARGETS_RELATIVE = "tmp/domain-docs-targets.yaml"
RESULT_RELATIVE = "tmp/domain-docs-result.yaml"
SPEC_PATH = "docs/spec.md"
README_PATH = "docs/spec/README.md"
SPEC_DIR = "docs/spec"
SCHEMA_VERSION = 1

# domain-docs が書ける節（`## ` を除いた見出し名）。表に無い節への書込みは拒否する。
OWNERSHIP: dict[str, tuple[str, ...]] = {
    "docs/spec.md": (
        "目的と背景",
        "ドメイン用語集",
        "システム境界",
        "不変の設計原則 (MUST)",
        "機能仕様",
        "非機能要件",
        "変更に強い点・弱い点",
    ),
    "docs/spec/README.md": ("収録仕様",),
    "docs/architecture.md": (
        "システム全体構成",
        "ディレクトリ/モジュール責務",
        "主要コンポーネント詳細",
        "依存関係方針",
    ),
    "docs/api.md": (
        "API設計概要",
        "エンドポイント一覧",
        "エラーハンドリング",
        "API 詳細",
    ),
    "docs/data-models.md": (
        "データベース設計思想",
        "主要テーブル/コレクション構成",
        "データアクセスパターン",
    ),
    "docs/workflows.md": (
        "主要ユースケースの処理フロー",
        "エラーハンドリング・リトライパターン",
        "状態管理・状態遷移",
    ),
}

# 契約節（placeholder）を埋められるファイル。このファイルの器にある `domain_docs.api_sections` の節
# （title が完全一致するもの。`api_section_titles`）だけを対象にする。
# data-models.md / workflows.md の契約節は、従来どおり書込みを拒否する。
PLACEHOLDER_FILES = frozenset({"docs/api.md"})
# kit の器が描く契約節の形: 見出し、引用段落（`> guidance`）、単独行の `[TODO]`。
PLACEHOLDER_SECTION_RE = re.compile(
    r"\A## [^\n]+\n\n(?P<quote>>[^\n]*(?:\n[^\n]+)*)\n\n\[TODO\]\n*\Z"
)

ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_SLUGS = frozenset({"readme"})
HEX64 = re.compile(r"[0-9a-f]{64}")
SECTION_KEYS = frozenset({"file", "heading", "body", "evidence"})
OMISSION_KEYS = frozenset({"file", "heading", "reason"})
SPEC_FILE_KEYS = frozenset({"slug", "title", "summary", "evidence", "body"})
RESULT_KEYS = frozenset({"schema_version", "sections", "omissions", "spec_files"})
ROW_RE = re.compile(
    r"^- \[(?P<title>[^\]]+)\]\((?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md\)"
    r"(?: — (?P<summary>.*?))?"
    r"(?:（根拠: `(?P<evidence>[^`]+)`）)?\s*$"
)
SPEC_LINK_RE = re.compile(r"\]\(spec/([a-z0-9]+(?:-[a-z0-9]+)*)\.md\)")


class ApplyError(Exception):
    """結果ファイル・状態の検証失敗。結果ファイルを直して再実行できる（exit 1）。"""


class FatalError(Exception):
    """入力の曖昧・消失・書込み失敗など（exit 2）。"""


@dataclass
class Plan:
    writes: dict[str, bytes] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    diffs: list[str] = field(default_factory=list)
    digest: str = ""


# --------------------------------------------------------------------------
# 入出力の基本部品
# --------------------------------------------------------------------------
def _read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _load_yaml(path: Path, error: type[Exception]) -> dict:
    try:
        loaded = genlib.load_manifest(str(path))
    except (OSError, genlib.YamlError, UnicodeDecodeError) as exc:
        raise error(f"YAML 読み込み失敗 ({path.name}): {exc}") from exc
    if not isinstance(loaded, dict):
        raise error(f"YAML root は mapping である必要があります: {path.name}")
    return loaded


def _safe_path(root: Path, rel: str, label: str) -> Path:
    try:
        return Path(generate._safe_join(str(root), rel, label))
    except genlib.YamlError as exc:
        raise ApplyError(str(exc)) from exc


def _write_bytes(path: Path, payload: bytes) -> None:
    rp._atomic_write_bytes(path, payload)


def _heading_name(heading_line: str) -> str:
    return heading_line[3:].strip()


def heading_names(design_doc: Path) -> set[str]:
    """Design Doc の ATX 見出しの本文を返す。コードフェンス内は見出しとして数えない。"""
    try:
        text = design_doc.read_text(encoding="utf-8")
    except OSError as exc:
        raise FatalError(f"Design Doc 読み込み失敗: {exc}") from exc
    lines = text.splitlines(keepends=True)
    mask = generate._fence_mask(lines)
    headings = set()
    for line, inside in zip(lines, mask):
        if inside:
            continue
        match = ATX_HEADING.match(line.rstrip("\r\n"))
        if match:
            headings.add(match.group(1).strip())
    return headings


# --------------------------------------------------------------------------
# root manifest の design_doc ブロック（source_path / source_fingerprint の2キー）
# --------------------------------------------------------------------------
def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_top_level_key_line(line: str) -> bool:
    stripped = line.rstrip("\r\n")
    if not stripped.strip() or _line_indent(stripped) != 0:
        return False
    if stripped.startswith("#"):
        return False
    key, separator, _ = stripped.partition(":")
    key = key.strip()
    return bool(separator) and bool(key) and not key.startswith("- ")


def _find_top_level_block_span(raw: bytes, key: str) -> tuple[int, int] | None:
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    offset = 0
    start = None
    for line in lines:
        if line.startswith(f"{key}:") and _line_indent(line.rstrip("\r\n")) == 0:
            start = offset
            break
        offset += len(line.encode("utf-8"))
    if start is None:
        return None
    offset = 0
    for line in lines:
        line_start = offset
        offset += len(line.encode("utf-8"))
        if line_start <= start:
            continue
        if _is_top_level_key_line(line):
            return start, line_start
    return start, len(raw)


def pinned_manifest_bytes(manifest_path: Path, source_path: str, fingerprint: str) -> bytes:
    """root manifest の design_doc ブロックを2キーへ置換した全文を返す（他のキーは保持）。"""
    raw = manifest_path.read_bytes()
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    block = {"design_doc": {"source_path": source_path, "source_fingerprint": fingerprint}}
    replacement = newline.join(line.encode("utf-8") for line in dump_yaml(block)) + newline
    span = _find_top_level_block_span(raw, "design_doc")
    if span is None:
        if raw and not raw.endswith((b"\n", b"\r\n")):
            raw += newline
        new_raw = raw + replacement
    else:
        new_raw = raw[: span[0]] + replacement + raw[span[1]:]
    try:
        parsed = genlib.parse_yaml(new_raw.decode("utf-8"))
    except (UnicodeDecodeError, genlib.YamlError) as exc:
        raise FatalError(f"pin 後 manifest の解析に失敗しました: {exc}") from exc
    loaded = parsed.get("design_doc") if isinstance(parsed, dict) else None
    if loaded != block["design_doc"]:
        raise FatalError("pin round-trip で design_doc が一致しません")
    return new_raw


# --------------------------------------------------------------------------
# Design Doc の検知と状態判定
# --------------------------------------------------------------------------
def detect_design_doc(root: Path) -> Path | None:
    matches = [root / rel for rel in DESIGN_DOC_PATHS if (root / rel).is_file()]
    if len(matches) > 1:
        joined = ", ".join(path.relative_to(root).as_posix() for path in matches)
        raise FatalError(f"Design Doc が複数存在します: {joined}")
    return matches[0] if matches else None


def design_doc_state(root: Path, manifest_path: Path) -> tuple[Path | None, str]:
    """(Design Doc, 状態) を返す。状態は none / unpinned / fresh / stale。"""
    doc = detect_design_doc(root)
    manifest = _load_yaml(manifest_path, FatalError) if manifest_path.is_file() else {}
    pinned = manifest.get("design_doc")
    if doc is None:
        if pinned is not None:
            raise FatalError("固定済み design_doc の入力ファイルが消失しています")
        return None, "none"
    if pinned is None:
        return doc, "unpinned"
    if not isinstance(pinned, dict):
        raise FatalError("manifest.design_doc は mapping である必要があります")
    relative = doc.relative_to(root).as_posix()
    if pinned.get("source_path") != relative:
        raise FatalError(
            f"design_doc.source_path {pinned.get('source_path')!r} が検出済みパス {relative!r} と一致しません"
        )
    fingerprint = pinned.get("source_fingerprint")
    if not isinstance(fingerprint, str) or not HEX64.fullmatch(fingerprint):
        raise FatalError("design_doc.source_fingerprint が不正です")
    return doc, ("fresh" if fingerprint == tc.source_fingerprint(doc) else "stale")


# --------------------------------------------------------------------------
# 器（kit テンプレートの描画結果）と節の解析
# --------------------------------------------------------------------------
def render_skeletons(manifest_path: Path) -> dict[str, str]:
    """所有権表のファイルについて、kit が書く器（投影なしの描画結果）を返す。"""
    import run_resolved_engine as resolver  # noqa: WPS433

    manifest = resolver.resolved_manifest(str(SEED_MANIFEST), str(manifest_path))
    skeletons: dict[str, str] = {}
    for out in manifest.get("outputs") or []:
        rel = out.get("path")
        if rel in OWNERSHIP:
            template = (TEMPLATES_DIR / out["template"]).read_text(encoding="utf-8")
            skeletons[rel] = genlib.render(template, manifest)
    return skeletons


def api_section_titles(manifest_path: Path) -> frozenset[str]:
    """契約（`domain_docs.api_sections`）が宣言する節の見出し名を返す。"""
    import run_resolved_engine as resolver  # noqa: WPS433

    manifest = resolver.resolved_manifest(str(SEED_MANIFEST), str(manifest_path))
    sections = (manifest.get("domain_docs") or {}).get("api_sections") or []
    return frozenset(
        item["title"] for item in sections if isinstance(item, dict) and isinstance(item.get("title"), str)
    )


def placeholder_quotes(
    rel: str, skeleton: str, headings: list[str], titles: frozenset[str] = frozenset()
) -> dict[str, str]:
    """契約節（placeholder）の名前と、kit が器に書く引用段落を返す。

    kit が描画した器だけから求める。`PLACEHOLDER_FILES` の器で、見出し名が `titles`
    （`domain_docs.api_sections` の title）と完全一致し、所有権表の節でも `参照` でもない節のうち、
    引用段落と単独行の `[TODO]` だけでできているものが対象である。既存ファイルの手書きの節は対象にならない。
    `titles` が空なら対象は無い。
    """
    if rel not in PLACEHOLDER_FILES:
        return {}
    _, sections = generate.split_structural_sections(skeleton, headings, "器")
    owned = set(OWNERSHIP[rel])
    quotes: dict[str, str] = {}
    for heading, section in zip(headings, sections):
        name = _heading_name(heading)
        if name in owned or name == "参照" or name not in titles:
            continue
        match = PLACEHOLDER_SECTION_RE.match(section)
        if match:
            quotes[name] = match.group("quote")
    return quotes


def analyze(
    root: Path, skeletons: dict[str, str], titles: frozenset[str] = frozenset()
) -> dict[str, dict]:
    """ファイルごとに、構造見出し・存在・器のまま残る節（fillable）を求める。"""
    info: dict[str, dict] = {}
    for rel, owned in OWNERSHIP.items():
        skeleton = skeletons.get(rel)
        if skeleton is None:
            raise FatalError(f"{rel} の器（テンプレート描画結果）がありません")
        headings = generate.structural_headings(skeleton)
        names = [_heading_name(heading) for heading in headings]
        absent = [name for name in owned if name not in names]
        if absent:
            raise FatalError(f"所有権表の節がテンプレートに存在しません: {rel} {absent}")
        path = _safe_path(root, rel, "domain-docs file")
        quotes = placeholder_quotes(rel, skeleton, headings, titles)
        entry = {
            "headings": headings,
            "names": names,
            "exists": path.is_file(),
            "fillable": [],
            "mismatch": "",
            "placeholder_quotes": quotes,
        }
        if path.is_file():
            try:
                _, skeleton_sections = generate.split_structural_sections(
                    skeleton, headings, "器"
                )
                _, current_sections = generate.split_structural_sections(
                    _read_text(path), headings, "既存ファイル"
                )
            except generate.SectionMismatch as exc:
                entry["mismatch"] = str(exc)
            else:
                entry["fillable"] = [
                    name
                    for name, base, current in zip(names, skeleton_sections, current_sections)
                    if (name in owned or name in quotes) and base == current
                ]
        info[rel] = entry
    return info


def _section_body(text: str, name: str) -> str:
    """`## name` の節本文（次の構造見出し直前まで）。見つからなければ空文字。"""
    lines = text.splitlines(keepends=True)
    mask = generate._fence_mask(lines)
    body: list[str] = []
    inside = False
    for line, fenced in zip(lines, mask):
        stripped = line.rstrip("\r\n")
        is_heading = not fenced and generate._STRUCTURAL_HEADING_RE.match(line) is not None
        if is_heading:
            if inside:
                break
            inside = stripped == f"## {name}"
            continue
        if inside:
            body.append(line)
    return "".join(body)


def readme_rows(text: str) -> list[dict]:
    """README 収録仕様の一覧行（slug / title / summary / evidence）。"""
    rows = []
    for line in _section_body(text, "収録仕様").splitlines():
        match = ROW_RE.match(line)
        if match:
            rows.append({
                "slug": match.group("slug"),
                "title": match.group("title"),
                "summary": match.group("summary") or "",
                "evidence": match.group("evidence") or "",
            })
    return rows


def _spec_md_files(root: Path) -> list[str]:
    directory = root / SPEC_DIR
    if not directory.is_dir():
        return []
    return sorted(f"{SPEC_DIR}/{path.name}" for path in directory.glob("*.md"))


def _existing_slugs(root: Path) -> set[str]:
    return {
        Path(rel).stem for rel in _spec_md_files(root) if Path(rel).name != "README.md"
    }


def _digests(root: Path, doc: Path | None, manifest_path: Path) -> dict[str, str]:
    paths = set(OWNERSHIP) | set(_spec_md_files(root))
    paths.add(manifest_path.relative_to(root).as_posix())
    if doc is not None:
        paths.add(doc.relative_to(root).as_posix())
    return {rel: _sha(root / rel) for rel in sorted(paths)}


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------
def build_targets(
    root: Path,
    manifest_path: Path,
    skeletons: dict[str, str],
    *,
    refresh: bool,
    titles: frozenset[str] = frozenset(),
) -> dict:
    doc, pin_state = design_doc_state(root, manifest_path)
    if refresh and doc is None:
        raise FatalError("refresh には Design Doc が必要です")
    if refresh and pin_state == "unpinned":
        raise FatalError("refresh には固定済みの design_doc が必要です（先に fill を実行してください）")
    files: list[dict] = []
    spec_files: list[dict] = []
    if doc is not None:
        info = analyze(root, skeletons, titles)
        for rel, entry in info.items():
            if refresh:
                sections = list(OWNERSHIP[rel]) if entry["exists"] and not entry["mismatch"] else []
            else:
                sections = list(entry["fillable"])
            item = {"file": rel, "exists": entry["exists"], "sections": sections}
            placeholders = [name for name in sections if name in entry["placeholder_quotes"]]
            if placeholders:
                item["placeholders"] = placeholders
            if entry["mismatch"]:
                item["mismatch"] = entry["mismatch"]
            files.append(item)
        readme = root / README_PATH
        rows = readme_rows(_read_text(readme)) if readme.is_file() else []
        by_slug = {row["slug"]: row["evidence"] for row in rows}
        for slug in sorted(_existing_slugs(root) | set(by_slug)):
            spec_files.append({
                "slug": slug,
                "exists": (root / SPEC_DIR / f"{slug}.md").is_file(),
                "evidence": by_slug.get(slug, ""),
            })
    total = sum(len(item["sections"]) for item in files)
    if doc is None:
        action = "skip"
    elif refresh:
        action = "refresh"
    elif pin_state == "stale":
        action = "stale"
    elif total > 0:
        action = "fill"
    else:
        action = "skip"
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "refresh" if refresh else "fill",
        "action": action,
        "pin": pin_state,
        "design_doc": doc.relative_to(root).as_posix() if doc is not None else "",
        "source_fingerprint": tc.source_fingerprint(doc) if doc is not None else "",
        "files": files,
        "spec_files": spec_files,
        "digests": _digests(root, doc, manifest_path),
    }


# --------------------------------------------------------------------------
# 結果ファイルの検証
# --------------------------------------------------------------------------
def _single_line(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApplyError(f"{label} は非空文字列が必要です")
    if "\n" in value or "\r" in value:
        raise ApplyError(f"{label} は1行である必要があります")
    if "{{" in value or "}}" in value:
        raise ApplyError(f"{label} に Mustache 構文は許可されません")
    return value.strip()


def _check_body(body: object, label: str) -> str:
    if not isinstance(body, str) or not body.strip():
        raise ApplyError(f"{label}.body は非空文字列が必要です")
    if "{{" in body or "}}" in body:
        raise ApplyError(f"{label}.body に Mustache 構文は許可されません")
    if "[TODO]" in body:
        raise ApplyError(f"{label}.body に [TODO] は書けません（根拠が無い節は omissions に書く）")
    if re.search(r"!\[[^\]]*\]\(", body):
        raise ApplyError(f"{label}.body に画像リンクは書けません")
    if "erDiagram" in body:
        raise ApplyError(f"{label}.body に ER 図は書けません")
    return body.strip("\n")


def _check_evidence(value: object, label: str, doc_headings: set[str]) -> str:
    evidence = _single_line(value, f"{label}.evidence")
    if evidence not in doc_headings:
        raise ApplyError(f"{label}.evidence に対応する見出しが Design Doc にありません: {evidence!r}")
    return evidence


def _check_keys(item: object, allowed: frozenset[str], label: str) -> dict:
    if not isinstance(item, dict):
        raise ApplyError(f"{label} は mapping である必要があります")
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise ApplyError(f"{label} に未知キーがあります: {unknown}")
    missing = sorted(allowed - set(item))
    if missing:
        raise ApplyError(f"{label} に必須キーがありません: {missing}")
    return item


def spec_file_document(item: dict) -> str:
    """機能仕様 1 件を、生成物 `docs/spec/{slug}.md` の全文にする。"""
    body = item["body"].strip("\n")
    return (
        f"# {item['title'].strip()}\n"
        "\n"
        f"{body}\n"
        "\n"
        "## 関連仕様\n"
        "\n"
        "- [仕様概要](../spec.md)\n"
        "- [API 仕様](../api.md)\n"
        "- [データモデル](../data-models.md)\n"
        "- [ワークフロー](../workflows.md)\n"
    )


def _replace_sections(text: str, headings: list[str], replacements: dict[str, str]) -> str:
    preamble, sections = generate.split_structural_sections(text, headings, "対象")
    out = [preamble]
    for index, (heading, section) in enumerate(zip(headings, sections)):
        name = _heading_name(heading)
        if name not in replacements:
            out.append(section)
            continue
        trailing = section[len(section.rstrip("\r\n")):]
        if index == len(sections) - 1:
            trailing = trailing or "\n"
        elif trailing.count("\n") < 2:
            trailing = "\n\n"
        out.append(f"{heading}\n\n{replacements[name]}{trailing}")
    return "".join(out)


def _check_targets(targets: dict, *, refresh: bool) -> None:
    if targets.get("schema_version") != SCHEMA_VERSION:
        raise FatalError("targets の schema_version が不正です。state を再実行してください")
    mode = targets.get("mode")
    if mode not in ("fill", "refresh"):
        raise FatalError("targets の mode が不正です")
    if (mode == "refresh") != refresh:
        raise FatalError(
            f"targets は {mode} 用です。apply の --refresh の有無を合わせるか、state をやり直してください"
        )
    for key in ("files", "spec_files", "digests", "source_fingerprint", "design_doc"):
        if key not in targets:
            raise FatalError(f"targets に {key} がありません。state を再実行してください")


def _check_unchanged(root: Path, manifest_path: Path, targets: dict) -> Path:
    doc = detect_design_doc(root)
    if doc is None or doc.relative_to(root).as_posix() != targets["design_doc"]:
        raise ApplyError("state の後に Design Doc の検出結果が変わりました。state を再実行してください")
    if tc.source_fingerprint(doc) != targets["source_fingerprint"]:
        raise ApplyError("state の後に Design Doc が変更されました。state を再実行してください")
    current = _digests(root, doc, manifest_path)
    recorded = targets["digests"]
    changed = sorted(
        rel for rel in set(current) | set(recorded) if current.get(rel, "") != recorded.get(rel, "")
    )
    if changed:
        raise ApplyError(
            "state の後に変更されたファイルがあります（subagent による直接編集の疑い）: "
            + ", ".join(changed)
        )
    return doc


def _consistency_errors(
    readme_text: str,
    spec_text: str,
    final_slugs: set[str],
    new_evidence: dict[str, str],
) -> list[str]:
    rows = readme_rows(readme_text)
    readme_slugs = {row["slug"] for row in rows}
    spec_slugs = set(SPEC_LINK_RE.findall(_section_body(spec_text, "機能仕様")))
    errors = []
    if readme_slugs != final_slugs:
        errors.append(
            f"収録仕様と docs/spec/*.md が一致しません: 収録仕様のみ={sorted(readme_slugs - final_slugs)} "
            f"ファイルのみ={sorted(final_slugs - readme_slugs)}"
        )
    if spec_slugs != final_slugs:
        errors.append(
            f"docs/spec.md の機能仕様と docs/spec/*.md が一致しません: 機能仕様のみ={sorted(spec_slugs - final_slugs)} "
            f"ファイルのみ={sorted(final_slugs - spec_slugs)}"
        )
    by_slug = {row["slug"]: row["evidence"] for row in rows}
    for slug, evidence in sorted(new_evidence.items()):
        if by_slug.get(slug) != evidence:
            errors.append(f"収録仕様の {slug} に根拠 `{evidence}` が併記されていません")
    return errors


def build_plan(
    root: Path,
    manifest_path: Path,
    skeletons: dict[str, str],
    targets: dict,
    result: dict,
    *,
    refresh: bool,
    titles: frozenset[str] = frozenset(),
) -> Plan:
    _check_targets(targets, refresh=refresh)
    doc = _check_unchanged(root, manifest_path, targets)
    doc_headings = heading_names(doc)
    info = analyze(root, skeletons, titles)
    plan = Plan()

    unknown = sorted(set(result) - RESULT_KEYS)
    if unknown:
        raise ApplyError(f"結果ファイルに未知キーがあります: {unknown}")
    if result.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ApplyError("結果ファイルの schema_version が不正です")

    target_sections = {
        (item["file"], name)
        for item in targets["files"]
        for name in item.get("sections", [])
    }

    # --- sections / omissions -------------------------------------------------
    section_bodies: dict[tuple[str, str], str] = {}
    for index, raw in enumerate(result.get("sections") or []):
        label = f"sections[{index}]"
        item = _check_keys(raw, SECTION_KEYS, label)
        rel = _single_line(item["file"], f"{label}.file")
        name = _single_line(item["heading"], f"{label}.heading")
        quotes = info[rel]["placeholder_quotes"] if rel in info else {}
        if rel not in OWNERSHIP or (name not in OWNERSHIP[rel] and name not in quotes):
            raise ApplyError(f"{label}: 書込み対象外の節です: {rel} / {name}（所有権表に無い）")
        if name in quotes and refresh:
            raise ApplyError(f"{label}: 契約節は fill-only でだけ書けます（refresh では書けません）: {rel} / {name}")
        if (rel, name) in section_bodies:
            raise ApplyError(f"{label}: 同じ節が重複しています: {rel} / {name}")
        _check_evidence(item["evidence"], label, doc_headings)
        body = _check_body(item["body"], label)
        clash = [h for h in generate.structural_headings(body) if h in info[rel]["headings"]]
        if clash:
            raise ApplyError(f"{label}.body が構造見出しと同名の `##` を含みます: {clash}")
        if name in quotes:
            # 契約節の body は `[TODO]` の置換文である。kit の引用は apply が器から復元して残す。
            if body.lstrip().startswith(">") or quotes[name] in body:
                raise ApplyError(f"{label}.body に kit の引用を含められません（引用は apply が保持する）: {rel} / {name}")
            body = f"{quotes[name]}\n\n{body}"
        section_bodies[(rel, name)] = body

    omitted: set[tuple[str, str]] = set()
    for index, raw in enumerate(result.get("omissions") or []):
        label = f"omissions[{index}]"
        item = _check_keys(raw, OMISSION_KEYS, label)
        rel = _single_line(item["file"], f"{label}.file")
        name = _single_line(item["heading"], f"{label}.heading")
        _single_line(item["reason"], f"{label}.reason")
        quotes = info[rel]["placeholder_quotes"] if rel in info else {}
        if rel not in OWNERSHIP or (name not in OWNERSHIP[rel] and name not in quotes):
            raise ApplyError(f"{label}: 書込み対象外の節です: {rel} / {name}")
        if (rel, name) in section_bodies or (rel, name) in omitted:
            raise ApplyError(f"{label}: 同じ節を sections と omissions に重複して書けません: {rel} / {name}")
        omitted.add((rel, name))

    unanswered = sorted(target_sections - set(section_bodies) - omitted)
    if unanswered:
        raise ApplyError(
            "対象節に回答がありません（sections か omissions に書く）: "
            + ", ".join(f"{rel}#{name}" for rel, name in unanswered)
        )

    new_texts: dict[str, str] = {}
    for rel, entry in info.items():
        replacements = {
            name: body for (file, name), body in section_bodies.items() if file == rel
        }
        if not replacements:
            continue
        if not entry["exists"]:
            raise ApplyError(f"{rel} が存在しません。generate を先に実行してください")
        if entry["mismatch"]:
            raise ApplyError(f"{rel}: 見出し構成不一致（{entry['mismatch']}）")
        path = root / rel
        existing = _read_text(path)
        headings = entry["headings"]
        if refresh:
            new_text = _replace_sections(existing, headings, replacements)
        else:
            expected = _replace_sections(skeletons[rel], headings, replacements)
            try:
                new_text, _ = generate.merge_seed_sections(existing, skeletons[rel], expected)
            except generate.SectionMismatch as exc:
                raise ApplyError(f"{rel}: 見出し構成不一致（{exc}）") from exc
            for name in sorted(set(replacements) - set(entry["fillable"])):
                plan.notes.append(f"KEPT: {rel}#{name} は埋め済みのため書き込みません")
        if new_text != existing:
            new_texts[rel] = new_text
            if refresh:
                plan.diffs.append(_unified_diff(rel, existing, new_text))

    # --- spec_files -----------------------------------------------------------
    readme_path = root / README_PATH
    existing_readme = _read_text(readme_path) if readme_path.is_file() else ""
    rows = readme_rows(existing_readme)
    row_by_slug = {row["slug"]: row for row in rows}
    slug_by_evidence = {row["evidence"]: row["slug"] for row in rows if row["evidence"]}
    existing_slugs = _existing_slugs(root)
    new_files: dict[str, str] = {}
    new_evidence: dict[str, str] = {}
    seen_slugs: set[str] = set()
    seen_evidence: set[str] = set()
    for index, raw in enumerate(result.get("spec_files") or []):
        label = f"spec_files[{index}]"
        item = _check_keys(raw, SPEC_FILE_KEYS, label)
        slug = _single_line(item["slug"], f"{label}.slug")
        if not SLUG_RE.fullmatch(slug) or slug in RESERVED_SLUGS:
            raise ApplyError(f"{label}.slug は kebab-case で README 以外である必要があります: {slug!r}")
        if slug in seen_slugs:
            raise ApplyError(f"{label}: slug が重複しています: {slug}")
        seen_slugs.add(slug)
        _single_line(item["title"], f"{label}.title")
        _single_line(item["summary"], f"{label}.summary")
        evidence = _check_evidence(item["evidence"], label, doc_headings)
        if evidence in seen_evidence:
            raise ApplyError(f"{label}: 根拠見出しが重複しています: {evidence!r}")
        seen_evidence.add(evidence)
        body = _check_body(item["body"], label)
        lines = [line.strip() for line in body.splitlines()]
        if "## 概要" not in lines:
            raise ApplyError(f"{label}.body には見出し `## 概要` が必要です")
        if any(line == "## 関連仕様" or line.startswith("# ") for line in lines):
            raise ApplyError(f"{label}.body に H1 と `## 関連仕様` は書けません")
        mapped = slug_by_evidence.get(evidence)
        if mapped is not None and mapped != slug:
            raise ApplyError(
                f"{label}: 根拠見出し {evidence!r} は既存の {mapped} に対応付いています（別 slug {slug} は不可）"
            )
        path = _safe_path(root, f"{SPEC_DIR}/{slug}.md", f"{label}.slug")
        document = spec_file_document({**item, "body": body})
        if slug in existing_slugs:
            row = row_by_slug.get(slug)
            if row is None:
                raise ApplyError(f"{label}: {slug}.md は既存ですが収録仕様に行がありません")
            if row["evidence"] and row["evidence"] != evidence:
                raise ApplyError(
                    f"{label}: {slug}.md の根拠は {row['evidence']!r} です（結果は {evidence!r}）"
                )
            if not refresh:
                plan.notes.append(f"KEPT: {SPEC_DIR}/{slug}.md は既存のため再作成しません")
                continue
            current = _read_text(path)
            if current != document:
                new_files[f"{SPEC_DIR}/{slug}.md"] = document
                plan.diffs.append(_unified_diff(f"{SPEC_DIR}/{slug}.md", current, document))
            continue
        new_files[f"{SPEC_DIR}/{slug}.md"] = document
        new_evidence[slug] = evidence
        plan.diffs.append(_unified_diff(f"{SPEC_DIR}/{slug}.md", "", document))

    # --- 3者の整合 -----------------------------------------------------------
    touches_index = (
        refresh or bool(new_files) or SPEC_PATH in new_texts or README_PATH in new_texts
    )
    if touches_index:
        spec_path = root / SPEC_PATH
        final_readme = new_texts.get(README_PATH, existing_readme)
        final_spec = new_texts.get(
            SPEC_PATH, _read_text(spec_path) if spec_path.is_file() else ""
        )
        final_slugs = existing_slugs | {Path(rel).stem for rel in new_files}
        errors = _consistency_errors(final_readme, final_spec, final_slugs, new_evidence)
        if errors:
            raise ApplyError("; ".join(errors))
        for row in readme_rows(final_readme):
            if row["evidence"] and row["evidence"] not in doc_headings:
                plan.notes.append(
                    f"ORPHAN: {row['slug']}.md の根拠見出し {row['evidence']!r} は Design Doc にありません（削除しません）"
                )

    # --- pin（fingerprint の更新）--------------------------------------------
    plan.writes.update({rel: text.encode("utf-8") for rel, text in new_texts.items()})
    plan.writes.update({rel: text.encode("utf-8") for rel, text in new_files.items()})
    if refresh or targets["pin"] == "unpinned":
        _plan_pin(root, manifest_path, doc, plan)
    plan.digest = _plan_digest(targets["source_fingerprint"], plan.writes)
    return plan


def _plan_pin(root: Path, manifest_path: Path, doc: Path, plan: Plan) -> None:
    relative = manifest_path.relative_to(root).as_posix()
    updated = pinned_manifest_bytes(
        manifest_path, doc.relative_to(root).as_posix(), tc.source_fingerprint(doc)
    )
    if updated != manifest_path.read_bytes():
        plan.writes[relative] = updated


def _plan_digest(fingerprint: str, writes: dict[str, bytes]) -> str:
    payload = tc.canonical_json({
        "fingerprint": fingerprint,
        "writes": {rel: hashlib.sha256(data).hexdigest() for rel, data in sorted(writes.items())},
    })
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _unified_diff(rel: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


# --------------------------------------------------------------------------
# 書込み（全ファイルを atomic に。失敗時は書込み前へ戻す）
# --------------------------------------------------------------------------
def commit(root: Path, writes: dict[str, bytes]) -> None:
    originals: dict[Path, bytes | None] = {}
    done: list[Path] = []
    try:
        for rel, payload in writes.items():
            path = _safe_path(root, rel, "write path")
            originals[path] = path.read_bytes() if path.exists() else None
            _write_bytes(path, payload)
            done.append(path)
    except BaseException as exc:  # noqa: BLE001 - 失敗は戻したうえで致命的エラーとして報告する
        unrestored = []
        for path in reversed(done):
            try:
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    _write_bytes(path, original)
            except OSError:
                unrestored.append(path.relative_to(root).as_posix())
        if unrestored:
            raise FatalError(
                f"書込み失敗後に元へ戻せないファイルがあります: {', '.join(unrestored)}（{exc}）"
            ) from exc
        raise FatalError(f"書込み失敗。変更は元へ戻しました: {exc}") from exc


# --------------------------------------------------------------------------
# サブコマンド
# --------------------------------------------------------------------------
def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    manifest_path = Path(args.manifest).resolve()
    root = manifest_path.parent
    targets_path = Path(args.targets).resolve() if args.targets else root / TARGETS_RELATIVE
    result_path = Path(args.result).resolve() if args.result else root / RESULT_RELATIVE
    return root, manifest_path, targets_path, result_path


def cmd_state(args: argparse.Namespace) -> int:
    root, manifest_path, targets_path, _ = _paths(args)
    if not manifest_path.is_file():
        raise FatalError(f"manifest が存在しません: {manifest_path}")
    skeletons = render_skeletons(manifest_path)
    targets = build_targets(
        root, manifest_path, skeletons, refresh=args.refresh, titles=api_section_titles(manifest_path)
    )
    targets_path.parent.mkdir(parents=True, exist_ok=True)
    targets_path.write_text(dump_yaml_text(targets), encoding="utf-8")
    total = sum(len(item["sections"]) for item in targets["files"])
    print(
        f"STATE: action={targets['action']} pin={targets['pin']} sections={total} "
        f"targets={targets_path.relative_to(root).as_posix() if targets_path.is_relative_to(root) else targets_path}"
    )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    root, manifest_path, targets_path, result_path = _paths(args)
    if args.approve and not args.refresh:
        raise FatalError("--approve は --refresh と併用します")
    if args.decline and not args.refresh:
        raise FatalError("--decline は --refresh と併用します")
    if args.approve and args.decline:
        raise FatalError("--approve と --decline は同時に指定できません")
    if not targets_path.is_file():
        raise FatalError("targets がありません。先に state を実行してください")
    targets = _load_yaml(targets_path, FatalError)
    _check_targets(targets, refresh=args.refresh)
    if targets.get("action") == "skip":
        print("PASS: 対象なし（skip）")
        return 0

    if args.decline:
        doc = _check_unchanged(root, manifest_path, targets)
        plan = Plan()
        _plan_pin(root, manifest_path, doc, plan)
        commit(root, plan.writes)
        _cleanup(targets_path, result_path)
        print("PASS: refresh を見送り、Design Doc を既読にしました（docs は変更なし）")
        return 0

    if not result_path.is_file():
        raise ApplyError(f"結果ファイルがありません: {result_path}")
    result = _load_yaml(result_path, ApplyError)
    skeletons = render_skeletons(manifest_path)
    plan = build_plan(
        root, manifest_path, skeletons, targets, result,
        refresh=args.refresh, titles=api_section_titles(manifest_path),
    )

    if args.refresh and not args.approve:
        for diff in plan.diffs:
            print(diff, end="" if diff.endswith("\n") else "\n")
        for note in plan.notes:
            print(note)
        print(f"PLAN: files={len(plan.writes)} digest={plan.digest}")
        print("承認するには apply --refresh --approve <digest> を実行する（書込みなし）")
        return 0
    if args.refresh and args.approve != plan.digest:
        raise ApplyError("承認した digest が現在の計画と一致しません。計画を再表示してください")

    commit(root, plan.writes)
    _cleanup(targets_path, result_path)
    for note in plan.notes:
        print(note)
    print(f"PASS: domain-docs 適用完了 files={len(plan.writes)}")
    for rel in sorted(plan.writes):
        print(f"  [write] {rel}")
    return 0


def cmd_pin(args: argparse.Namespace) -> int:
    root, manifest_path, _, _ = _paths(args)
    if not manifest_path.is_file():
        raise FatalError(f"manifest が存在しません: {manifest_path}")
    doc = detect_design_doc(root)
    if doc is None:
        raise FatalError("Design Doc がありません")
    plan = Plan()
    _plan_pin(root, manifest_path, doc, plan)
    commit(root, plan.writes)
    print(f"PASS: design_doc を固定しました source_path={doc.relative_to(root).as_posix()}")
    return 0


def _cleanup(targets_path: Path, result_path: Path) -> None:
    targets_path.unlink(missing_ok=True)
    result_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="domain-docs の state / apply / pin")
    parser.add_argument("command", choices=("state", "apply", "pin"))
    parser.add_argument("--manifest", default=str(ROOT / "manifest.yaml"))
    parser.add_argument("--targets", help="targets ファイル（既定: tmp/domain-docs-targets.yaml）")
    parser.add_argument("--result", help="結果ファイル（既定: tmp/domain-docs-result.yaml）")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--approve", metavar="DIGEST")
    parser.add_argument("--decline", action="store_true")
    args = parser.parse_args(argv)
    try:
        handler = {"state": cmd_state, "apply": cmd_apply, "pin": cmd_pin}[args.command]
        return handler(args)
    except ApplyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except FatalError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
