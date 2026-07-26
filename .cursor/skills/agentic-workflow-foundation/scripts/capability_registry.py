#!/usr/bin/env python3
"""共有 capability レジストリ（Phase 1.65 / 1.68 統合 SoT）。

tech_stack → capability → contract / scripts / artifact_paths を純関数で導出する。
新スタック追加時は本ファイルに Capability 断片を追加するだけで契約が成立する。
seed / root manifest にスタック固有キーを増やさない。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# tech_stack ヘルパー
# ---------------------------------------------------------------------------

def _normalize(value: str) -> str:
    text = (value or "").replace("`", "").strip().lower()
    return re.sub(r"\s+", " ", text)


def tech_names(manifest: dict) -> set[str]:
    """manifest.tech_stack.items から正規化済みテック名 set を返す。"""
    items = (manifest.get("tech_stack") or {}).get("items") or []
    names: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            names.add(_normalize(item.get("technology", "")))
    return names


def has_tech(names: set[str], needle: str) -> bool:
    """正規化済み名前 set に needle（部分一致）が含まれるか判定する。"""
    n = _normalize(needle)
    return any(n in name for name in names)


# ---------------------------------------------------------------------------
# Capability 定義
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Capability:
    """1 つの capability 断片。contract 1 行と（任意の）script 断片を保持する。"""
    id: str
    gate: str
    detect_all: tuple[str, ...]
    contract: str
    script: str | None = None
    artifact_paths: tuple[str, ...] = ()


CAPABILITIES: tuple[Capability, ...] = (
    # --- GEN ---
    Capability(
        id="openapi_bundle",
        gate="gen",
        detect_all=("openapi", "redocly", "spectral"),
        contract="OpenAPI bundle を生成し、bundle 成功を検証する",
        script="redocly bundle openapi/openapi.yaml -o openapi/bundled.yaml",
        artifact_paths=("openapi/bundled.yaml",),
    ),
    Capability(
        id="openapi_types",
        gate="gen",
        detect_all=("openapi-typescript",),
        contract="OpenAPI 由来の型生成、または生成物の再生成差分チェックを実行する",
        script=(
            "openapi-typescript openapi/bundled.yaml"
            " -o packages/types/src/generated/api.d.ts"
        ),
        artifact_paths=("packages/types/src/generated/api.d.ts",),
    ),
    # --- BUILD ---
    Capability(
        id="typescript_typecheck",
        gate="build",
        detect_all=("typescript",),
        contract="TypeScript typecheck を実行する",
        script="tsc --noEmit",
    ),
    Capability(
        id="nextjs_build",
        gate="build",
        detect_all=("next.js",),
        contract="Next.js / OpenNext build を実行する",
    ),
    Capability(
        id="hono_build",
        gate="build",
        detect_all=("hono",),
        contract="Hono Worker build を実行する",
    ),
    # --- LINT ---
    Capability(
        id="redocly_lint",
        gate="lint",
        detect_all=("redocly",),
        contract="Redocly lint を実行する",
        script="redocly lint openapi/bundled.yaml",
    ),
    Capability(
        id="spectral_lint",
        gate="lint",
        detect_all=("spectral",),
        contract="Spectral lint を実行する",
        script="spectral lint openapi/openapi.yaml",
    ),
    Capability(
        id="lint_ts",
        gate="lint",
        detect_all=("typescript",),
        contract="TypeScript / ESLint 相当の静的検査を実行する",
        script="biome check .",
    ),
    # --- TEST ---
    Capability(
        id="vitest_run",
        gate="test",
        detect_all=("vitest", "cloudflare"),
        contract="Vitest を実行する",
        script="vitest run",
    ),
    Capability(
        id="workers_pool_test",
        gate="test",
        detect_all=("vitest", "cloudflare"),
        contract="Cloudflare Workers pool 上のテストを実行する",
    ),
    Capability(
        id="openapi_contract_test",
        gate="test",
        detect_all=("openapi", "vitest", "cloudflare"),
        contract="OpenAPI contract test を実行する",
    ),
    Capability(
        id="response_validation_test",
        gate="test",
        detect_all=("openapi", "vitest", "cloudflare"),
        contract="response validation test を実行する",
    ),
)

ELIGIBILITY_REQUIRED_TECHS: tuple[str, ...] = (
    "pnpm",
    "next.js",
    "hono",
    "typescript",
    "cloudflare workers",
    "openapi",
    "redocly",
    "spectral",
    "vitest",
)

GATES: tuple[str, ...] = ("gen", "build", "lint", "test")


# ---------------------------------------------------------------------------
# 適格判定
# ---------------------------------------------------------------------------

def check_eligibility(manifest: dict) -> tuple[str, str | None]:
    """開発型フルスタック適格判定。

    Returns ``("PASS", None)`` / ``("SKIP", reason)`` / ``("FATAL", reason)``。
    """
    pattern = str((manifest.get("project") or {}).get("workflow_pattern") or "")
    if pattern != "開発型":
        return "FATAL", f"workflow_pattern が開発型でない: {pattern!r}（開発型専用）"
    names = tech_names(manifest)
    missing = [t for t in ELIGIBILITY_REQUIRED_TECHS if not has_tech(names, t)]
    if missing:
        return "SKIP", f"開発型 G-* 決定に必要な技術が不足: {', '.join(missing)}"
    return "PASS", None


# ---------------------------------------------------------------------------
# 導出関数（純関数）
# ---------------------------------------------------------------------------

def active_capabilities(manifest: dict) -> list[Capability]:
    """manifest から有効な Capability のリストを返す。"""
    names = tech_names(manifest)
    return [
        cap for cap in CAPABILITIES
        if all(has_tech(names, t) for t in cap.detect_all)
    ]


def detect_capabilities(manifest: dict) -> dict[str, bool]:
    """tech_stack.items から capability フラグ dict を導出する（1.68 互換）。"""
    names = tech_names(manifest)
    has_ts = has_tech(names, "typescript")
    return {
        "pnpm": has_tech(names, "pnpm"),
        "typescript": has_ts,
        "openapi": (
            has_tech(names, "openapi")
            and has_tech(names, "redocly")
            and has_tech(names, "spectral")
        ),
        "openapi_types": has_tech(names, "openapi-typescript"),
        "spectral": has_tech(names, "spectral"),
        "redocly": has_tech(names, "redocly"),
        "vitest_workers": has_tech(names, "vitest") and has_tech(names, "cloudflare"),
        "wrangler": has_tech(names, "wrangler"),
        "turbo": has_tech(names, "turborepo"),
        "lint_ts": has_ts,
    }


def compose_contract(manifest: dict) -> dict[str, list[str]]:
    """有効な capabilities から quality_gate_contract dict を合成する。"""
    caps = active_capabilities(manifest)
    contract: dict[str, list[str]] = {g: [] for g in GATES}
    for cap in caps:
        contract[cap.gate].append(cap.contract)
    return contract


def compose_scripts(manifest: dict) -> dict[str, str]:
    """有効な capabilities から gate scripts を合成する。"""
    names = tech_names(manifest)
    has_turbo = has_tech(names, "turborepo")
    caps = active_capabilities(manifest)

    if has_turbo:
        scripts: dict[str, str] = {}
        gates_with_caps = {cap.gate for cap in caps}
        for gate in GATES:
            if gate in gates_with_caps:
                scripts[gate] = f"turbo run {gate}"
        return scripts

    gate_parts: dict[str, list[str]] = {g: [] for g in GATES}
    for cap in caps:
        if cap.script:
            gate_parts[cap.gate].append(cap.script)

    return {
        gate: " && ".join(parts)
        for gate, parts in gate_parts.items()
        if parts
    }


def compose_artifact_paths(manifest: dict) -> list[str]:
    """有効な capabilities から gen_artifact_paths を合成する。"""
    caps = active_capabilities(manifest)
    paths: list[str] = []
    for cap in caps:
        paths.extend(cap.artifact_paths)
    return paths


def compose_gate_cmds(manifest: dict) -> dict[str, str] | None:
    """パッケージマネージャ capability から抽象ゲートコマンドを導出する。"""
    names = tech_names(manifest)
    if has_tech(names, "pnpm"):
        return {
            "gen_cmd": "pnpm run gen",
            "build_cmd": "pnpm run build",
            "lint_cmd": "pnpm run lint",
            "test_cmd": "pnpm run test",
        }
    return None
