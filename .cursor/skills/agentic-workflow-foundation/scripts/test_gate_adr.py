#!/usr/bin/env python3
"""gate-adr.py の草案モード (--draft) と標準モードの回帰テスト。

検査対象:
  - 正常草案 → exit 0
  - 空草案 → exit 1 (G-ADR-DRAFT-EMPTY-001)
  - ID 不一致 → exit 1 (G-ADR-DRAFT-ID-001)
  - Status 不正 → exit 1 (G-ADR-DRAFT-STATUS-001)
  - 代替案不足 → exit 1 (G-ADR-ALTERNATIVES-001)
  - 標準モード: ADR なし → exit 0
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent

GATE_ADR = ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "gate-adr.py"
FIXTURES = HERE.parent / "fixtures" / "adr-drafts"


def _run_draft(fixture_name: str, expected_id: str = None) -> int:
    cmd = [sys.executable, str(GATE_ADR), "--draft", str(FIXTURES / fixture_name)]
    if expected_id:
        cmd.append(expected_id)
    result = subprocess.run(cmd, capture_output=True, text=True,
                            env={**os.environ, "CURSOR_PROJECT_DIR": str(ROOT)})
    return result.returncode


def _run_standard(args: list[str] = None) -> int:
    cmd = [sys.executable, str(GATE_ADR)] + (args or [])
    result = subprocess.run(cmd, capture_output=True, text=True,
                            env={**os.environ, "CURSOR_PROJECT_DIR": str(ROOT)})
    return result.returncode


def test_valid_draft():
    rc = _run_draft("valid-draft.md", "ADR-0001")
    assert rc == 0, f"valid draft should PASS (got exit {rc})"


def test_empty_draft():
    rc = _run_draft("empty-draft.md", "ADR-0001")
    assert rc == 1, f"empty draft should FAIL (got exit {rc})"


def test_wrong_id():
    rc = _run_draft("wrong-id-draft.md", "ADR-0001")
    assert rc == 1, f"wrong ID draft should FAIL (got exit {rc})"


def test_wrong_status():
    rc = _run_draft("wrong-status-draft.md", "ADR-0001")
    assert rc == 1, f"wrong status draft should FAIL (got exit {rc})"


def test_no_alternatives():
    rc = _run_draft("no-alternatives-draft.md", "ADR-0001")
    assert rc == 1, f"no alternatives draft should FAIL (got exit {rc})"


def test_wrong_heading_id():
    rc = _run_draft("wrong-heading-id-draft.md", "ADR-0001")
    assert rc == 1, f"wrong heading ID draft should FAIL (got exit {rc})"


def test_standard_no_adrs():
    rc = _run_standard()
    assert rc == 0, f"standard mode with no ADRs should PASS (got exit {rc})"


def test_wrapper_adr_subcommand():
    """bin/quality-gate adr --draft で引数転送と非 root CWD を検証する。"""
    wrapper = ROOT / "bin" / "quality-gate"
    draft = FIXTURES / "valid-draft.md"
    relative_draft = str(draft.relative_to(ROOT))
    result = subprocess.run(
        [str(wrapper), "adr", "--draft", relative_draft, "ADR-0001"],
        capture_output=True, text=True,
        cwd=str(ROOT / ".cursor"),  # root 以外の CWD
    )
    assert result.returncode == 0, (
        f"wrapper adr subcommand should PASS (got exit {result.returncode})\n"
        f"stderr: {result.stderr}"
    )
    wrong_id = subprocess.run(
        [str(wrapper), "adr", "--draft", relative_draft, "ADR-9999"],
        capture_output=True, text=True,
        cwd=str(ROOT / ".cursor"),
    )
    assert wrong_id.returncode != 0, (
        "wrapper must forward the expected ADR ID"
    )


def main() -> int:
    tests = [
        test_valid_draft,
        test_empty_draft,
        test_wrong_id,
        test_wrong_status,
        test_no_alternatives,
        test_wrong_heading_id,
        test_standard_no_adrs,
        test_wrapper_adr_subcommand,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}", file=sys.stderr)
            failed += 1
        except Exception as e:
            print(f"  ERROR: {t.__name__}: {e}", file=sys.stderr)
            failed += 1

    print(f"[test_gate_adr] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
