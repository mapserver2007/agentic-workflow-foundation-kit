#!/usr/bin/env python3
"""_validate_project_gate_command の検証テスト。"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run_resolved_engine as engine  # noqa: E402

passed = 0
failed = 0


def ok(label):
    global passed
    passed += 1
    print(f"  PASS: {label}")


def fail(label, reason=""):
    global failed
    failed += 1
    print(f"  FAIL: {label} — {reason}")


def expect_no_error(manifest, label):
    try:
        engine._validate_project_gate_command(manifest)
        ok(label)
    except SystemExit as e:
        fail(label, f"unexpected exit {e.code}")


def expect_exit2(manifest, label):
    try:
        engine._validate_project_gate_command(manifest)
        fail(label, "expected exit 2 but no exit")
    except SystemExit as e:
        if e.code == 2:
            ok(label)
        else:
            fail(label, f"expected exit 2 but got exit {e.code}")


# --- valid cases ---
expect_no_error({}, "no agent_workflow key")
expect_no_error({"agent_workflow": {}}, "no step6 key")
expect_no_error({"agent_workflow": {"step6": {}}}, "no project_gate_command key")
expect_no_error({"agent_workflow": {"step6": {"project_gate_command": None}}}, "null value")
expect_no_error(
    {"agent_workflow": {"step6": {"project_gate_command": ["python3", "gate.py"]}}},
    "valid 2-element command",
)
expect_no_error(
    {"agent_workflow": {"step6": {"project_gate_command": ["./bin/check"]}}},
    "valid single-element command",
)

# --- invalid cases ---
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": []}}},
    "empty list",
)
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": "python3"}}},
    "string instead of list",
)
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": [123]}}},
    "non-string element",
)
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": [""]}}},
    "empty string element",
)
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": ["cmd\narg"]}}},
    "newline in element",
)
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": ['cmd"arg']}}},
    "double quote in element",
)
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": ["cmd\\arg"]}}},
    "backslash in element",
)
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": ["$HOME/cmd"]}}},
    "dollar sign in element",
)
expect_exit2(
    {"agent_workflow": {"step6": {"project_gate_command": ["`cmd`"]}}},
    "backtick in element",
)

print(f"\n[test_project_gate_command] {passed}/{passed + failed} passed")
sys.exit(0 if failed == 0 else 1)
