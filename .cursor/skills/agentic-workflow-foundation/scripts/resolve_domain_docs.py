#!/usr/bin/env python3
"""tech_stack から Domain 層ドキュメント用の変数を決定する（Phase 1.67）。"""
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

import genlib  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")

# -- 共通セクション（全 tech-stack 共通） --

SPEC_SECTIONS_COMMON = [
    {"title": "目的と背景", "guidance": "サービスの目的・解決する課題・非目標を記述する"},
    {"title": "ドメイン用語集", "guidance": "プロジェクト固有の用語を定義する"},
    {"title": "システム境界", "guidance": "外部システムとの接続点・責務境界を記述する"},
    {"title": "不変の設計原則 (MUST)", "guidance": "変更不可の設計原則を列挙する（冪等性、トランザクション境界等）"},
    {"title": "機能仕様", "guidance": "主要機能の一覧と概要。詳細は docs/spec/{機能名}.md に分割する"},
    {"title": "非機能要件", "guidance": "SLO・パフォーマンス要件・セキュリティ要件等を記述する"},
    {"title": "変更に強い点・弱い点", "guidance": "アーキテクチャ上の拡張容易性と制約を記述する"},
]

ARCHITECTURE_SECTIONS_COMMON = [
    {"title": "システム全体構成", "guidance": "外部システムとの接続関係を図示する"},
    {"title": "ディレクトリ/モジュール責務", "guidance": "主要ディレクトリの責務を記述する"},
    {"title": "主要コンポーネント詳細", "guidance": "コンポーネント間の依存関係と責務を記述する"},
    {"title": "依存関係方針", "guidance": "依存の方向性・DI 方針・外部ライブラリ選定基準を記述する"},
]

API_SECTIONS_COMMON = [
    {"title": "API設計概要", "guidance": "API の設計方針・認証方式・共通仕様を記述する"},
    {"title": "エンドポイント一覧", "guidance": "主要エンドポイントのパス・メソッド・概要を記述する"},
    {"title": "エラーハンドリング", "guidance": "共通エラーコード・エラーレスポンス形式を記述する"},
]

DATA_MODEL_SECTIONS_COMMON = [
    {"title": "データベース設計思想", "guidance": "DB 設計の基本方針・正規化レベル・命名規約を記述する"},
    {"title": "主要テーブル/コレクション構成", "guidance": "主要エンティティの構造・カラム・型を記述する"},
    {"title": "ER図・関係性", "guidance": "エンティティ間のリレーションを図示する"},
    {"title": "データアクセスパターン", "guidance": "Repository パターン・クエリ方針・トランザクション管理を記述する"},
]

CODING_STANDARDS_SECTIONS_COMMON = [
    {"title": "基本方針", "guidance": "コーディング規約の基本方針・準拠規約を記述する"},
    {"title": "命名規約", "guidance": "変数・関数・ファイル・ディレクトリの命名規約を記述する"},
    {"title": "エラーハンドリング規約", "guidance": "エラー処理の統一パターンを記述する"},
    {"title": "テスト規約", "guidance": "テストの種類・命名・構成・カバレッジ方針を記述する"},
    {"title": "コメント・ドキュメント", "guidance": "コメント方針・JSDoc/GoDoc 等のルールを記述する"},
]

WORKFLOW_SECTIONS_COMMON = [
    {"title": "主要ユースケースの処理フロー", "guidance": "主要な業務フローをシーケンス図等で記述する"},
    {"title": "エラーハンドリング・リトライパターン", "guidance": "外部 API 呼び出しのリトライ・タイムアウト方針を記述する"},
    {"title": "状態管理・状態遷移", "guidance": "主要エンティティの状態遷移を図示する"},
]

# -- tech-stack 固有の追加セクション --

API_SECTIONS_OPENAPI = [
    {"title": "OpenAPI 定義", "guidance": "OpenAPI スキーマの構成・生成コマンド・バリデーション方針を記述する"},
]

API_SECTIONS_GRPC = [
    {"title": "Protocol Buffers定義", "guidance": "proto ファイルの構成・生成コマンド・サービス定義を記述する"},
    {"title": "gRPC サービス一覧", "guidance": "gRPC サービスと RPC メソッドの一覧を記述する"},
]

API_SECTIONS_GRAPHQL = [
    {"title": "GraphQL スキーマ", "guidance": "スキーマの構成・リゾルバ方針・型生成を記述する"},
]

DATA_MODEL_SECTIONS_MIGRATION = [
    {"title": "マイグレーション規約", "guidance": "マイグレーションの命名・適用手順・ロールバック方針を記述する"},
]

CODING_STANDARDS_SECTIONS_ARCH = [
    {"title": "アーキテクチャ規約", "guidance": "レイヤー間の依存ルール・責務分離の原則を記述する"},
]

CODING_STANDARDS_SECTIONS_LINT = [
    {"title": "静的解析・Lint", "guidance": "lint ツール・設定ファイル・CI での実行方法を記述する"},
]

WORKFLOW_SECTIONS_ASYNC = [
    {"title": "非同期処理・スケジューラー", "guidance": "バックグラウンドジョブ・スケジュール実行の方針を記述する"},
]


def _out(level: str, msg: str) -> None:
    print(f"[resolve_domain_docs] {level}: {msg}")


def _normalize(value: str) -> str:
    text = (value or "").replace("`", "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _tech_items(manifest: dict) -> list[dict]:
    return (manifest.get("tech_stack") or {}).get("items") or []


def _tech_names(manifest: dict) -> set[str]:
    names = set()
    for item in _tech_items(manifest):
        if isinstance(item, dict):
            names.add(_normalize(item.get("technology", "")))
    return names


def _tech_layers(manifest: dict) -> set[str]:
    layers = set()
    for item in _tech_items(manifest):
        if isinstance(item, dict):
            layers.add(_normalize(item.get("layer", "")))
    return layers


def _has(names: set[str], needle: str) -> bool:
    n = _normalize(needle)
    return any(n in name for name in names)


def _find_value(manifest: dict, layer_needles: list[str], tech_needles: list[str] | None = None) -> str:
    """layer 名または technology 名にマッチする最初の technology 値を返す。"""
    for item in _tech_items(manifest):
        if not isinstance(item, dict):
            continue
        layer = _normalize(item.get("layer", ""))
        tech = _normalize(item.get("technology", ""))
        for needle in layer_needles:
            if _normalize(needle) in layer:
                return item.get("technology", "").replace("`", "").strip()
        if tech_needles:
            for needle in tech_needles:
                if _normalize(needle) in tech:
                    return item.get("technology", "").replace("`", "").strip()
    return ""


def _detect_primary_language(manifest: dict) -> str:
    lang = _find_value(manifest, ["ランタイム言語", "言語", "language"])
    if lang:
        return lang
    names = _tech_names(manifest)
    for candidate in ["typescript", "go", "python", "rust", "java", "kotlin", "ruby"]:
        if _has(names, candidate):
            return candidate.capitalize() if candidate != "go" else "Go"
    return ""


def _detect_api_style(manifest: dict) -> str:
    names = _tech_names(manifest)
    parts = []
    if _has(names, "openapi"):
        parts.append("REST+OpenAPI")
    elif _has(names, "rest"):
        parts.append("REST")
    if _has(names, "grpc") or _has(names, "protocol buffers"):
        parts.append("gRPC")
    if _has(names, "graphql"):
        parts.append("GraphQL")
    return " / ".join(parts) if parts else ""


def _detect_database(manifest: dict) -> str:
    return _find_value(manifest, ["database", "db", "データベース"])


def _detect_architecture(manifest: dict) -> str:
    return _find_value(manifest, ["architecture", "アーキテクチャ"], ["clean architecture"])


def _detect_framework(manifest: dict) -> str:
    return _find_value(manifest, ["backend", "frontend", "フレームワーク"])


def _detect_test_framework(manifest: dict) -> str:
    return _find_value(manifest, ["テスト", "契約テスト", "test"])


def _detect_package_manager(manifest: dict) -> str:
    return _find_value(manifest, ["パッケージ管理", "package"])


def _resolve(manifest: dict) -> dict:
    names = _tech_names(manifest)

    api_sections = list(API_SECTIONS_COMMON)
    if _has(names, "openapi"):
        api_sections.extend(API_SECTIONS_OPENAPI)
    if _has(names, "grpc") or _has(names, "protocol buffers"):
        api_sections.extend(API_SECTIONS_GRPC)
    if _has(names, "graphql"):
        api_sections.extend(API_SECTIONS_GRAPHQL)

    data_model_sections = list(DATA_MODEL_SECTIONS_COMMON)
    if _detect_database(manifest):
        data_model_sections.extend(DATA_MODEL_SECTIONS_MIGRATION)

    coding_standards_sections = list(CODING_STANDARDS_SECTIONS_COMMON)
    if _detect_architecture(manifest):
        coding_standards_sections.extend(CODING_STANDARDS_SECTIONS_ARCH)
    coding_standards_sections.extend(CODING_STANDARDS_SECTIONS_LINT)

    workflow_sections = list(WORKFLOW_SECTIONS_COMMON)
    workflow_sections.extend(WORKFLOW_SECTIONS_ASYNC)

    return {
        "primary_language": _detect_primary_language(manifest) or "\u2014",
        "api_style": _detect_api_style(manifest) or "\u2014",
        "database": _detect_database(manifest) or "\u2014",
        "architecture": _detect_architecture(manifest) or "\u2014",
        "framework": _detect_framework(manifest) or "\u2014",
        "test_framework": _detect_test_framework(manifest) or "\u2014",
        "package_manager": _detect_package_manager(manifest) or "\u2014",
        "spec_sections": SPEC_SECTIONS_COMMON,
        "architecture_sections": ARCHITECTURE_SECTIONS_COMMON,
        "api_sections": api_sections,
        "data_model_sections": data_model_sections,
        "coding_standards_sections": coding_standards_sections,
        "workflow_sections": workflow_sections,
    }


def _yaml_quote(value: str) -> str:
    s = "" if value is None else str(value)
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_top_block(lines, key: str):
    start = None
    for idx, line in enumerate(lines):
        if line.rstrip() == f"{key}:" and _indent_of(line) == 0:
            start = idx
            break
    if start is None:
        return None, None
    last = start
    j = start + 1
    while j < len(lines):
        if lines[j].strip() == "":
            j += 1
            continue
        if _indent_of(lines[j]) > 0:
            last = j
            j += 1
            continue
        break
    return start, last


def _domain_docs_block(resolved: dict) -> list[str]:
    lines = ["domain_docs:"]
    for key in ("primary_language", "api_style", "database", "architecture",
                "framework", "test_framework", "package_manager"):
        lines.append(f"  {key}: {_yaml_quote(resolved[key])}")
    for section_key in ("spec_sections", "architecture_sections", "api_sections",
                        "data_model_sections", "coding_standards_sections",
                        "workflow_sections"):
        lines.append(f"  {section_key}:")
        for item in resolved[section_key]:
            lines.append(f"    - title: {_yaml_quote(item['title'])}")
            lines.append(f"      guidance: {_yaml_quote(item['guidance'])}")
    return lines


def _render_manifest(content: str, resolved: dict) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]
    block = _domain_docs_block(resolved)
    start, last = _find_top_block(lines, "domain_docs")
    if start is not None:
        lines = lines[:start] + block + lines[last + 1:]
    else:
        a_start, a_last = _find_top_block(lines, "quality_gate_contract")
        if a_start is not None:
            insert_at = a_last + 1
            lines = lines[:insert_at] + [""] + block + lines[insert_at:]
        else:
            lines = lines + [""] + block
    return newline.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="tech_stack から Domain 層ドキュメント変数を決定する")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        _out("ERROR", f"manifest が見つからない: {args.manifest}")
        return 2
    try:
        manifest = genlib.load_manifest(args.manifest)
    except genlib.YamlError as e:
        _out("ERROR", f"manifest 解析失敗: {e}")
        return 2

    resolved = _resolve(manifest)

    with open(args.manifest, "r", encoding="utf-8") as f:
        content = f.read()
    new_content = _render_manifest(content, resolved)
    changed = new_content != content

    if args.check:
        _out("INFO", f"domain_docs 解決結果: {resolved['primary_language']} / {resolved['api_style']} / 書き換え{'あり' if changed else 'なし'}（--check）")
        return 0
    if changed:
        with open(args.manifest, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
    _out("PASS", f"domain_docs を root manifest へ反映（{'更新あり' if changed else '更新なし=冪等'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
