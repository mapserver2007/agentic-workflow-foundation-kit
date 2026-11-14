#!/usr/bin/env python3
"""run_resolved_engine.py の readonly 回帰テスト。

検査対象:
  - audit / check の main() がホスト updater を配置しない（書き込みは generate だけ）
  - generate の main() がホスト updater を配置する
  - fresh --work-root の generate / check が成立する
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run_resolved_engine as engine  # noqa: E402


RUN_ENGINE_FN = "run_resolved_engine.run_engine"
RESOLVED_MANIFEST_FN = "run_resolved_engine.resolved_manifest"
PREPARE_SKILL_DIR_FN = "run_resolved_engine.prepare_skill_dir"
INSTALL_UPDATE_SKILL_FN = "run_resolved_engine._install_update_skill"


def _make_mock_manifest():
    return {"features": {"deep_thinking": {"enabled": False}}}


def _run_main_with_mocks(command: str):
    """main() を呼び出し、各関数の呼び出し有無を返す。"""
    mock_run_engine = MagicMock(return_value=0)
    mock_resolved = MagicMock(return_value=_make_mock_manifest())
    mock_prepare = MagicMock(return_value="/tmp/fake-resolved")
    mock_install = MagicMock(return_value=0)

    with patch(RUN_ENGINE_FN, mock_run_engine), \
         patch(RESOLVED_MANIFEST_FN, mock_resolved), \
         patch(PREPARE_SKILL_DIR_FN, mock_prepare), \
         patch(INSTALL_UPDATE_SKILL_FN, mock_install), \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fake-tmpdir")
        mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
        engine.main([command])

    return {
        "install_update_skill": mock_install.called,
        "run_engine": mock_run_engine.called,
    }


def test_audit_does_not_install_update_skill():
    result = _run_main_with_mocks("audit")
    assert not result["install_update_skill"], "audit must NOT install the host update skill"


def test_check_does_not_install_update_skill():
    result = _run_main_with_mocks("check")
    assert not result["install_update_skill"], "check must NOT install the host update skill"


def test_generate_installs_update_skill():
    result = _run_main_with_mocks("generate")
    assert result["install_update_skill"], "generate MUST install the host update skill"


def _assert_fresh_work_root_supported(command: str) -> None:
    with tempfile.TemporaryDirectory(dir=engine.ROOT) as tmp:
        work_root = Path(tmp) / "fresh-work-root"
        with patch(RESOLVED_MANIFEST_FN, return_value=_make_mock_manifest()), \
             patch(PREPARE_SKILL_DIR_FN, side_effect=lambda path, manifest: path), \
             patch(RUN_ENGINE_FN, return_value=0):
            rc = engine.main([command, "--work-root", str(work_root)])
        assert rc == 0, f"{command} must support a fresh --work-root"
        assert (work_root / ".cursor" / "skills").is_dir(), (
            f"{command} must create the TemporaryDirectory parent"
        )


def test_generate_supports_fresh_work_root():
    _assert_fresh_work_root_supported("generate")


def test_check_supports_fresh_work_root():
    _assert_fresh_work_root_supported("check")


def test_foundation_runner_preserves_exit_2() -> None:
    import run_all_foundation_tests as runner

    assert runner.propagate_exit(0) == 0
    assert runner.propagate_exit(2) == 2
    assert runner.propagate_exit(1) == 1


def main() -> int:
    tests = [
        test_audit_does_not_install_update_skill,
        test_check_does_not_install_update_skill,
        test_generate_installs_update_skill,
        test_generate_supports_fresh_work_root,
        test_check_supports_fresh_work_root,
        test_foundation_runner_preserves_exit_2,
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
