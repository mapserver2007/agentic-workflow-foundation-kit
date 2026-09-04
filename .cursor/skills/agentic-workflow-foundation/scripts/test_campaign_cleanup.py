#!/usr/bin/env python3
"""campaign-cleanup.sh の current campaign 保護と削除境界を検査する。"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "templates" / "skills" / "session-handover" / "scripts" / "campaign-cleanup.sh.template"


def write_script(root: Path) -> Path:
    script = root / "campaign-cleanup.sh"
    script.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def run(script: Path, root: Path, *args: str, extra_env: dict[str, str] | None = None):
    env = dict(os.environ)
    env["CURSOR_PROJECT_DIR"] = str(root)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["/bin/bash", str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def state(root: Path, session_id: str, campaign_id: str) -> None:
    path = root / ".cursor" / ".session" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"session_id": session_id, "campaign_id": campaign_id}),
        encoding="utf-8",
    )


def touch(root: Path, relative: str, content: str = "runtime\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_inventory_and_apply_protect_current_campaign() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        state(root, "S1", "C1")
        state(root, "S2", "C1")
        state(root, "S3", "C2")

        touch(root, ".cursor/.tracking/tracker-C1.md", "report_path: docs/agent-tasks/reports/TICKET-current.md\n")
        touch(root, ".cursor/.tracking/tracker-C2.md")
        touch(root, ".cursor/.artifacts/TICKET-current--step1.md", "campaign_slug: TICKET-current\n")
        touch(root, ".cursor/.artifacts/TICKET-current-extra--step1.md")
        touch(root, ".cursor/.artifacts/TICKET-other--step1.md")
        touch(root, ".cursor/.session/S1.turns.jsonl")
        touch(root, ".cursor/.session/S1.progress.jsonl")
        touch(root, ".cursor/.session/S1.lock")
        touch(root, ".cursor/.session/S2.turns.jsonl")
        touch(root, ".cursor/.session/S2.lock")
        touch(root, ".cursor/.session/S3.turns.jsonl")
        touch(root, ".cursor/.session/S3.lock")
        touch(root, ".cursor/.session/handoff-S2.md")
        touch(root, ".cursor/.session/handoff-S3.md")
        touch(root, ".cursor/.session/handoff-consumed-S1-100.md")
        touch(root, ".cursor/.session/handoff-consumed-S3-200.md")
        touch(root, ".cursor/.session/compact-events.jsonl")

        script = write_script(root)
        inventory = run(script, root, "inventory", "--current-session-id", "S1")
        assert inventory.returncode == 0, inventory.stderr
        assert "current-campaign-id: C1" in inventory.stdout
        assert ".cursor/.tracking/tracker-C1.md" in inventory.stdout.split("--- delete candidates ---")[0]
        assert ".cursor/.session/S2.lock" in inventory.stdout.split("--- delete candidates ---")[0]
        assert ".cursor/.session/handoff-consumed-S1-100.md" in inventory.stdout.split(
            "--- delete candidates ---"
        )[0]
        delete_section = inventory.stdout.split("--- delete candidates ---", 1)[1]
        assert ".cursor/.tracking/tracker-C2.md" in delete_section
        assert ".cursor/.session/S3.turns.jsonl" in delete_section
        assert ".cursor/.session/handoff-S3.md" in delete_section
        assert ".cursor/.session/compact-events.jsonl" in delete_section
        assert ".cursor/.artifacts/TICKET-current-extra--step1.md" in delete_section
        assert ".cursor/.artifacts/TICKET-other--step1.md" in delete_section

        applied = run(script, root, "apply", "--current-session-id", "S1")
        assert applied.returncode == 0, applied.stderr
        assert "deleted: 9" in applied.stdout, applied.stdout
        for relative in (
            ".cursor/.tracking/tracker-C1.md",
            ".cursor/.artifacts/TICKET-current--step1.md",
            ".cursor/.session/S1.json",
            ".cursor/.session/S2.json",
            ".cursor/.session/S1.turns.jsonl",
            ".cursor/.session/S2.lock",
            ".cursor/.session/handoff-S2.md",
            ".cursor/.session/handoff-consumed-S1-100.md",
        ):
            assert (root / relative).is_file(), f"current campaign runtime was deleted: {relative}"
        for relative in (
            ".cursor/.tracking/tracker-C2.md",
            ".cursor/.artifacts/TICKET-current-extra--step1.md",
            ".cursor/.artifacts/TICKET-other--step1.md",
            ".cursor/.session/S3.json",
            ".cursor/.session/S3.turns.jsonl",
            ".cursor/.session/handoff-S3.md",
            ".cursor/.session/handoff-consumed-S3-200.md",
            ".cursor/.session/compact-events.jsonl",
        ):
            assert not (root / relative).exists(), f"other runtime remains: {relative}"


def test_current_state_and_path_safety_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-safety-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        touch(root, ".cursor/.tracking/tracker-OLD.md")

        missing = run(script, root, "inventory", "--current-session-id", "MISSING")
        assert missing.returncode == 1
        assert (root / ".cursor/.tracking/tracker-OLD.md").is_file()

        state(root, "S1", "C1")
        outside = touch(root, "outside.txt", "keep\n")
        link = root / ".cursor" / ".tracking" / "tracker-C2.md"
        link.symlink_to(outside)
        symlink_result = run(script, root, "apply", "--current-session-id", "S1")
        assert symlink_result.returncode == 2
        assert outside.is_file()
        assert link.is_symlink()


def test_tracked_file_is_rejected_before_delete() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-tracked-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        state(root, "S1", "C1")
        candidate = touch(root, ".cursor/.tracking/tracker-C2.md")
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/usr/bin/env bash\n"
            'case "$*" in\n'
            '  *"rev-parse --show-toplevel"*) exit 0 ;;\n'
            '  *"ls-files"*) exit 0 ;;\n'
            "esac\n"
            "exit 1\n",
            encoding="utf-8",
        )
        fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)
        result = run(
            script,
            root,
            "apply",
            "--current-session-id",
            "S1",
            extra_env={"PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"},
        )
        assert result.returncode == 2
        assert candidate.is_file()


def test_empty_runtime_directories_do_not_abort_under_set_u() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-empty-dirs-") as tmp:
        root = Path(tmp)
        state(root, "S1", "C1")
        (root / ".cursor" / ".artifacts").mkdir(parents=True)
        (root / ".cursor" / ".tracking").mkdir(parents=True)
        script = write_script(root)
        inventory = run(script, root, "inventory", "--current-session-id", "S1")
        assert inventory.returncode == 0, inventory.stderr
        assert "current-campaign-id: C1" in inventory.stdout
        applied = run(script, root, "apply", "--current-session-id", "S1")
        assert applied.returncode == 0, applied.stderr
        assert "deleted: 0" in applied.stdout
        assert (root / ".cursor" / ".session" / "S1.json").is_file()


def test_invalid_arguments_and_allowlist_are_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-arguments-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        invalid_sid = run(script, root, "inventory", "--current-session-id", "../S1")
        assert invalid_sid.returncode == 2

        state(root, "S1", "C1")
        unknown = touch(root, ".cursor/.session/not-allowlisted.tmp")
        result = run(script, root, "inventory", "--current-session-id", "S1")
        assert result.returncode == 2
        assert unknown.is_file()


def main() -> int:
    tests = (
        test_inventory_and_apply_protect_current_campaign,
        test_current_state_and_path_safety_fail_closed,
        test_tracked_file_is_rejected_before_delete,
        test_empty_runtime_directories_do_not_abort_under_set_u,
        test_invalid_arguments_and_allowlist_are_rejected,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            print(f"[test_campaign_cleanup] FAIL: {test.__name__}: {exc}")
            return 1
    print(f"[test_campaign_cleanup] PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
