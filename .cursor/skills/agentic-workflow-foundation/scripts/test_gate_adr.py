#!/usr/bin/env python3
"""test_gate_adr.py — gate-adr.py の草案モード・標準モードを検証する。

fixtures/adr-drafts/ の草案ファイルに対して --draft を実行し、
期待する exit code と検査 ID の PASS/FAIL を検証する。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
GATE_SCRIPT = os.path.join(
    ROOT, ".cursor", "skills", "session-handover", "scripts", "gate-adr.py"
)
FIXTURE_DIR = os.path.join(HERE, "..", "fixtures", "adr-drafts")


def run_gate(args: list[str]) -> tuple[int, dict]:
    cmd = [sys.executable, GATE_SCRIPT] + args + ["--format=json"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        data = {"raw_stdout": result.stdout, "raw_stderr": result.stderr}
    return result.returncode, data


def check_ids(results: list[dict], expected_fails: set[str], expected_passes: set[str]) -> list[str]:
    errors = []
    for r in results:
        for c in r.get("checks", []):
            cid = c["id"]
            status = c["status"]
            if cid in expected_fails and status != "FAIL":
                errors.append(f"  期待 FAIL だが {status}: {cid} — {c.get('message', '')}")
            if cid in expected_passes and status == "FAIL":
                errors.append(f"  期待 PASS だが FAIL: {cid} — {c.get('message', '')}")
    return errors


def main():
    if not os.path.isfile(GATE_SCRIPT):
        print("[test_gate_adr] SKIP: gate-adr.py 不在（再生成前の可能性）")
        sys.exit(0)

    fixture_dir = os.path.normpath(FIXTURE_DIR)
    if not os.path.isdir(fixture_dir):
        print("[test_gate_adr] SKIP: fixtures/adr-drafts/ 不在")
        sys.exit(0)

    passed = 0
    failed = 0
    errors_all = []

    # Test 1: valid draft → PASS (exit 0)
    rc, data = run_gate(["--draft", os.path.join(fixture_dir, "valid-draft.md"), "ADR-0002"])
    if rc == 0 and data.get("status") == "PASS":
        passed += 1
    else:
        failed += 1
        errors_all.append(f"valid-draft: 期待 exit=0/PASS, 実際 exit={rc}/{data.get('status')}")

    # Test 2: empty draft → FAIL (exit 1), G-ADR-DRAFT-EMPTY-001
    rc, data = run_gate(["--draft", os.path.join(fixture_dir, "empty-draft.md")])
    if rc == 1:
        errs = check_ids(data.get("results", []), {"G-ADR-DRAFT-EMPTY-001"}, set())
        if not errs:
            passed += 1
        else:
            failed += 1
            errors_all.extend(errs)
    else:
        failed += 1
        errors_all.append(f"empty-draft: 期待 exit=1, 実際 exit={rc}")

    # Test 3: wrong ID → FAIL (exit 1), G-ADR-DRAFT-ID-001
    rc, data = run_gate(["--draft", os.path.join(fixture_dir, "wrong-id-draft.md"), "ADR-0001"])
    if rc == 1:
        errs = check_ids(data.get("results", []), {"G-ADR-DRAFT-ID-001"}, set())
        if not errs:
            passed += 1
        else:
            failed += 1
            errors_all.extend(errs)
    else:
        failed += 1
        errors_all.append(f"wrong-id-draft: 期待 exit=1, 実際 exit={rc}")

    # Test 4: wrong status → PASS (exit 0) — Status Accepted is WARN for a draft, not a FAIL
    rc, data = run_gate(["--draft", os.path.join(fixture_dir, "wrong-status-draft.md")])
    if rc == 0:
        passed += 1
    else:
        failed += 1
        errors_all.append(f"wrong-status-draft: 期待 exit=0(Status WARN only), 実際 exit={rc}")

    # Test 5: no alternatives → FAIL (exit 1), G-ADR-ALTERNATIVES-001
    rc, data = run_gate(["--draft", os.path.join(fixture_dir, "no-alternatives-draft.md")])
    if rc == 1:
        errs = check_ids(data.get("results", []), {"G-ADR-ALTERNATIVES-001"}, set())
        if not errs:
            passed += 1
        else:
            failed += 1
            errors_all.extend(errs)
    else:
        failed += 1
        errors_all.append(f"no-alternatives-draft: 期待 exit=1, 実際 exit={rc}")

    # Test 6: standard mode (docs/DECISIONS.md with ADR-0001)
    rc, data = run_gate(["ADR-0001"])
    if rc == 0 and data.get("status") == "PASS":
        passed += 1
    else:
        failed += 1
        errors_all.append(f"standard ADR-0001: 期待 exit=0/PASS, 実際 exit={rc}/{data.get('status')}")

    # Report
    total = passed + failed
    print(f"[test_gate_adr] {passed}/{total} passed")
    if errors_all:
        for e in errors_all:
            print(f"  FAIL: {e}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
