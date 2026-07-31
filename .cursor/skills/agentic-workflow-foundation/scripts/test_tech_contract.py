#!/usr/bin/env python3
"""tech_contract lifecycle の digest / stale / preimage / safety 回帰。"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        doc = root / "TECH.md"
        doc.write_text("# 技術\nGo\n", encoding="utf-8")
        c = base_contract(tc.source_fingerprint(doc))
        digest1 = tc.contract_digest(c)
        reordered = dict(reversed(list(c.items())))
        if digest1 != tc.contract_digest(reordered):
            print("FAIL: canonical digest changed by key order", file=sys.stderr)
            return 1
        tc.validate(c, doc, require_approval=False)
        manifest = root / "manifest.yaml"
        manifest.write_text("# preserved\nproject:\n  name: test\n", encoding="utf-8")
        preimage = hashlib.sha256(manifest.read_bytes()).hexdigest()
        tc.pin_contract(manifest, c, preimage)
        text = manifest.read_text(encoding="utf-8")
        if not text.startswith("# preserved\nproject:\n  name: test\n") or "tech_contract:" not in text:
            print("FAIL: non-owned manifest bytes were not preserved", file=sys.stderr)
            return 1
        c2 = base_contract(tc.source_fingerprint(doc))
        c2["quality_gate"]["gen"]["argv"] = ["tool", "|", "bad"]
        try:
            tc.validate(c2, doc, require_approval=False)
        except tc.SchemaError:
            pass
        else:
            print("FAIL: unsafe argv accepted", file=sys.stderr)
            return 1
        try:
            tc.pin_contract(manifest, c, preimage)
        except tc.ContractError:
            pass
        else:
            print("FAIL: stale preimage accepted", file=sys.stderr)
            return 1
    print("[test_tech_contract] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
