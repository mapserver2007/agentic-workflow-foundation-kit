#!/usr/bin/env python3
"""run_resolved_engine.py の readonly 回帰テスト。

検査対象:
  - audit / check の main() が _migrate_root_manifest_file を呼ばない
  - audit / check の main() が _cleanup_legacy_* を呼ばない
  - generate の main() が _migrate_root_manifest_file を呼ぶ
  - generate の main() が _cleanup_legacy_* を呼ぶ
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run_resolved_engine as engine  # noqa: E402


MIGRATION_FN = "run_resolved_engine._migrate_root_manifest_file"
CLEANUP_DOCS_FN = "run_resolved_engine._cleanup_legacy_workflow_docs"
CLEANUP_SKILL_FN = "run_resolved_engine._cleanup_legacy_skill_dir"
CLEANUP_TRIAGE_FN = "run_resolved_engine._cleanup_legacy_workflow_triage"
RUN_ENGINE_FN = "run_resolved_engine.run_engine"
RESOLVED_MANIFEST_FN = "run_resolved_engine.resolved_manifest"
PREPARE_SKILL_DIR_FN = "run_resolved_engine.prepare_skill_dir"

READONLY_COMMANDS = ("audit", "check")
WRITE_COMMANDS = ("generate",)


def _make_mock_manifest():
    return {"features": {"dual_thinking": {"enabled": False}}}


def _run_main_with_mocks(command: str):
    """main() を呼び出し、各関数の呼び出し有無を返す。"""
    mock_migrate = MagicMock(return_value=0)
    mock_cleanup_docs = MagicMock(return_value=0)
    mock_cleanup_skill = MagicMock(return_value=0)
    mock_cleanup_triage = MagicMock(return_value=0)
    mock_run_engine = MagicMock(return_value=0)
    mock_resolved = MagicMock(return_value=_make_mock_manifest())
    mock_prepare = MagicMock(return_value="/tmp/fake-resolved")

    with patch(MIGRATION_FN, mock_migrate), \
         patch(CLEANUP_DOCS_FN, mock_cleanup_docs), \
         patch(CLEANUP_SKILL_FN, mock_cleanup_skill), \
         patch(CLEANUP_TRIAGE_FN, mock_cleanup_triage), \
         patch(RUN_ENGINE_FN, mock_run_engine), \
         patch(RESOLVED_MANIFEST_FN, mock_resolved), \
         patch(PREPARE_SKILL_DIR_FN, mock_prepare), \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fake-tmpdir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        engine.main([command])

    return {
        "migrate": mock_migrate.called,
        "cleanup_docs": mock_cleanup_docs.called,
        "cleanup_skill": mock_cleanup_skill.called,
        "cleanup_triage": mock_cleanup_triage.called,
        "run_engine": mock_run_engine.called,
    }


def test_audit_does_not_call_migration():
    result = _run_main_with_mocks("audit")
    assert not result["migrate"], "audit must NOT call _migrate_root_manifest_file"


def test_audit_does_not_call_cleanup():
    result = _run_main_with_mocks("audit")
    assert not result["cleanup_docs"], "audit must NOT call _cleanup_legacy_workflow_docs"
    assert not result["cleanup_skill"], "audit must NOT call _cleanup_legacy_skill_dir"
    assert not result["cleanup_triage"], "audit must NOT call _cleanup_legacy_workflow_triage"


def test_check_does_not_call_migration():
    result = _run_main_with_mocks("check")
    assert not result["migrate"], "check must NOT call _migrate_root_manifest_file"


def test_check_does_not_call_cleanup():
    result = _run_main_with_mocks("check")
    assert not result["cleanup_docs"], "check must NOT call _cleanup_legacy_workflow_docs"
    assert not result["cleanup_skill"], "check must NOT call _cleanup_legacy_skill_dir"
    assert not result["cleanup_triage"], "check must NOT call _cleanup_legacy_workflow_triage"


def test_generate_calls_migration():
    result = _run_main_with_mocks("generate")
    assert result["migrate"], "generate MUST call _migrate_root_manifest_file"


def test_generate_calls_cleanup():
    result = _run_main_with_mocks("generate")
    assert result["cleanup_docs"], "generate MUST call _cleanup_legacy_workflow_docs"
    assert result["cleanup_skill"], "generate MUST call _cleanup_legacy_skill_dir"
    assert result["cleanup_triage"], "generate MUST call _cleanup_legacy_workflow_triage"


def main() -> int:
    tests = [
        test_audit_does_not_call_migration,
        test_audit_does_not_call_cleanup,
        test_check_does_not_call_migration,
        test_check_does_not_call_cleanup,
        test_generate_calls_migration,
        test_generate_calls_cleanup,
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

    print(f"[test_engine_readonly] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
