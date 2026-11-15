#!/usr/bin/env python3
"""Design Doc 由来の Domain docs 投影を検証し、root manifest へ固定する。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
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
from yaml_emitter import dump_yaml  # noqa: E402

SCHEMA_VERSION = 1
TOP_LEVEL_KEYS = frozenset({
    "schema_version",
    "source_path",
    "source_fingerprint",
    "projection",
    "omissions",
    "digest",
    "approval",
})
APPROVAL_KEYS = frozenset({"status", "digest", "schema_version"})
FIELD_KEYS = frozenset({"body", "evidence"})
PROJECTION_FIELDS = {
    "spec": frozenset({
        "purpose",
        "glossary",
        "boundary",
        "principles",
        "features",
        "non_functional",
        "change_resilience",
    }),
    "api": frozenset({"overview", "endpoints", "errors", "details"}),
    "architecture": frozenset({"overview", "modules", "components", "dependencies"}),
    "data_models": frozenset({"principles", "entities", "access"}),
    "workflows": frozenset({"flows", "retry", "states"}),
}
ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")


class ProjectionError(Exception):
    """stale / digest mismatch / doc 欠落など、再起案で修正できる不一致。"""


class SchemaError(Exception):
    """schema / filesystem の致命的な不正。"""


def _reject_unknown(obj: dict, allowed: frozenset[str], label: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise SchemaError(f"{label} に未知キーがあります: {sorted(unknown)}")


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{label} は非空文字列が必要です")
    return value


def _bare_projection(value: dict) -> dict:
    return {key: copy.deepcopy(item) for key, item in value.items() if key not in {"digest", "approval"}}


def projection_digest(value: dict) -> str:
    payload = tc.canonical_json(_bare_projection(value)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_omissions(value: object) -> dict[str, str]:
    """omissions（doc 名 → 省略理由）の形式を検査し、正規化して返す。"""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SchemaError("design_doc.omissions は mapping である必要があります")
    _reject_unknown(value, frozenset(PROJECTION_FIELDS), "design_doc.omissions")
    return {
        doc_name: _require_str(reason, f"design_doc.omissions.{doc_name}")
        for doc_name, reason in value.items()
    }


def _design_doc_relative_path(manifest_path: Path, design_doc: Path) -> str:
    try:
        return design_doc.resolve().relative_to(manifest_path.parent.resolve()).as_posix()
    except ValueError as exc:
        raise SchemaError("Design Doc はリポジトリルート配下に必要です") from exc


def _heading_names(design_doc: Path) -> set[str]:
    try:
        text = design_doc.read_text(encoding="utf-8")
    except OSError as exc:
        raise SchemaError(f"Design Doc 読み込み失敗: {exc}") from exc
    # コードフェンス内の `## ` は見出しではないため、generate.py の節境界と同じ規則で除外する。
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


def validate(
    value: dict,
    manifest_path: Path,
    design_doc: Path,
    *,
    require_approval: bool,
) -> None:
    if not isinstance(value, dict):
        raise SchemaError("design_doc は mapping である必要があります")
    _reject_unknown(value, TOP_LEVEL_KEYS, "design_doc")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise SchemaError(f"schema_version は {SCHEMA_VERSION} である必要があります")

    expected_path = _design_doc_relative_path(manifest_path, design_doc)
    source_path = _require_str(value.get("source_path"), "design_doc.source_path")
    if source_path != expected_path:
        raise SchemaError(
            f"design_doc.source_path は検出済みパス {expected_path!r} と一致する必要があります"
        )
    expected_fingerprint = tc.source_fingerprint(design_doc)
    if value.get("source_fingerprint") != expected_fingerprint:
        raise ProjectionError("source_fingerprint が現在の Design Doc と一致しません")

    projection = value.get("projection")
    if not isinstance(projection, dict):
        raise SchemaError("design_doc.projection は mapping である必要があります")
    _reject_unknown(projection, frozenset(PROJECTION_FIELDS), "design_doc.projection")
    omissions = _validate_omissions(value.get("omissions"))
    headings = _heading_names(design_doc)
    field_count = 0
    projected_docs: set[str] = set()
    for doc_name, fields in projection.items():
        label = f"design_doc.projection.{doc_name}"
        if not isinstance(fields, dict):
            raise SchemaError(f"{label} は mapping である必要があります")
        _reject_unknown(fields, PROJECTION_FIELDS[doc_name], label)
        if fields:
            projected_docs.add(doc_name)
        for field_name, field in fields.items():
            field_count += 1
            field_label = f"{label}.{field_name}"
            if not isinstance(field, dict):
                raise SchemaError(f"{field_label} は mapping である必要があります")
            _reject_unknown(field, FIELD_KEYS, field_label)
            body = _require_str(field.get("body"), f"{field_label}.body")
            evidence = _require_str(field.get("evidence"), f"{field_label}.evidence")
            if "{{" in body or "}}" in body:
                raise SchemaError(f"{field_label}.body に Mustache 構文は許可されません")
            if evidence not in headings:
                raise SchemaError(
                    f"{field_label}.evidence に対応する見出しが Design Doc にありません: {evidence!r}"
                )
    if field_count == 0:
        raise SchemaError("design_doc.projection には少なくとも1フィールド必要です")
    overlap = sorted(projected_docs & set(omissions))
    if overlap:
        raise SchemaError(
            f"design_doc.omissions と projection の両方に書かれた doc があります: {overlap}"
        )
    # PROJECTION_FIELDS の全 doc を走査する。旧規則で pin 済みの投影も再起案（exit 1）で復旧させる。
    uncovered = [
        doc_name
        for doc_name in PROJECTION_FIELDS
        if doc_name not in projected_docs and doc_name not in omissions
    ]
    if uncovered:
        raise ProjectionError(
            "投影も omissions も無い doc があります: "
            f"{uncovered}。フィールドを起案するか、design_doc.omissions に省略理由を書いてください"
        )

    expected_digest = projection_digest(value)
    digest = value.get("digest")
    if require_approval:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SchemaError("固定済み design_doc では digest が必須です")
        if digest != expected_digest:
            raise SchemaError("digest が canonical digest と一致しません")
        approval = value.get("approval")
        if not isinstance(approval, dict):
            raise SchemaError("固定済み design_doc では approval が必須です")
        _reject_unknown(approval, APPROVAL_KEYS, "design_doc.approval")
        if approval.get("status") != "approved":
            raise SchemaError("approval.status=approved が必要です")
        if (
            approval.get("digest") != expected_digest
            or approval.get("schema_version") != SCHEMA_VERSION
        ):
            raise SchemaError("approval が digest / schema version に結合されていません")
    else:
        if digest is not None and digest != expected_digest:
            raise SchemaError("digest が canonical digest と一致しません")
        approval = value.get("approval")
        if approval is not None:
            if not isinstance(approval, dict):
                raise SchemaError("design_doc.approval は mapping である必要があります")
            _reject_unknown(approval, APPROVAL_KEYS, "design_doc.approval")
            if (
                approval.get("status") != "approved"
                or approval.get("digest") != expected_digest
                or approval.get("schema_version") != SCHEMA_VERSION
            ):
                raise SchemaError("approval が digest / schema version に結合されていません")


def _finalize(value: dict) -> dict:
    finalized = _bare_projection(value)
    digest = projection_digest(finalized)
    finalized["digest"] = digest
    finalized["approval"] = {
        "status": "approved",
        "digest": digest,
        "schema_version": SCHEMA_VERSION,
    }
    return finalized


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_top_level_key_line(line: str) -> bool:
    """値の有無にかかわらず、インデント 0 の `key:` 行を次のトップレベルキーとみなす。"""
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


def pin_projection(
    manifest_path: Path,
    value: dict,
    expected_preimage: str,
    design_doc: Path,
) -> dict:
    current = tc.file_digest(manifest_path)
    if current != expected_preimage:
        raise ProjectionError("root manifest の preimage が plan 時点から変化しました")
    finalized = _finalize(value)
    validate(finalized, manifest_path, design_doc, require_approval=True)

    raw = manifest_path.read_bytes()
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    replacement = (
        newline.join(line.encode("utf-8") for line in dump_yaml({"design_doc": finalized}))
        + newline
    )
    span = _find_top_level_block_span(raw, "design_doc")
    if span is None:
        if raw and not raw.endswith((b"\n", b"\r\n")):
            raw += newline
        new_raw = raw + replacement
    else:
        new_raw = raw[: span[0]] + replacement + raw[span[1] :]

    try:
        parsed = genlib.parse_yaml(new_raw.decode("utf-8"))
    except (UnicodeDecodeError, genlib.YamlError) as exc:
        raise SchemaError(f"pin 後 manifest の解析に失敗しました: {exc}") from exc
    loaded = parsed.get("design_doc") if isinstance(parsed, dict) else None
    if not isinstance(loaded, dict):
        raise SchemaError("pin 後 design_doc が見つかりません")
    if tc.canonical_json(loaded) != tc.canonical_json(finalized):
        raise SchemaError("pin round-trip で design_doc が一致しません")
    validate(loaded, manifest_path, design_doc, require_approval=True)
    rp._atomic_write_bytes(manifest_path, new_raw)
    return loaded


def _load_yaml(path: Path) -> dict:
    try:
        loaded = genlib.load_manifest(str(path))
    except (OSError, genlib.YamlError) as exc:
        raise SchemaError(f"YAML 読み込み失敗: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SchemaError("YAML root は mapping である必要があります")
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Design Doc 投影の validate / apply")
    parser.add_argument("command", choices=("validate", "apply"))
    parser.add_argument("--manifest", type=Path, default=ROOT / "manifest.yaml")
    parser.add_argument("--design-doc", type=Path, required=True)
    parser.add_argument(
        "--draft",
        type=Path,
        default=ROOT / "tmp" / "design-doc-projection-draft.yaml",
    )
    parser.add_argument("--preimage", help="apply に必要な root manifest 全体 SHA-256")
    parser.add_argument("--check", action="store_true", help="互換用 read-only 検証フラグ")
    args = parser.parse_args(argv)
    try:
        if not args.manifest.is_file() or not args.design_doc.is_file():
            raise SchemaError("manifest または Design Doc が存在しません")
        if not args.draft.is_file():
            raise ProjectionError(f"draft が見つかりません: {args.draft}")
        draft_root = _load_yaml(args.draft)
        draft = (
            draft_root.get("design_doc")
            if isinstance(draft_root.get("design_doc"), dict)
            else draft_root
        )
        validate(draft, args.manifest, args.design_doc, require_approval=False)
        if args.command == "validate":
            print(f"PASS: design_doc draft digest={projection_digest(draft)}")
            return 0
        if not args.preimage or not re.fullmatch(r"[0-9a-f]{64}", args.preimage):
            raise SchemaError("apply には --preimage <root manifest sha256> が必要です")
        sealed = pin_projection(args.manifest, draft, args.preimage, args.design_doc)
        args.draft.unlink(missing_ok=True)
        print(
            "PASS: design_doc projection auto-approved "
            f"digest={sealed['digest']}"
        )
        return 0
    except ProjectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (
        SchemaError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        AttributeError,
        OSError,
        re.error,
    ) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
