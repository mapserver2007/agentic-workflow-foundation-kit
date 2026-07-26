#!/usr/bin/env python3
"""bootstrap_root_manifest の死蔵ブロック除去テスト。

outputs / quality_gate_contract が root に持ち込まれない・既存から除去される
ことを検証する。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
GENLIB_DIR = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
if str(GENLIB_DIR) not in sys.path:
    sys.path.insert(0, str(GENLIB_DIR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import genlib  # noqa: E402
import run_resolved_engine as rre  # noqa: E402

SEED_FIXTURE = """\
version: 1
marker_id: test-marker
framework:
  naming:
    meta_pattern: "UPPER_SNAKE_CASE.md"
tech_stack:
  note: "fixture"
  items: []
quality_gate_contract:
  gen:
  build:
  lint:
  test:
# (2b) outputs
outputs:
  - path: AGENTS.md
    template: AGENTS.md.template
    mode: render
  - path: CLAUDE.md
    template: CLAUDE.md.template
    mode: render
project:
  name: "test"
  workflow_pattern: "開発型"
"""

ROOT_WITH_DEAD = """\
version: 1
marker_id: test-marker
framework:
  naming:
    meta_pattern: "OLD"
tech_stack:
  note: "fixture"
  items: []
# old comment block
quality_gate_contract:
  gen:
    - "legacy"
  build:
    - "legacy"
# (2b) outputs
outputs:
  - path: AGENTS.md
    template: AGENTS.md.template
    mode: render
project:
  name: "test"
  workflow_pattern: "開発型"
"""


def _has_dead_blocks(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped == "outputs:" and not line.startswith(" "):
            found.append("outputs")
        if stripped == "quality_gate_contract:" and not line.startswith(" "):
            found.append("quality_gate_contract")
    return found


def test_01_new_root_strips_dead():
    """seed から新規生成時に outputs / quality_gate_contract が除去される。"""
    with tempfile.TemporaryDirectory() as tmp:
        seed = Path(tmp) / "seed.yaml"
        root = Path(tmp) / "root.yaml"
        seed.write_text(SEED_FIXTURE, encoding="utf-8")
        rc = rre.bootstrap_root_manifest(str(seed), str(root))
        if rc != 0:
            print(f"bootstrap returned {rc}", file=sys.stderr)
            return 1
        text = root.read_text(encoding="utf-8")
        dead = _has_dead_blocks(text)
        if dead:
            print(f"new root still contains dead blocks: {dead}", file=sys.stderr)
            return 1
        if "tech_stack:" not in text or "project:" not in text:
            print("overlay keys were incorrectly removed", file=sys.stderr)
            return 1
    return 0


def test_02_existing_root_strips_dead():
    """既存 root から outputs / quality_gate_contract とコメントが除去される。"""
    with tempfile.TemporaryDirectory() as tmp:
        seed = Path(tmp) / "seed.yaml"
        root = Path(tmp) / "root.yaml"
        seed.write_text(SEED_FIXTURE, encoding="utf-8")
        root.write_text(ROOT_WITH_DEAD, encoding="utf-8")
        rc = rre.bootstrap_root_manifest(str(seed), str(root))
        if rc != 0:
            print(f"bootstrap returned {rc}", file=sys.stderr)
            return 1
        text = root.read_text(encoding="utf-8")
        dead = _has_dead_blocks(text)
        if dead:
            print(f"existing root still contains dead blocks: {dead}", file=sys.stderr)
            return 1
        if "tech_stack:" not in text or "project:" not in text:
            print("overlay keys were incorrectly removed", file=sys.stderr)
            return 1
        if "# old comment block" in text:
            print("orphan comment not removed", file=sys.stderr)
            return 1
    return 0


def test_03_framework_synced():
    """framework が seed から正しく同期され、dead block 除去と共存する。"""
    with tempfile.TemporaryDirectory() as tmp:
        seed = Path(tmp) / "seed.yaml"
        root = Path(tmp) / "root.yaml"
        seed.write_text(SEED_FIXTURE, encoding="utf-8")
        root.write_text(ROOT_WITH_DEAD, encoding="utf-8")
        rre.bootstrap_root_manifest(str(seed), str(root))
        text = root.read_text(encoding="utf-8")
        if 'meta_pattern: "OLD"' in text:
            print("framework not synced from seed", file=sys.stderr)
            return 1
        if 'meta_pattern: "UPPER_SNAKE_CASE.md"' not in text:
            print("seed framework not applied", file=sys.stderr)
            return 1
    return 0


def test_04_idempotent():
    """2回実行で内容が変わらない。"""
    with tempfile.TemporaryDirectory() as tmp:
        seed = Path(tmp) / "seed.yaml"
        root = Path(tmp) / "root.yaml"
        seed.write_text(SEED_FIXTURE, encoding="utf-8")
        root.write_text(ROOT_WITH_DEAD, encoding="utf-8")
        rre.bootstrap_root_manifest(str(seed), str(root))
        first = root.read_text(encoding="utf-8")
        rre.bootstrap_root_manifest(str(seed), str(root))
        second = root.read_text(encoding="utf-8")
        if first != second:
            print("bootstrap not idempotent", file=sys.stderr)
            return 1
    return 0


def test_05_crlf_no_crash():
    """CRLF 入力でクラッシュせず dead block が除去される（CRLF 維持は pre-existing 未対応）。"""
    with tempfile.TemporaryDirectory() as tmp:
        seed = Path(tmp) / "seed.yaml"
        root = Path(tmp) / "root.yaml"
        seed.write_text(SEED_FIXTURE, encoding="utf-8")
        crlf = ROOT_WITH_DEAD.replace("\n", "\r\n")
        root.write_text(crlf, encoding="utf-8", newline="")
        rc = rre.bootstrap_root_manifest(str(seed), str(root))
        if rc != 0:
            print(f"bootstrap crashed with CRLF input: exit {rc}", file=sys.stderr)
            return 1
        text = root.read_text(encoding="utf-8")
        dead = _has_dead_blocks(text)
        if dead:
            print(f"dead blocks remain with CRLF: {dead}", file=sys.stderr)
            return 1
    return 0


def test_06_resolved_equivalent():
    """dead block 除去前後で resolved_manifest() の結果が等価。"""
    seed_path = str(HERE.parent / "manifest.yaml")
    if not os.path.isfile(seed_path):
        print("seed manifest not found, skip", file=sys.stderr)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        root_with = Path(tmp) / "root_with.yaml"
        root_without = Path(tmp) / "root_without.yaml"
        seed_text = Path(seed_path).read_text(encoding="utf-8")
        root_with.write_text(seed_text, encoding="utf-8")
        lines = seed_text.splitlines()
        stripped = rre._strip_dead_blocks(list(lines))
        root_without.write_text("\n".join(stripped) + "\n", encoding="utf-8")

        m1 = rre.resolved_manifest(seed_path, str(root_with))
        m2 = rre.resolved_manifest(seed_path, str(root_without))

        for key in rre.ROOT_OVERLAY_KEYS:
            if m1.get(key) != m2.get(key):
                print(f"resolved differs at {key}", file=sys.stderr)
                return 1
        if m1.get("quality_gate_contract") != m2.get("quality_gate_contract"):
            print("quality_gate_contract differs after resolve", file=sys.stderr)
            return 1
    return 0


ALL = [
    test_01_new_root_strips_dead,
    test_02_existing_root_strips_dead,
    test_03_framework_synced,
    test_04_idempotent,
    test_05_crlf_no_crash,
    test_06_resolved_equivalent,
]


def main() -> int:
    passed = 0
    for fn in ALL:
        rc = fn()
        if rc != 0:
            print(f"FAIL: {fn.__name__}")
            return 1
        passed += 1
    print(f"[test_bootstrap_dead_blocks] PASS ({passed}/{len(ALL)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
