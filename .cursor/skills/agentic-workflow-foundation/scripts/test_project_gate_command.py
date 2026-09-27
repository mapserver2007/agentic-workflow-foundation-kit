#!/usr/bin/env python3
"""_validate_project_gate_command の検証テスト。"""
from __future__ import annotations

import os
import sys
import tempfile

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


def expect_report_contract_ok(manifest, label):
    try:
        engine._validate_report_id_contract(manifest)
        ok(label)
    except SystemExit as e:
        fail(label, f"unexpected exit {e.code}")


def expect_report_contract_exit2(manifest, label):
    try:
        engine._validate_report_id_contract(manifest)
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


# --- report ID contract ---
REPORT_ID_CONTRACT = {
    "agent_workflow": {
        "enabled": True,
        "report_slug_format": "{ticket}-{slug}",
        "ticket": {"format": r"TICKET-[0-9]+", "example": "TICKET-123"},
    },
}
expect_report_contract_ok(REPORT_ID_CONTRACT, "valid report ID contract")
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "{ticket}-{slug}", "ticket": {"example": "TICKET-123"}}},
    "ticket.format missing",
)
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "{ticket}-{slug}", "ticket": {"format": None, "example": "TICKET-123"}}},
    "ticket.format null",
)
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "{ticket}-{slug}", "ticket": {"format": "", "example": "TICKET-123"}}},
    "ticket.format empty",
)
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "{ticket}-{slug}", "ticket": {"format": "   ", "example": "TICKET-123"}}},
    "ticket.format whitespace",
)
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "{ticket}-{slug}", "ticket": {"format": "[", "example": "TICKET-123"}}},
    "ticket.format invalid regex",
)
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "{ticket}-{slug}", "ticket": {"format": r"TICKET-[0-9]+"}}},
    "ticket.example missing",
)
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "{ticket}-{slug}", "ticket": {"format": r"TICKET-[0-9]+", "example": "OPS-123"}}},
    "ticket.example mismatch",
)
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "{ticket}-{slug}", "ticket": {"format": r".+", "example": "TICKET-123"}}},
    "ticket.format consumes slug",
)
expect_report_contract_exit2(
    {"agent_workflow": {"report_slug_format": "TICKET-{number}-{slug}", "ticket": {"format": r"TICKET-[0-9]+", "example": "TICKET-123"}}},
    "invalid report slug format",
)
expect_report_contract_exit2(
    {"agent_workflow": {"enabled": False, "report_slug_format": "{ticket}-{slug}", "ticket": {"format": "", "example": "TICKET-123"}}},
    "disabled agent_workflow remains strict",
)

with tempfile.TemporaryDirectory(prefix="report-id-overlay-") as temp_dir:
    root_manifest = os.path.join(temp_dir, "manifest.yaml")
    original_inject = engine._inject_approved_tech_contract
    engine._inject_approved_tech_contract = lambda manifest, _path: manifest
    with open(root_manifest, "w", encoding="utf-8") as f:
        f.write(
            "agent_workflow:\n"
            '  report_slug_format: "TICKET-{number}-{slug}"\n'
            "  ticket:\n"
            '    format: "[0-9]+"\n'
        )
    try:
        engine.resolved_manifest(
            os.path.join(engine.SKILL_DIR, "manifest.yaml"), root_manifest,
        )
        fail("legacy root overlay rejected", "expected exit 2 but no exit")
    except SystemExit as e:
        ok("legacy root overlay rejected") if e.code == 2 else fail(
            "legacy root overlay rejected", f"unexpected exit {e.code}",
        )
    with open(root_manifest, "w", encoding="utf-8") as f:
        f.write(
            "agent_workflow:\n"
            '  report_slug_format: "{ticket}-{slug}"\n'
            "  ticket:\n"
            '    format: "TICKET-[0-9]+"\n'
            '    example: "TICKET-123"\n'
        )
    try:
        engine.resolved_manifest(
            os.path.join(engine.SKILL_DIR, "manifest.yaml"), root_manifest,
        )
        ok("updated root overlay accepted")
    except SystemExit as e:
        fail("updated root overlay accepted", f"unexpected exit {e.code}")
    finally:
        engine._inject_approved_tech_contract = original_inject

print(f"\n[test_project_gate_command] {passed}/{passed + failed} passed")
sys.exit(0 if failed == 0 else 1)
