#!/usr/bin/env python3
"""project_ignore_dirs: writes / marker からのドットディレクトリ投影を検証。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract_projection as cp  # noqa: E402


def _contract_with_writes(*actions_writes: list[str], markers: list[str] | None = None) -> dict:
    actions: list[dict] = []
    for writes in actions_writes:
        action: dict = {"argv": ["true"], "writes": list(writes), "effects": ["host_write"]}
        if markers:
            action["postconditions"] = [
                {"kind": "record-state-digest", "marker": m, "paths": ["x"]}
                for m in markers
            ]
        actions.append(action)
    return {"provisioning": {"policy": "explicit", "command_actions": actions}}


def test_state_writes_project_to_state_dir() -> None:
    contract = _contract_with_writes(
        [".state/toolchain-state.json", ".state/provision-state.json", "pnpm-lock.yaml"]
    )
    assert cp.project_ignore_dirs(contract) == [".state/"]


def test_empty_writes_yield_empty() -> None:
    contract = {"provisioning": {"policy": "none", "command_actions": []}}
    assert cp.project_ignore_dirs(contract) == []


def test_lockfile_only_yield_empty() -> None:
    contract = _contract_with_writes(["pnpm-lock.yaml", "package.json"])
    assert cp.project_ignore_dirs(contract) == []


def test_pnpm_store_path_projects() -> None:
    contract = _contract_with_writes([".pnpm-store/v3/files"])
    assert cp.project_ignore_dirs(contract) == [".pnpm-store/"]


def test_trailing_slash_dir_projects() -> None:
    contract = _contract_with_writes([".pnpm-store/"])
    assert cp.project_ignore_dirs(contract) == [".pnpm-store/"]


def test_root_dotfile_not_projected() -> None:
    contract = _contract_with_writes([".env", ".gitignore"])
    assert cp.project_ignore_dirs(contract) == []


def test_marker_only_projects() -> None:
    contract = {
        "provisioning": {
            "command_actions": [
                {
                    "argv": ["true"],
                    "writes": [],
                    "effects": ["host_write"],
                    "postconditions": [
                        {
                            "kind": "capture-toolchain-version",
                            "marker": ".state/toolchain-state.json",
                            "pointer": "pnpm.version",
                            "pattern": ".*",
                            "argv": ["pnpm", "--version"],
                        }
                    ],
                }
            ]
        }
    }
    assert cp.project_ignore_dirs(contract) == [".state/"]


def test_unsafe_paths_not_projected() -> None:
    contract = _contract_with_writes(
        ["/tmp/.state/value", "../.state/value", ".state/../value"]
    )
    assert cp.project_ignore_dirs(contract) == []


def test_dedupe_and_sort() -> None:
    contract = _contract_with_writes(
        [".z-cache/a", ".state/a"],
        [".state/b", ".a-store/x"],
    )
    assert cp.project_ignore_dirs(contract) == [".a-store/", ".state/", ".z-cache/"]


def main() -> int:
    tests = [
        test_state_writes_project_to_state_dir,
        test_empty_writes_yield_empty,
        test_lockfile_only_yield_empty,
        test_pnpm_store_path_projects,
        test_trailing_slash_dir_projects,
        test_root_dotfile_not_projected,
        test_marker_only_projects,
        test_unsafe_paths_not_projected,
        test_dedupe_and_sort,
    ]
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            print(f"FAIL: {fn.__name__}: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: {fn.__name__}: {exc}", file=sys.stderr)
            return 1
    print("[test_project_ignore_dirs] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
