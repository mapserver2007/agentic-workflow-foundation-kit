#!/usr/bin/env python3
"""contract runtime action の generic projection 回帰（read-only materialize）。"""
from __future__ import annotations

import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import materialize_runtime as runtime  # noqa: E402
import runtime_plan as rp  # noqa: E402
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract, write_sealed_manifest  # noqa: E402


def _action(target: str, content: str, conflict_policy: str = "merge_owned") -> dict:
    return {
        "kind": "owned-text-render",
        "target": target,
        "ownership": "tool",
        "conflict_policy": conflict_policy,
        "evidence_ref": "fixture",
        "content": content,
    }


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


def test_atomic_write_modes_and_cleanup(root: Path) -> None:
    existing = root / "mode-existing.txt"
    existing.write_text("before\n", encoding="utf-8")
    existing.chmod(0o640)
    rp.apply_file_action(_action(existing.name, "after\n"), root)
    assert stat.S_IMODE(existing.stat().st_mode) == 0o640

    created = root / "mode-created.txt"
    rp.apply_file_action(_action(created.name, "created\n"), root)
    assert stat.S_IMODE(created.stat().st_mode) == 0o644

    marker = root / "state.json"
    marker.write_text("{}\n", encoding="utf-8")
    marker.chmod(0o600)
    rp._atomic_write_json(marker, {"ready": True})
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600

    new_marker = root / "new-state.json"
    rp._atomic_write_json(new_marker, {"ready": True})
    assert stat.S_IMODE(new_marker.stat().st_mode) == 0o644

    write_failure = root / "write-failure.txt"
    real_factory = tempfile.NamedTemporaryFile
    before_entries = set(root.iterdir())
    with patch(
        "runtime_plan.tempfile.NamedTemporaryFile",
        side_effect=_failing_named_temporary_file(real_factory),
    ):
        try:
            rp.apply_file_action(_action(write_failure.name, "content\n"), root)
        except OSError:
            pass
        else:
            raise AssertionError("write failure must propagate")
    assert not write_failure.exists()
    assert set(root.iterdir()) == before_entries

    before = marker.read_bytes()
    before_entries = set(root.iterdir())
    with patch("runtime_plan.os.replace", side_effect=OSError("injected replace failure")):
        try:
            rp._atomic_write_json(marker, {"ready": False})
        except OSError:
            pass
        else:
            raise AssertionError("replace failure must propagate")
    assert marker.read_bytes() == before
    assert set(root.iterdir()) == before_entries


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        design = root / "docs" / "TECH.md"
        design.parent.mkdir(parents=True, exist_ok=True)
        design_text = "# fixture\n"
        design.write_text(design_text, encoding="utf-8")
        fp = tc.source_fingerprint(design)
        contract = base_contract(fp)
        contract["runtime_materialization"]["actions"] = [{
            "kind": "owned-text-render",
            "target": "generated/config.txt",
            "ownership": "tool",
            "conflict_policy": "fail",
            "evidence_ref": "fixture",
            "content": "contract-owned\n",
        }]
        manifest, design = write_sealed_manifest(root, contract, design_text)

        result = subprocess.run(
            [sys.executable, str(HERE / "materialize_runtime.py"),
             "--manifest", str(manifest), "--design-doc", str(design)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 2:
            print("FAIL: apply path not rejected", result.stderr)
            return 1

        if runtime.main(["--manifest", str(manifest), "--design-doc", str(design), "--check"]) != 0:
            print("FAIL: --check renderability")
            return 1

        actions = [{
            "kind": "owned-text-render",
            "target": "generated/config.txt",
            "ownership": "tool",
            "conflict_policy": "fail",
            "evidence_ref": "fixture",
            "content": "contract-owned\n",
        }]
        for action in actions:
            try:
                rp.apply_file_action(action, root, dry_run=True)
            except Exception:
                print("FAIL: dry-run")
                return 1
        if (root / "generated/config.txt").exists():
            print("FAIL: dry-run wrote target")
            return 1
        rp.apply_file_action(actions[0], root, dry_run=False)
        target = root / "generated/config.txt"
        if target.read_text(encoding="utf-8") != "contract-owned\n":
            print("FAIL: apply via runtime_plan")
            return 1
        target.write_text("drift\n", encoding="utf-8")
        try:
            rp.apply_file_action(actions[0], root, dry_run=False)
        except ValueError:
            pass
        else:
            print("FAIL: drift was accepted")
            return 1
        try:
            test_atomic_write_modes_and_cleanup(root)
        except AssertionError as exc:
            print(f"FAIL: atomic write regression: {exc}", file=sys.stderr)
            return 1
    print("[test_materialize_runtime] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
