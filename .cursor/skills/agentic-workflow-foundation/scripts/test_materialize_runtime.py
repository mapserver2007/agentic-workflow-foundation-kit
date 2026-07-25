#!/usr/bin/env python3
"""materialize_runtime.py の fixture テスト。

テストシナリオ:
1. package.json 不在 → 生成、必須 scripts / packageManager あり
2. 既存 package.json → kit 所有 scripts 上書き同期、非所有キー保持
3. 冪等（同一入力で 2 回実行 → 差分なし）
4. 契約未確定（1.65 非適格）→ skip / 非破壊
5. gen 不要スタック相当 → scripts.gen なし

MATERIALIZE_VERSIONS_JSON 経由でオフラインテスト（npm registry 不使用）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "materialize_runtime.py"

VERSIONS_FIXTURE = {
    "pnpm": "9.15.4",
    "typescript": "5.8.3",
    "@redocly/cli": "1.34.2",
    "@stoplight/spectral-cli": "6.14.2",
    "openapi-typescript": "7.8.0",
    "vitest": "3.2.1",
    "@cloudflare/vitest-pool-workers": "0.8.5",
    "wrangler": "4.14.0",
    "turbo": "2.5.4",
    "@biomejs/biome": "1.9.4",
}

FULL_MANIFEST = """\
version: 1
tech_stack:
  note: "fixture"
  items:
    - layer: "実行基盤"
      technology: "Cloudflare Workers"
      version_policy: "—"
      note: "`workerd` ランタイム"
    - layer: "デプロイ CLI"
      technology: "Wrangler"
      version_policy: "v4 系"
      note: ""
    - layer: "Frontend"
      technology: "Next.js"
      version_policy: "15 / 16 系"
      note: ""
    - layer: "Backend"
      technology: "Hono"
      version_policy: "4 系"
      note: ""
    - layer: "API 定義"
      technology: "OpenAPI"
      version_policy: "3.1"
      note: ""
    - layer: "OpenAPI lint"
      technology: "Spectral"
      version_policy: "6 系"
      note: ""
    - layer: "OpenAPI bundle/diff"
      technology: "Redocly CLI"
      version_policy: "1 系"
      note: ""
    - layer: "型生成"
      technology: "openapi-typescript"
      version_policy: "7 系"
      note: ""
    - layer: "契約テスト"
      technology: "Vitest + `@cloudflare/vitest-pool-workers`"
      version_policy: "—"
      note: "`workerd` 上でテスト実行"
    - layer: "ランタイム言語"
      technology: "TypeScript"
      version_policy: "5 系"
      note: "strict"
    - layer: "パッケージ管理"
      technology: "pnpm"
      version_policy: "9 系以降"
      note: "workspace"
    - layer: "タスク管理"
      technology: "Turborepo"
      version_policy: "2 系"
      note: "任意"
session:
  verification:
    gate_command: "bin/quality-gate verify"
project:
  workflow_pattern: 開発型
  slug: "test-project"
  quality_gate:
    gen_cmd: "pnpm run gen"
    build_cmd: "pnpm run build"
    lint_cmd: "pnpm run lint"
    test_cmd: "pnpm run test"
quality_gate_contract:
  gen:
    - "OpenAPI bundle"
  build:
    - "TypeScript typecheck"
  lint:
    - "Redocly lint"
  test:
    - "Vitest"
"""

INCOMPLETE_MANIFEST = """\
version: 1
tech_stack:
  note: "incomplete"
  items:
    - layer: "パッケージ管理"
      technology: "pnpm"
      version_policy: "9 系以降"
      note: "workspace"
session:
  verification:
    gate_command: "[要確認]"
project:
  workflow_pattern: 開発型
  slug: "test-incomplete"
  quality_gate:
    gen_cmd: "[要確認]"
"""

NO_OPENAPI_MANIFEST = """\
version: 1
tech_stack:
  note: "no openapi"
  items:
    - layer: "実行基盤"
      technology: "Cloudflare Workers"
      version_policy: "—"
      note: ""
    - layer: "Frontend"
      technology: "Next.js"
      version_policy: "15 / 16 系"
      note: ""
    - layer: "Backend"
      technology: "Hono"
      version_policy: "4 系"
      note: ""
    - layer: "ランタイム言語"
      technology: "TypeScript"
      version_policy: "5 系"
      note: ""
    - layer: "パッケージ管理"
      technology: "pnpm"
      version_policy: "9 系以降"
      note: "workspace"
session:
  verification:
    gate_command: "bin/quality-gate verify"
project:
  workflow_pattern: 開発型
  slug: "test-no-openapi"
  quality_gate:
    gen_cmd: "pnpm run gen"
"""


def _run(manifest_content: str, tmp: str, extra_args=None, pkg_content=None):
    """helper: manifest を書いて materialize_runtime.py を実行する。"""
    manifest_path = os.path.join(tmp, "manifest.yaml")
    pkg_path = os.path.join(tmp, "package.json")
    versions_path = os.path.join(tmp, "versions.json")

    Path(manifest_path).write_text(manifest_content, encoding="utf-8")
    Path(versions_path).write_text(
        json.dumps(VERSIONS_FIXTURE), encoding="utf-8"
    )
    if pkg_content is not None:
        Path(pkg_path).write_text(
            json.dumps(pkg_content, indent=2), encoding="utf-8"
        )

    env = dict(os.environ, MATERIALIZE_VERSIONS_JSON=versions_path)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--manifest", manifest_path,
        "--package-json", pkg_path,
    ]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result, manifest_path, pkg_path


def test_new_package_json():
    """1. package.json 不在 → 生成、必須 scripts / packageManager あり。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, _, pkg_path = _run(FULL_MANIFEST, tmp)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}\n{result.stdout}\n{result.stderr}")
            return 1

        pkg = json.loads(Path(pkg_path).read_text(encoding="utf-8"))

        errors = []
        if "packageManager" not in pkg:
            errors.append("packageManager が存在しない")
        elif not pkg["packageManager"].startswith("pnpm@"):
            errors.append(f"packageManager が pnpm でない: {pkg['packageManager']}")

        scripts = pkg.get("scripts", {})
        for gate in ("gen", "build", "lint", "test"):
            if gate not in scripts:
                errors.append(f"scripts.{gate} が存在しない")

        dev = pkg.get("devDependencies", {})
        required_pkgs = ["typescript", "@redocly/cli", "vitest", "turbo"]
        for rp in required_pkgs:
            if rp not in dev:
                errors.append(f"devDependencies に {rp} がない")

        if pkg.get("name") != "test-project":
            errors.append(f"name が test-project でない: {pkg.get('name')}")
        if pkg.get("private") is not True:
            errors.append(f"private が true でない")

        if errors:
            print(f"FAIL: {'; '.join(errors)}")
            return 1
    return 0


def test_merge_existing():
    """2. 既存 package.json → kit 所有 scripts 上書き、非所有キー保持。"""
    existing = {
        "name": "my-app",
        "version": "1.0.0",
        "description": "My application",
        "scripts": {
            "dev": "next dev",
            "build": "echo old-build",
            "custom": "echo custom",
        },
        "dependencies": {
            "react": "^19.0.0",
        },
        "devDependencies": {
            "some-tool": "^1.0.0",
        },
    }

    with tempfile.TemporaryDirectory() as tmp:
        result, _, pkg_path = _run(FULL_MANIFEST, tmp, pkg_content=existing)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}\n{result.stdout}\n{result.stderr}")
            return 1

        pkg = json.loads(Path(pkg_path).read_text(encoding="utf-8"))

        errors = []
        if pkg.get("name") != "my-app":
            errors.append("name が上書きされた")
        if pkg.get("version") != "1.0.0":
            errors.append("version が上書きされた")
        if pkg.get("description") != "My application":
            errors.append("description が消えた")

        scripts = pkg.get("scripts", {})
        if scripts.get("dev") != "next dev":
            errors.append("非所有 scripts.dev が消えた")
        if scripts.get("custom") != "echo custom":
            errors.append("非所有 scripts.custom が消えた")
        if scripts.get("build") == "echo old-build":
            errors.append("kit 所有 scripts.build が上書きされていない")
        if "build" not in scripts:
            errors.append("scripts.build が存在しない")

        deps = pkg.get("dependencies", {})
        if deps.get("react") != "^19.0.0":
            errors.append("dependencies.react が消えた")

        dev = pkg.get("devDependencies", {})
        if "some-tool" not in dev:
            errors.append("非所有 devDependencies.some-tool が消えた")
        if "typescript" not in dev:
            errors.append("kit 所有 devDependencies.typescript が追加されていない")

        if errors:
            print(f"FAIL: {'; '.join(errors)}")
            return 1
    return 0


def test_idempotent():
    """3. 冪等: 2 回目の実行で差分なし。"""
    with tempfile.TemporaryDirectory() as tmp:
        result1, manifest_path, pkg_path = _run(FULL_MANIFEST, tmp)
        if result1.returncode != 0:
            print(f"FAIL: 1st run exit {result1.returncode}")
            return 1

        pkg1 = Path(pkg_path).read_text(encoding="utf-8")
        manifest1 = Path(manifest_path).read_text(encoding="utf-8")

        versions_path = os.path.join(tmp, "versions.json")
        env = dict(os.environ, MATERIALIZE_VERSIONS_JSON=versions_path)
        result2 = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--manifest", manifest_path,
                "--package-json", pkg_path,
            ],
            capture_output=True, text=True, env=env,
        )
        if result2.returncode != 0:
            print(f"FAIL: 2nd run exit {result2.returncode}")
            return 1

        pkg2 = Path(pkg_path).read_text(encoding="utf-8")
        manifest2 = Path(manifest_path).read_text(encoding="utf-8")

        if pkg1 != pkg2:
            print("FAIL: package.json に差分あり（冪等でない）")
            return 1
        if manifest1 != manifest2:
            print("FAIL: manifest.yaml に差分あり（冪等でない）")
            return 1
    return 0


def test_skip_ineligible():
    """4. 契約未確定（1.65 非適格）→ skip / 非破壊。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, _, pkg_path = _run(INCOMPLETE_MANIFEST, tmp)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}（0 期待）\n{result.stdout}")
            return 1
        if os.path.exists(pkg_path):
            print("FAIL: 非適格なのに package.json が生成された")
            return 1
        warn_keywords = ["スキップ", "skip", "不足", "非適格"]
        if not any(kw in result.stdout.lower() or kw in result.stdout for kw in warn_keywords):
            print(f"FAIL: WARN ログに非適格の説明なし\n{result.stdout}")
            return 1
    return 0


def test_no_gen_without_openapi():
    """5. gen 不要スタック → scripts.gen なし。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, _, pkg_path = _run(NO_OPENAPI_MANIFEST, tmp)
        # 1.65 非適格（OpenAPI 不在で _resolve は None 返却）→ skip
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}")
            return 1
        # OpenAPI 不在は 1.65 で非適格のため package.json 不生成が正
        if os.path.exists(pkg_path):
            pkg = json.loads(Path(pkg_path).read_text(encoding="utf-8"))
            if "gen" in pkg.get("scripts", {}):
                print("FAIL: openapi 不在なのに scripts.gen が存在")
                return 1
    return 0


def test_seed_files():
    """6. tsconfig.json / pnpm-workspace.yaml の seed 生成。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, _, pkg_path = _run(FULL_MANIFEST, tmp)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}")
            return 1

        pkg_dir = os.path.dirname(pkg_path)
        tsconfig = os.path.join(pkg_dir, "tsconfig.json")
        pnpm_ws = os.path.join(pkg_dir, "pnpm-workspace.yaml")

        errors = []
        if not os.path.isfile(tsconfig):
            errors.append("tsconfig.json が生成されていない")
        else:
            ts = json.loads(Path(tsconfig).read_text(encoding="utf-8"))
            if not ts.get("compilerOptions", {}).get("strict"):
                errors.append("tsconfig.json strict が true でない")

        if not os.path.isfile(pnpm_ws):
            errors.append("pnpm-workspace.yaml が生成されていない")

        if errors:
            print(f"FAIL: {'; '.join(errors)}")
            return 1
    return 0


def test_seed_no_overwrite():
    """7. seed ファイルが既存の場合は上書きしない。"""
    with tempfile.TemporaryDirectory() as tmp:
        tsconfig = os.path.join(tmp, "tsconfig.json")
        Path(tsconfig).write_text('{"custom": true}\n', encoding="utf-8")

        result, _, _ = _run(FULL_MANIFEST, tmp)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}")
            return 1

        content = Path(tsconfig).read_text(encoding="utf-8")
        if '"custom"' not in content:
            print("FAIL: 既存 tsconfig.json が上書きされた")
            return 1
    return 0


def test_gen_artifact_paths():
    """8. manifest に gen_artifact_paths が書き込まれる。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, manifest_path, _ = _run(FULL_MANIFEST, tmp)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}")
            return 1

        manifest_content = Path(manifest_path).read_text(encoding="utf-8")
        if "gen_artifact_paths:" not in manifest_content:
            print("FAIL: manifest に gen_artifact_paths がない")
            return 1
        if "openapi/bundled.yaml" not in manifest_content:
            print("FAIL: gen_artifact_paths に openapi/bundled.yaml がない")
            return 1
    return 0


def test_turbo_scripts():
    """9. Turborepo 検出時の scripts が turbo run に委譲される。"""
    with tempfile.TemporaryDirectory() as tmp:
        result, _, pkg_path = _run(FULL_MANIFEST, tmp)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}")
            return 1

        pkg = json.loads(Path(pkg_path).read_text(encoding="utf-8"))
        scripts = pkg.get("scripts", {})

        errors = []
        for gate in ("gen", "build", "lint", "test"):
            val = scripts.get(gate, "")
            if not val.startswith("turbo run "):
                errors.append(f"scripts.{gate} が turbo 委譲でない: {val}")

        if errors:
            print(f"FAIL: {'; '.join(errors)}")
            return 1
    return 0


def main() -> int:
    tests = [
        ("new_package_json", test_new_package_json),
        ("merge_existing", test_merge_existing),
        ("idempotent", test_idempotent),
        ("skip_ineligible", test_skip_ineligible),
        ("no_gen_without_openapi", test_no_gen_without_openapi),
        ("seed_files", test_seed_files),
        ("seed_no_overwrite", test_seed_no_overwrite),
        ("gen_artifact_paths", test_gen_artifact_paths),
        ("turbo_scripts", test_turbo_scripts),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"[test_materialize_runtime] RUN: {name}")
        rc = fn()
        if rc == 0:
            print(f"[test_materialize_runtime] PASS: {name}")
            passed += 1
        else:
            print(f"[test_materialize_runtime] FAIL: {name}")
            failed += 1

    print(f"[test_materialize_runtime] {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
