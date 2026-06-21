#!/usr/bin/env python3
"""resolve_quality_gate.py の最小 fixture テスト。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESOLVER = HERE / "resolve_quality_gate.py"


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
            'gate_command: "pnpm run build && pnpm run lint && pnpm run test"',
            "quality_gate_contract:",
            "  gen:",
            "OpenAPI bundle",
            "Cloudflare Workers pool",
        ]
        missing = [needle for needle in expected if needle not in out]
        if missing:
            print(f"missing expected content: {missing}", file=sys.stderr)
            return 1
        if 'gate_command: "pnpm run gen' in out:
            print("G-GEN must not be included in session.verification.gate_command", file=sys.stderr)
            return 1
        second = subprocess.run(
            [sys.executable, str(RESOLVER), "--manifest", str(manifest), "--check"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if second.returncode != 0:
            print(second.stdout)
            print(second.stderr, file=sys.stderr)
            return second.returncode
    print("[test_resolve_quality_gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
