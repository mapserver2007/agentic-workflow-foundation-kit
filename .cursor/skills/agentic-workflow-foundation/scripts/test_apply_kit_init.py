#!/usr/bin/env python3
"""apply_kit_init.py の fixture テスト。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPLY = HERE / "apply_kit_init.py"

MANIFEST_FIXTURE = """version: 1
project:
  name: "[要確認]"
  slug: "[要確認]"
  workflow_pattern: "[要確認]"
  one_liner: "test"
  context_budget:
    min_context_window_tokens: 200000
session:
  verification:
    gate_command: "[要確認]"
"""

INIT_VALID = """version: 1
project:
  name: my-test-project
context_budget:
  min_context_window_tokens: 200000
"""

INIT_NULL_NAME = """version: 1
project:
  name: null
context_budget:
  min_context_window_tokens: 300000
"""

INIT_MINIMAL = """version: 1
"""

INIT_BAD_VERSION = """version: 2
project:
  name: test
"""

INIT_FORBIDDEN_KEY = """version: 1
project:
  name: test
features:
  code_review: true
"""

INIT_EMPTY_NAME = """version: 1
project:
  name: ""
"""

INIT_SMALL_WINDOW = """version: 1
context_budget:
  min_context_window_tokens: 10000
"""

INIT_UNKNOWN_KEY = """version: 1
project:
  name: test
  slug: forced
"""


def _run(manifest_text: str, init_text: str, extra_args: list[str] | None = None) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory(prefix="test-apply-") as tmp:
        manifest = Path(tmp) / "manifest.yaml"
        init = Path(tmp) / "init.yaml"
        manifest.write_text(manifest_text, encoding="utf-8")
        init.write_text(init_text, encoding="utf-8")
        cmd = [sys.executable, str(APPLY), "--manifest", str(manifest), "--init", str(init)]
        if extra_args:
            cmd.extend(extra_args)
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True, env=dict(os.environ),
        )
        out = manifest.read_text(encoding="utf-8") if manifest.exists() else ""
        return result.returncode, out, result.stdout + result.stderr


def main() -> int:
    errors = []

    # 1. Valid init → name / slug / workflow_pattern が書き換わる
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_VALID)
    if rc != 0:
        errors.append(f"valid init: expected exit 0, got {rc}\n{log}")
    for needle in ['name: "my-test-project"', 'slug: "my-test-project"', 'workflow_pattern: "開発型"']:
        if needle not in out:
            errors.append(f"valid init: missing {needle!r} in manifest")

    # 2. null name → ディレクトリ名から導出
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_NULL_NAME)
    if rc != 0:
        errors.append(f"null name: expected exit 0, got {rc}\n{log}")
    if 'workflow_pattern: "開発型"' not in out:
        errors.append("null name: missing workflow_pattern")
    if "min_context_window_tokens: 300000" not in out:
        errors.append("null name: missing min_context_window_tokens 300000")

    # 3. Minimal init (name/context_budget 省略) → デフォルトで通過
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_MINIMAL)
    if rc != 0:
        errors.append(f"minimal init: expected exit 0, got {rc}\n{log}")
    if 'workflow_pattern: "開発型"' not in out:
        errors.append("minimal: missing workflow_pattern")

    # 4. Bad version → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_BAD_VERSION)
    if rc != 2:
        errors.append(f"bad version: expected exit 2, got {rc}\n{log}")

    # 5. Forbidden key (features) → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_FORBIDDEN_KEY)
    if rc != 2:
        errors.append(f"forbidden key: expected exit 2, got {rc}\n{log}")

    # 6. Empty name → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_EMPTY_NAME)
    if rc != 2:
        errors.append(f"empty name: expected exit 2, got {rc}\n{log}")

    # 7. Small window (< 50000) → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_SMALL_WINDOW)
    if rc != 2:
        errors.append(f"small window: expected exit 2, got {rc}\n{log}")

    # 8. Unknown project key → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_UNKNOWN_KEY)
    if rc != 2:
        errors.append(f"unknown key: expected exit 2, got {rc}\n{log}")

    # 9. --check → exit 0, manifest unchanged
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_VALID, ["--check"])
    if rc != 0:
        errors.append(f"--check: expected exit 0, got {rc}\n{log}")
    if 'name: "[要確認]"' not in out:
        errors.append("--check: manifest was modified (should be dry-run)")

    # 10. Idempotency: apply twice → same result
    rc1, out1, _ = _run(MANIFEST_FIXTURE, INIT_VALID)
    with tempfile.TemporaryDirectory(prefix="test-idempotent-") as tmp:
        m = Path(tmp) / "manifest.yaml"
        i = Path(tmp) / "init.yaml"
        m.write_text(out1, encoding="utf-8")
        i.write_text(INIT_VALID, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(APPLY), "--manifest", str(m), "--init", str(i)],
            check=False, capture_output=True, text=True, env=dict(os.environ),
        )
        out2 = m.read_text(encoding="utf-8")
    if out1 != out2:
        errors.append("idempotency: second apply changed manifest")
    if r.returncode != 0:
        errors.append(f"idempotency: second apply exit {r.returncode}")

    if errors:
        for e in errors:
            print(f"[test_apply_kit_init] FAIL: {e}", file=sys.stderr)
        return 1
    print("[test_apply_kit_init] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
