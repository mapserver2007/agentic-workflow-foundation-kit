#!/usr/bin/env python3
"""ingest_tech_stack.py の fixture テスト。

manifest の project.tech_stack_design_filename からパス解決、
CLI --design-doc override、未設定/不在時の exit 2 を検証する。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INGEST = HERE / "ingest_tech_stack.py"

MANIFEST_WITH_FILENAME = """version: 1
project:
  name: "test-project"
  slug: "test-project"
  workflow_pattern: "開発型"
  tech_stack_design_filename: "{filename}"
  context_budget:
    min_context_window_tokens: 200000
tech_stack:
  note: "seed default"
  items: []
"""

MANIFEST_WITHOUT_FILENAME = """version: 1
project:
  name: "test-project"
  slug: "test-project"
  workflow_pattern: "開発型"
  context_budget:
    min_context_window_tokens: 200000
tech_stack:
  note: "seed default"
  items: []
"""

DESIGN_DOC_FIXTURE = """# Tech Stack Design

## Other sections

Some content.

### 9. 技術スタック

> 技術スタック方針テスト。

| レイヤ | 技術 | バージョン方針 | 備考 |
| --- | --- | --- | --- |
| Runtime | Node.js | ^20 | LTS |
| Framework | Next.js | ^14 | App Router |

### 10. 次セクション
"""


def _run(manifest_text: str, design_doc_text: str | None = None,
         design_doc_name: str = "TECH.md",
         extra_args: list[str] | None = None) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory(prefix="test-ingest-") as tmp:
        manifest = Path(tmp) / "manifest.yaml"
        manifest.write_text(manifest_text, encoding="utf-8")

        cursor_docs = Path(tmp) / ".cursor" / "docs"
        cursor_docs.mkdir(parents=True, exist_ok=True)
        if design_doc_text is not None:
            doc = cursor_docs / design_doc_name
            doc.write_text(design_doc_text, encoding="utf-8")

        cmd = [sys.executable, str(INGEST), "--manifest", str(manifest)]
        if extra_args:
            cmd.extend(extra_args)
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        out = manifest.read_text(encoding="utf-8") if manifest.exists() else ""
        return result.returncode, out, result.stdout + result.stderr


def main() -> int:
    errors = []

    # 1. manifest から filename 解決 → 正常取り込み
    mtext = MANIFEST_WITH_FILENAME.replace("{filename}", "TECH.md")
    rc, out, log = _run(mtext, DESIGN_DOC_FIXTURE, design_doc_name="TECH.md")
    if rc != 0:
        errors.append(f"manifest resolve: expected exit 0, got {rc}\n{log}")
    if "Node.js" not in out:
        errors.append(f"manifest resolve: tech_stack should contain Node.js\n{out}")

    # 2. CLI --design-doc override → manifest 値を無視して CLI パスを使う
    mtext = MANIFEST_WITH_FILENAME.replace("{filename}", "NONEXISTENT.md")
    with tempfile.TemporaryDirectory(prefix="test-ingest-cli-") as tmp:
        manifest = Path(tmp) / "manifest.yaml"
        manifest.write_text(mtext, encoding="utf-8")
        cli_doc = Path(tmp) / "custom-design.md"
        cli_doc.write_text(DESIGN_DOC_FIXTURE, encoding="utf-8")
        cmd = [sys.executable, str(INGEST),
               "--manifest", str(manifest),
               "--design-doc", str(cli_doc)]
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        out_cli = manifest.read_text(encoding="utf-8")
    if result.returncode != 0:
        errors.append(f"cli override: expected exit 0, got {result.returncode}\n{result.stdout}{result.stderr}")
    if "Next.js" not in out_cli:
        errors.append(f"cli override: tech_stack should contain Next.js\n{out_cli}")

    # 3. manifest に tech_stack_design_filename がない + CLI 未指定 → exit 2
    rc, _, log = _run(MANIFEST_WITHOUT_FILENAME)
    if rc != 2:
        errors.append(f"no filename: expected exit 2, got {rc}\n{log}")

    # 4. manifest にファイル名あるが対象ファイルが存在しない → exit 2
    mtext = MANIFEST_WITH_FILENAME.replace("{filename}", "MISSING.md")
    rc, _, log = _run(mtext)
    if rc != 2:
        errors.append(f"missing doc: expected exit 2, got {rc}\n{log}")

    # 5. カスタムファイル名で正常動作
    mtext = MANIFEST_WITH_FILENAME.replace("{filename}", "MY_CUSTOM_STACK.md")
    rc, out, log = _run(mtext, DESIGN_DOC_FIXTURE, design_doc_name="MY_CUSTOM_STACK.md")
    if rc != 0:
        errors.append(f"custom filename: expected exit 0, got {rc}\n{log}")
    if "Next.js" not in out:
        errors.append(f"custom filename: tech_stack should contain Next.js\n{out}")

    # 6. 冪等性: 同じ入力で2回実行 → manifest 変化なし
    mtext = MANIFEST_WITH_FILENAME.replace("{filename}", "TECH.md")
    rc1, out1, _ = _run(mtext, DESIGN_DOC_FIXTURE, design_doc_name="TECH.md")
    if rc1 != 0:
        errors.append(f"idempotency: 1st ingest expected exit 0, got {rc1}")
    with tempfile.TemporaryDirectory(prefix="test-ingest-idempotent-") as tmp:
        manifest = Path(tmp) / "manifest.yaml"
        manifest.write_text(out1, encoding="utf-8")
        cursor_docs = Path(tmp) / ".cursor" / "docs"
        cursor_docs.mkdir(parents=True, exist_ok=True)
        (cursor_docs / "TECH.md").write_text(DESIGN_DOC_FIXTURE, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(INGEST), "--manifest", str(manifest)],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        out2 = manifest.read_text(encoding="utf-8")
    if out1 != out2:
        errors.append("idempotency: second ingest changed manifest")
    if result.returncode != 0:
        errors.append(f"idempotency: second ingest exit {result.returncode}")

    if errors:
        for e in errors:
            print(f"[test_ingest_tech_stack] FAIL: {e}", file=sys.stderr)
        return 1
    print("[test_ingest_tech_stack] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
