#!/usr/bin/env python3
"""tech_contract lifecycle の digest / stale / preimage / safety 回帰。"""
from __future__ import annotations

import hashlib
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract  # noqa: E402


def _failing_named_temporary_file(real_factory):
    def factory(*args, **kwargs):
        actual = real_factory(*args, **kwargs)

        class FailingWrite:
            name = actual.name

            def __enter__(self):
                return self

            def write(self, payload):
                raise OSError("injected write failure")

            def __exit__(self, exc_type, exc, traceback):
                actual.close()
                return False

        return FailingWrite()

    return factory


def _assert_pin_failure_cleanup(root: Path, contract: dict) -> None:
    write_dir = root / "write-failure"
    write_dir.mkdir()
    write_manifest = write_dir / "manifest.yaml"
    write_manifest.write_text("project:\n  name: write-failure\n", encoding="utf-8")
    before = write_manifest.read_bytes()
    before_entries = set(write_dir.iterdir())
    real_factory = tempfile.NamedTemporaryFile
    with patch(
        "tech_contract.rp.tempfile.NamedTemporaryFile",
        side_effect=_failing_named_temporary_file(real_factory),
    ):
        try:
            tc.pin_contract(write_manifest, contract, tc.file_digest(write_manifest))
        except OSError:
            pass
        else:
            raise AssertionError("manifest write failure must propagate")
    assert write_manifest.read_bytes() == before
    assert set(write_dir.iterdir()) == before_entries

    replace_dir = root / "replace-failure"
    replace_dir.mkdir()
    replace_manifest = replace_dir / "manifest.yaml"
    replace_manifest.write_text("project:\n  name: replace-failure\n", encoding="utf-8")
    before = replace_manifest.read_bytes()
    before_entries = set(replace_dir.iterdir())
    with patch("tech_contract.rp.os.replace", side_effect=OSError("injected replace failure")):
        try:
            tc.pin_contract(replace_manifest, contract, tc.file_digest(replace_manifest))
        except OSError:
            pass
        else:
            raise AssertionError("manifest replace failure must propagate")
    assert replace_manifest.read_bytes() == before
    assert set(replace_dir.iterdir()) == before_entries


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
        manifest.chmod(0o640)
        preimage = hashlib.sha256(manifest.read_bytes()).hexdigest()
        tc.pin_contract(manifest, c, preimage)
        if stat.S_IMODE(manifest.stat().st_mode) != 0o640:
            print("FAIL: manifest mode was not preserved", file=sys.stderr)
            return 1
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
        try:
            _assert_pin_failure_cleanup(root, c)
        except AssertionError as exc:
            print(f"FAIL: manifest atomic cleanup: {exc}", file=sys.stderr)
            return 1
    print("[test_tech_contract] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
