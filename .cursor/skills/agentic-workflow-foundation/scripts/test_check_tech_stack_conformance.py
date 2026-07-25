#!/usr/bin/env python3
"""check_tech_stack_conformance.py の fail-closed テスト。

プランで指定されたシナリオ:
1. 1.65 適格相当 + 1.68 未実行（package.json 不在）→ exit 1
2. 1.65 非適格（契約未確定）+ package.json 不在 → exit 0（fail-open 維持）
3. 1.65 適格 + 1.68 実行済み → scripts 存在確認可能
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "check_tech_stack_conformance.py"

ELIGIBLE_MANIFEST = """\
version: 1
tech_stack:
  note: "fixture"
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
    - layer: "契約テスト"
      technology: "Vitest + `@cloudflare/vitest-pool-workers`"
      version_policy: "—"
      note: ""
    - layer: "ランタイム言語"
      technology: "TypeScript"
      version_policy: "5 系"
      note: ""
    - layer: "パッケージ管理"
      technology: "pnpm"
      version_policy: "9 系以降"
      note: ""
project:
  workflow_pattern: 開発型
  quality_gate:
    gen_cmd: "pnpm run gen"
    build_cmd: "pnpm run build"
    lint_cmd: "pnpm run lint"
    test_cmd: "pnpm run test"
"""

INELIGIBLE_MANIFEST = """\
version: 1
tech_stack:
  note: "incomplete"
  items:
    - layer: "パッケージ管理"
      technology: "pnpm"
      version_policy: "9 系以降"
      note: ""
project:
  workflow_pattern: 開発型
  quality_gate:
    gen_cmd: "[要確認]"
"""


def _run(manifest_content: str, tmp: str, pkg_content=None):
    manifest_path = os.path.join(tmp, "manifest.yaml")
    pkg_path = os.path.join(tmp, "package.json")
    Path(manifest_path).write_text(manifest_content, encoding="utf-8")
    if pkg_content is not None:
        Path(pkg_path).write_text(
            json.dumps(pkg_content, indent=2), encoding="utf-8"
        )
    env = dict(os.environ)
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--manifest", manifest_path,
            "--package-json", pkg_path,
        ],
        capture_output=True, text=True, env=env,
    )
    return result


def test_fail_closed_no_package_json():
    """1. 契約確定 + package.json 不在 → exit 1。"""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(ELIGIBLE_MANIFEST, tmp)
        if result.returncode != 1:
            print(f"FAIL: exit {result.returncode}（1 期待）\n{result.stdout}")
            return 1
        if "契約確定" not in result.stdout and "不在" not in result.stdout:
            print(f"FAIL: fail-closed メッセージなし\n{result.stdout}")
            return 1
    return 0


def test_fail_open_ineligible():
    """2. 契約未確定 + package.json 不在 → exit 0。"""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(INELIGIBLE_MANIFEST, tmp)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}（0 期待）\n{result.stdout}")
            return 1
    return 0


def test_scripts_check_with_package():
    """3. 契約確定 + package.json あり + scripts 存在 → exit 0。"""
    pkg = {
        "name": "test",
        "packageManager": "pnpm@9.15.0",
        "scripts": {
            "gen": "turbo run gen",
            "build": "turbo run build",
            "lint": "turbo run lint",
            "test": "turbo run test",
        },
        "devDependencies": {
            "typescript": "^5.8.3",
            "next": "^15.2.0",
            "hono": "^4.7.0",
            "@redocly/cli": "^1.34.0",
            "@stoplight/spectral-cli": "^6.14.0",
            "vitest": "^3.2.0",
            "@cloudflare/vitest-pool-workers": "^0.8.0",
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(ELIGIBLE_MANIFEST, tmp, pkg_content=pkg)
        if result.returncode != 0:
            print(f"FAIL: exit {result.returncode}（0 期待）\n{result.stdout}")
            return 1
    return 0


def test_missing_scripts_fail():
    """4. 契約確定 + package.json あり + scripts 欠落 → exit 1。"""
    pkg = {
        "name": "test",
        "packageManager": "pnpm@9.15.0",
        "scripts": {
            "dev": "next dev",
        },
        "devDependencies": {
            "typescript": "^5.8.3",
            "next": "^15.2.0",
            "hono": "^4.7.0",
            "@redocly/cli": "^1.34.0",
            "@stoplight/spectral-cli": "^6.14.0",
            "vitest": "^3.2.0",
            "@cloudflare/vitest-pool-workers": "^0.8.0",
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(ELIGIBLE_MANIFEST, tmp, pkg_content=pkg)
        if result.returncode != 1:
            print(f"FAIL: exit {result.returncode}（1 期待）\n{result.stdout}")
            return 1
        if "欠落" not in result.stdout:
            print(f"FAIL: 欠落メッセージなし\n{result.stdout}")
            return 1
    return 0


def main() -> int:
    tests = [
        ("fail_closed_no_package_json", test_fail_closed_no_package_json),
        ("fail_open_ineligible", test_fail_open_ineligible),
        ("scripts_check_with_package", test_scripts_check_with_package),
        ("missing_scripts_fail", test_missing_scripts_fail),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"[test_conformance] RUN: {name}")
        rc = fn()
        if rc == 0:
            print(f"[test_conformance] PASS: {name}")
            passed += 1
        else:
            print(f"[test_conformance] FAIL: {name}")
            failed += 1

    print(f"[test_conformance] {passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
