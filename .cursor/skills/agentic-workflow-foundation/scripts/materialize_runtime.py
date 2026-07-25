#!/usr/bin/env python3
"""tech_stack capability から runtime 前提（package.json 等）を物質化する（Phase 1.68）。

Phase 1.65 で決定された quality-gate 契約が「呼び出し可能」になるよう、
tech_stack の capability から scripts / deps / packageManager を動的合成して
filesystem に書き出す。

深さ: 呼び出し可能まで。pnpm install / 最小アプリ生成 / ゲート PASS 保証は範囲外。
所有権: package.json はアプリ所有。kit 所有キーは
  scripts.{gen,build,lint,test} / packageManager / tech_stack 由来 deps。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
GENLIB_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if GENLIB_DIR not in sys.path:
    sys.path.insert(0, GENLIB_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import genlib  # noqa: E402
import resolve_quality_gate as rqg  # noqa: E402

DEFAULT_MANIFEST = os.path.join(ROOT, "manifest.yaml")
DEFAULT_PACKAGE_JSON = os.path.join(ROOT, "package.json")

GATE_SCRIPTS = frozenset({"gen", "build", "lint", "test"})

GEN_ARTIFACT_PATHS = [
    "openapi/bundled.yaml",
    "packages/types/src/generated/api.d.ts",
]

# capability_key → [(npm_package, dep_section)]
CAPABILITY_PACKAGES: list[tuple[str, str, str]] = [
    ("typescript", "typescript", "devDependencies"),
    ("redocly", "@redocly/cli", "devDependencies"),
    ("spectral", "@stoplight/spectral-cli", "devDependencies"),
    ("openapi_types", "openapi-typescript", "devDependencies"),
    ("vitest_workers", "vitest", "devDependencies"),
    ("vitest_workers", "@cloudflare/vitest-pool-workers", "devDependencies"),
    ("wrangler", "wrangler", "devDependencies"),
    ("turbo", "turbo", "devDependencies"),
    ("lint_ts", "@biomejs/biome", "devDependencies"),
]

# npm_package → tech_stack technology 正規化名の部分一致キー（version_policy 参照用）
NPM_TO_TECH: dict[str, str] = {
    "typescript": "typescript",
    "@redocly/cli": "redocly cli",
    "@stoplight/spectral-cli": "spectral",
    "openapi-typescript": "openapi-typescript",
    "vitest": "vitest",
    "@cloudflare/vitest-pool-workers": "vitest",
    "wrangler": "wrangler",
    "turbo": "turborepo",
    "@biomejs/biome": "",
    "pnpm": "pnpm",
}

TSCONFIG_SEED = {
    "compilerOptions": {
        "strict": True,
        "target": "ES2022",
        "module": "ESNext",
        "moduleResolution": "bundler",
        "esModuleInterop": True,
        "skipLibCheck": True,
        "noEmit": True,
    },
}

PNPM_WORKSPACE_SEED = 'packages:\n  - "apps/*"\n  - "packages/*"\n'


def _out(level: str, msg: str) -> None:
    print(f"[materialize_runtime] {level}: {msg}")


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------

def detect_capabilities(manifest: dict) -> dict[str, bool]:
    """tech_stack.items から capability フラグを導出する。"""
    names = rqg._tech_names(manifest)
    has_ts = rqg._has(names, "typescript")
    return {
        "pnpm": rqg._has(names, "pnpm"),
        "typescript": has_ts,
        "openapi": (
            rqg._has(names, "openapi")
            and rqg._has(names, "redocly")
            and rqg._has(names, "spectral")
        ),
        "openapi_types": rqg._has(names, "openapi-typescript"),
        "spectral": rqg._has(names, "spectral"),
        "redocly": rqg._has(names, "redocly"),
        "vitest_workers": rqg._has(names, "vitest") and rqg._has(names, "cloudflare"),
        "wrangler": rqg._has(names, "wrangler"),
        "turbo": rqg._has(names, "turborepo"),
        "lint_ts": has_ts,
    }


# ---------------------------------------------------------------------------
# Script composition
# ---------------------------------------------------------------------------

def compose_scripts(caps: dict[str, bool]) -> dict[str, str]:
    """capability フラグから gate scripts を動的合成する。"""
    scripts: dict[str, str] = {}

    if caps.get("turbo"):
        if caps.get("openapi"):
            scripts["gen"] = "turbo run gen"
        scripts["build"] = "turbo run build"
        scripts["lint"] = "turbo run lint"
        scripts["test"] = "turbo run test"
        return scripts

    if caps.get("openapi"):
        gen_parts = ["redocly bundle openapi/openapi.yaml -o openapi/bundled.yaml"]
        if caps.get("openapi_types"):
            gen_parts.append(
                "openapi-typescript openapi/bundled.yaml"
                " -o packages/types/src/generated/api.d.ts"
            )
        scripts["gen"] = " && ".join(gen_parts)

    build_parts: list[str] = []
    if caps.get("typescript"):
        build_parts.append("tsc --noEmit")
    if build_parts:
        scripts["build"] = " && ".join(build_parts)

    lint_parts: list[str] = []
    if caps.get("redocly"):
        lint_parts.append("redocly lint openapi/bundled.yaml")
    if caps.get("spectral"):
        lint_parts.append("spectral lint openapi/openapi.yaml")
    if caps.get("lint_ts"):
        lint_parts.append("biome check .")
    if lint_parts:
        scripts["lint"] = " && ".join(lint_parts)

    if caps.get("vitest_workers"):
        scripts["test"] = "vitest run"

    return scripts


# ---------------------------------------------------------------------------
# Version policy helpers
# ---------------------------------------------------------------------------

def _parse_version_policy(policy: str) -> tuple[set[int] | None, bool]:
    s = (policy or "").strip()
    if s in ("", "—", "-"):
        return None, False
    open_ended = "以降" in s or "+" in s
    majors: set[int] = set()
    for m in re.finditer(r"v?(\d+)", s):
        majors.add(int(m.group(1)))
    return (majors if majors else None), open_ended


def _major_of(version: str) -> int | None:
    m = re.match(r"(\d+)", version)
    return int(m.group(1)) if m else None


def _matches_policy(version: str, majors: set[int] | None, open_ended: bool) -> bool:
    if majors is None:
        return True
    v = _major_of(version)
    if v is None:
        return True
    return (v >= min(majors)) if open_ended else (v in majors)


# ---------------------------------------------------------------------------
# npm registry
# ---------------------------------------------------------------------------

def _fetch_npm_version_real(pkg: str, version_policy: str = "") -> str:
    """npm registry から version_policy に合う latest を取得する。"""
    majors, open_ended = _parse_version_policy(version_policy)

    url = f"https://registry.npmjs.org/{pkg}/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    latest = data["version"]

    if _matches_policy(latest, majors, open_ended):
        return latest

    _out("INFO", f"{pkg} latest {latest} が policy '{version_policy}' に不一致。適合版を検索中...")
    url2 = f"https://registry.npmjs.org/{pkg}"
    req2 = urllib.request.Request(url2, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req2, timeout=60) as resp2:
        full = json.loads(resp2.read())

    stable = [
        v for v in full.get("versions", {}).keys()
        if "-" not in v and _major_of(v) is not None
    ]
    stable.sort(
        key=lambda v: [int(x) for x in v.split(".")[:3] if x.isdigit()],
        reverse=True,
    )
    for v in stable:
        if _matches_policy(v, majors, open_ended):
            _out("INFO", f"{pkg}: policy '{version_policy}' に適合する {v} を選択")
            return v

    _out("WARN", f"{pkg}: policy '{version_policy}' に合う版が見つからず latest {latest} を使用")
    return latest


def _make_fetch_fn():
    """テスト用 env override 対応の fetch 関数を返す。"""
    versions_json = os.environ.get("MATERIALIZE_VERSIONS_JSON")
    if versions_json and os.path.isfile(versions_json):
        with open(versions_json, "r", encoding="utf-8") as f:
            versions_map = json.load(f)

        def _fetch_from_file(pkg: str, _policy: str = "") -> str:
            if pkg not in versions_map:
                raise KeyError(f"テスト versions JSON に {pkg} が未定義")
            return versions_map[pkg]

        return _fetch_from_file
    return _fetch_npm_version_real


# ---------------------------------------------------------------------------
# Package resolution
# ---------------------------------------------------------------------------

def _version_policies_map(manifest: dict) -> dict[str, str]:
    """tech_stack.items の technology→version_policy マップ（正規化済みキー）。"""
    items = (manifest.get("tech_stack") or {}).get("items") or []
    policies: dict[str, str] = {}
    for item in items:
        tech = rqg._normalize(item.get("technology", ""))
        policy = (item.get("version_policy") or "").strip()
        if tech:
            policies[tech] = policy
    return policies


def _lookup_policy(npm_pkg: str, policies_map: dict[str, str]) -> str:
    tech_key = NPM_TO_TECH.get(npm_pkg, "")
    if not tech_key:
        return ""
    for k, v in policies_map.items():
        if tech_key in k:
            return v
    return ""


def resolve_packages(
    caps: dict[str, bool],
    policies_map: dict[str, str],
    fetch_version=None,
) -> tuple[dict[str, str], str | None]:
    """capability から必要な npm パッケージと version を解決する。

    Returns (devDeps, packageManager).
    """
    if fetch_version is None:
        fetch_version = _make_fetch_fn()

    dev_deps: dict[str, str] = {}
    package_manager: str | None = None

    if caps.get("pnpm"):
        policy = _lookup_policy("pnpm", policies_map)
        version = fetch_version("pnpm", policy)
        package_manager = f"pnpm@{version}"

    seen: set[str] = set()
    for cap_key, npm_pkg, _section in CAPABILITY_PACKAGES:
        if not caps.get(cap_key):
            continue
        if npm_pkg in seen:
            continue
        seen.add(npm_pkg)
        policy = _lookup_policy(npm_pkg, policies_map)
        version = fetch_version(npm_pkg, policy)
        dev_deps[npm_pkg] = f"^{version}"

    return dev_deps, package_manager


# ---------------------------------------------------------------------------
# package.json generation / merge
# ---------------------------------------------------------------------------

def build_package_json(
    existing: dict | None,
    scripts: dict[str, str],
    dev_deps: dict[str, str],
    package_manager: str | None,
    project_name: str,
) -> dict:
    """package.json を構築する（既存があれば kit 所有キーのみ同期）。"""
    if existing:
        pkg = json.loads(json.dumps(existing))
    else:
        pkg = {}

    if "name" not in pkg:
        pkg["name"] = project_name
    if "private" not in pkg:
        pkg["private"] = True

    if package_manager:
        pkg["packageManager"] = package_manager

    existing_scripts = pkg.get("scripts") or {}
    for gate in GATE_SCRIPTS:
        if gate in scripts:
            existing_scripts[gate] = scripts[gate]
        else:
            existing_scripts.pop(gate, None)
    if existing_scripts:
        pkg["scripts"] = existing_scripts
    elif "scripts" in pkg:
        del pkg["scripts"]

    existing_dev = pkg.get("devDependencies") or {}
    for dep_name, dep_version in dev_deps.items():
        existing_dev[dep_name] = dep_version
    if existing_dev:
        pkg["devDependencies"] = dict(sorted(existing_dev.items()))

    return pkg


# ---------------------------------------------------------------------------
# manifest gen_artifact_paths update
# ---------------------------------------------------------------------------

def _update_manifest_gen_paths(manifest_path: str, gen_paths: list[str]) -> bool:
    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()

    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]

    if gen_paths:
        block = ["gen_artifact_paths:"]
        for p in gen_paths:
            block.append(f'  - "{p}"')
    else:
        block = ["gen_artifact_paths: []"]

    start, last = rqg._find_top_block(lines, "gen_artifact_paths")
    if start is not None:
        new_lines = lines[:start] + block + lines[last + 1 :]
    else:
        qgc_start, qgc_last = rqg._find_top_block(lines, "quality_gate_contract")
        if qgc_start is not None:
            insert_at = qgc_last + 1
            new_lines = lines[:insert_at] + [""] + block + lines[insert_at:]
        else:
            new_lines = lines + [""] + block

    new_content = newline.join(new_lines)
    if new_content == content:
        return False
    with open(manifest_path, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)
    return True


# ---------------------------------------------------------------------------
# seed files
# ---------------------------------------------------------------------------

def _seed_file(path: str, content: str, label: str) -> bool:
    if os.path.exists(path):
        _out("INFO", f"{label} は既存（seed スキップ）")
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    _out("INFO", f"{label} を seed 生成")
    return True


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="tech_stack から runtime 前提を物質化する（Phase 1.68）"
    )
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--package-json", default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--check", action="store_true", help="dry-run")
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        _out("ERROR", f"manifest が見つからない: {args.manifest}")
        return 2
    try:
        manifest = genlib.load_manifest(args.manifest)
    except genlib.YamlError as e:
        _out("ERROR", f"manifest 解析失敗: {e}")
        return 2

    # Phase 1.65 と同一の適格判定（関数共有）
    resolved, reason = rqg._resolve(manifest)
    if resolved == "FATAL":
        _out("ERROR", reason)
        return 2
    if resolved is None:
        _out("WARN", reason or "Phase 1.65 と同一条件で非適格。物質化をスキップ")
        return 0

    caps = detect_capabilities(manifest)
    active = [k for k, v in caps.items() if v]
    _out("INFO", f"検出 capability: {', '.join(active)}")

    scripts = compose_scripts(caps)
    _out("INFO", f"合成 scripts: {', '.join(scripts.keys())}")

    gen_paths = GEN_ARTIFACT_PATHS if caps.get("openapi") else []

    if args.check:
        _out("INFO", f"物質化対象: scripts={list(scripts.keys())}, gen_paths={gen_paths}（--check）")
        return 0

    # npm registry からバージョン解決（ネットワーク必須）
    policies_map = _version_policies_map(manifest)
    try:
        dev_deps, package_manager = resolve_packages(caps, policies_map)
    except urllib.error.URLError as e:
        _out("ERROR", f"npm registry アクセス失敗: {e}")
        return 1
    except KeyError as e:
        _out("ERROR", str(e))
        return 2
    except Exception as e:
        _out("ERROR", f"パッケージバージョン解決失敗: {e}")
        return 2

    _out("INFO", f"解決 devDependencies: {len(dev_deps)} 件, packageManager: {package_manager}")

    existing_pkg = None
    if os.path.exists(args.package_json):
        try:
            with open(args.package_json, "r", encoding="utf-8") as f:
                existing_pkg = json.load(f)
            _out("INFO", "既存 package.json を検出 — kit 所有キーを同期")
        except (OSError, json.JSONDecodeError) as e:
            _out("ERROR", f"既存 package.json の読込失敗: {e}")
            return 2

    project_name = (manifest.get("project") or {}).get("slug") or "project"
    pkg = build_package_json(existing_pkg, scripts, dev_deps, package_manager, project_name)

    with open(args.package_json, "w", encoding="utf-8") as f:
        json.dump(pkg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    _out("INFO", f"package.json を{'同期更新' if existing_pkg else '新規生成'}")

    if _update_manifest_gen_paths(args.manifest, gen_paths):
        _out("INFO", "manifest.yaml gen_artifact_paths を更新")

    pkg_dir = os.path.dirname(args.package_json) or ROOT
    if caps.get("typescript"):
        _seed_file(
            os.path.join(pkg_dir, "tsconfig.json"),
            json.dumps(TSCONFIG_SEED, indent=2) + "\n",
            "tsconfig.json",
        )
    if caps.get("pnpm"):
        _seed_file(
            os.path.join(pkg_dir, "pnpm-workspace.yaml"),
            PNPM_WORKSPACE_SEED,
            "pnpm-workspace.yaml",
        )

    _out("PASS", "runtime 前提の物質化完了（呼び出し可能まで）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
