#!/usr/bin/env python3
"""生成済み root manifest.yaml の tech_stack（policy）と package.json（reality）の整合ゲート（Phase 1.7）。"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
GENLIB_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if GENLIB_DIR not in sys.path:
    sys.path.insert(0, GENLIB_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import genlib  # noqa: E402
import ingest_tech_stack as ingest  # noqa: E402
import resolve_quality_gate as rqg  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")
DEFAULT_PACKAGE_JSON = os.path.join(ROOT, "package.json")
OPTIONAL_MARKERS = ("任意", "代替")
REQUIRED_GATE_SCRIPTS = ("build", "lint", "test")


def _out(level: str, msg: str) -> None:
    print(f"[check_tech_stack_conformance] {level}: {msg}")


def policy_allowed_majors(version_policy: str):
    s = (version_policy or "").strip()
    if s in ("", "—", "-"):
        return None, False
    open_ended = ("以降" in s) or ("+" in s)
    majors = set()
    for m in re.finditer(r"v?(\d+)(?:\.(?:\d+|x|X))?", s):
        majors.add(int(m.group(1)))
    return (majors, open_ended) if majors else (None, False)


def real_major(version_spec: str):
    if not version_spec:
        return None
    if version_spec.split("@")[-1].startswith("workspace"):
        return None
    m = re.search(r"(\d+)", version_spec)
    return int(m.group(1)) if m else None


def forbidden_libs(items):
    forb = set()
    for it in items:
        note = it.get("note") or ""
        if "不採用" not in note:
            continue
        for m in re.finditer(r"`([^`]+)`", note):
            token = m.group(1).strip()
            if token and " " not in token:
                forb.add(token)
    return forb


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="tech_stack policy↔reality 整合ゲート")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--package-json", default=DEFAULT_PACKAGE_JSON)
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        _out("ERROR", f"manifest が見つからない: {args.manifest}")
        return 2
    try:
        manifest = genlib.load_manifest(args.manifest)
    except genlib.YamlError as e:
        _out("ERROR", f"manifest 解析失敗: {e}")
        return 2

    items = (manifest.get("tech_stack") or {}).get("items") or []
    if not items:
        _out("WARN", "root manifest tech_stack.items が空（Phase 1.6 未実行？）。照合をスキップ")
        return 0

    # 契約確定判定: Phase 1.65 と同一の適格条件を使用
    resolved, _reason = rqg._resolve(manifest)
    if resolved == "FATAL":
        _out("ERROR", _reason)
        return 2
    contract_resolved = resolved is not None

    versions = ingest.load_package_versions(args.package_json)
    if versions is None:
        if contract_resolved:
            _out("FAIL", "quality-gate 契約確定済みだが package.json が不在（Phase 1.68 未実行？）")
            return 1
        _out("PASS", "契約未確定のため package.json 不在は対象外（fail-open）")
        return 0

    failures = []
    warnings = []
    for lib in sorted(forbidden_libs(items)):
        if lib in versions:
            failures.append(f"不採用宣言ライブラリが package.json に存在: `{lib}`")

    for it in items:
        tech = it.get("technology", "")
        pkg = ingest._match_package_name(tech, versions)
        if not pkg or pkg == "__packageManager__":
            continue
        if pkg not in versions:
            note = it.get("note") or ""
            if not any(mk in note for mk in OPTIONAL_MARKERS):
                warnings.append(f"ポリシーにあるが package.json に無い技術: {tech}（{pkg}）")
            continue
        allowed, open_ended = policy_allowed_majors(it.get("version_policy", ""))
        if allowed is None:
            continue
        rm = real_major(versions[pkg])
        if rm is None:
            continue
        if (open_ended and rm < min(allowed)) or (not open_ended and rm not in allowed):
            failures.append(
                f"version_policy 違反: {tech} はポリシー「{it.get('version_policy')}」"
                f"に対し実 major {rm}（{versions[pkg]}）"
            )

    # 契約確定時: 必須 scripts の存在検査
    if contract_resolved and versions is not None:
        pkg_path = args.package_json
        try:
            import json as _json
            with open(pkg_path, "r", encoding="utf-8") as _f:
                pkg_data = _json.load(_f)
            pkg_scripts = pkg_data.get("scripts") or {}
            for gate in REQUIRED_GATE_SCRIPTS:
                if gate not in pkg_scripts:
                    failures.append(f"契約確定済みだが package.json scripts.{gate} が欠落")
            # gen は openapi capability 存在時のみ必須
            names = rqg._tech_names(manifest)
            has_openapi = (
                rqg._has(names, "openapi")
                and rqg._has(names, "redocly")
                and rqg._has(names, "spectral")
            )
            if has_openapi and "gen" not in pkg_scripts:
                failures.append("契約確定済み + OpenAPI capability ありだが package.json scripts.gen が欠落")
        except (OSError, ValueError):
            pass

    for w in warnings:
        _out("WARN", w)
    if failures:
        for fmsg in failures:
            _out("FAIL", fmsg)
        _out("FAIL", f"整合ゲート不合格（{len(failures)} 件の意味的違反）。PO に報告し中断する")
        return 1
    _out("PASS", f"tech_stack policy↔reality 整合 OK（{len(items)} 技術 / WARN {len(warnings)} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
