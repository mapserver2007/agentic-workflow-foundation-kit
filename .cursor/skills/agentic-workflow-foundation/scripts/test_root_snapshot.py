#!/usr/bin/env python3
"""root/seed manifest と tracked paths の不変性スナップショット。"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SKILL_MANIFEST = HERE.parent / "manifest.yaml"

TRACKED_PATHS = (
    ROOT / "manifest.yaml",
    SKILL_MANIFEST,
    ROOT / "docs" / "agent-tasks" / "reports" / "llm-tech-contract-provisioning.md",
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


def snapshot() -> dict[str, str]:
    return {str(p): file_sha256(p) for p in TRACKED_PATHS}


def assert_unchanged(before: dict[str, str], after: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for key, digest in before.items():
        if after.get(key) != digest:
            failures.append(f"{key}: {digest} -> {after.get(key)}")
    return failures


def git_tracked_diff() -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--", *(str(p.relative_to(ROOT)) for p in TRACKED_PATHS if p.is_file())],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except OSError:
        return ""
