#!/usr/bin/env python3
"""resolve_quality_gate.py の最小 fixture テスト。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RESOLVER = HERE / "resolve_quality_gate.py"
GENLIB_DIR = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
if str(GENLIB_DIR) not in sys.path:
    sys.path.insert(0, str(GENLIB_DIR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import genlib  # noqa: E402
import capability_registry as reg  # noqa: E402


FIXTURE = """version: 1
tech_stack:
  note: "fixture"
  items:
    - layer: "実行基盤"
      technology: "Cloudflare Workers"
      version_policy: "—"
      note: "`workerd` ランタイム"
    - layer: "Frontend"
      technology: "Next.js"
      version_policy: "15 / 16 系"
      note: "OpenNext"
    - layer: "Backend"
      technology: "Hono"
      version_policy: "4 系"
      note: "Workers"
    - layer: "API 定義"
      technology: "OpenAPI"
      version_policy: "3.1"
      note: "JSON Schema"
    - layer: "OpenAPI lint"
      technology: "Spectral"
      version_policy: "6 系"
      note: "lint"
    - layer: "OpenAPI bundle/diff"
      technology: "Redocly CLI"
      version_policy: "1 系"
      note: "bundle"
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
    gate_command: "[要確認]"
project:
  workflow_pattern: 開発型
  quality_gate:
    gen_cmd: "[要確認]"
    build_cmd: "[要確認]"
    lint_cmd: "[要確認]"
    test_cmd: "[要確認]"
quality_gate_contract:
  gen:
    - "legacy contract line"
  build:
    - "legacy"
  lint:
    - "legacy"
  test:
    - "legacy"
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        manifest = Path(tmp) / "manifest.yaml"
        manifest.write_text(FIXTURE, encoding="utf-8")
        env = dict(os.environ)
        result = subprocess.run(
            [sys.executable, str(RESOLVER), "--manifest", str(manifest)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return result.returncode
        out = manifest.read_text(encoding="utf-8")
        expected = [
            'gen_cmd: "pnpm run gen"',
            'build_cmd: "pnpm run build"',
            'lint_cmd: "pnpm run lint"',
            'test_cmd: "pnpm run test"',
            'gate_command: "bin/quality-gate verify"',
        ]
        missing = [needle for needle in expected if needle not in out]
        if missing:
            print(f"missing expected content: {missing}", file=sys.stderr)
            return 1
        if "quality_gate_contract:" in out:
            print("quality_gate_contract must not be persisted in root manifest", file=sys.stderr)
            return 1
        if 'gate_command: "pnpm run' in out:
            print("gate_command must use wrapper, not raw pnpm commands", file=sys.stderr)
            return 1

        parsed = genlib.load_manifest(str(manifest))
        contract = reg.compose_contract(parsed)
        contract_lines = sum(len(v) for v in contract.values())
        if contract_lines != 12:
            print(f"expected 12 composed contract lines, got {contract_lines}", file=sys.stderr)
            return 1
        if contract["gen"][0] != "OpenAPI bundle を生成し、bundle 成功を検証する":
            print("unexpected gen contract content", file=sys.stderr)
            return 1
        if not any("Cloudflare Workers pool" in line for line in contract["test"]):
            print("missing workers pool contract line", file=sys.stderr)
            return 1
        if reg.compose_contract(parsed) != reg.compose_contract(parsed):
            print("compose_contract must be idempotent", file=sys.stderr)
            return 1

        check = subprocess.run(
            [sys.executable, str(RESOLVER), "--manifest", str(manifest), "--check"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if check.returncode != 0:
            print(check.stdout)
            print(check.stderr, file=sys.stderr)
            return check.returncode
    print("[test_resolve_quality_gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
