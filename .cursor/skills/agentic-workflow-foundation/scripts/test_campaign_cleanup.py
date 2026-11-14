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
TEMPLATE = HERE.parent / "templates" / "skills" / "campaign-cleanup" / "scripts" / "campaign-cleanup.sh.template"
PROJECT_ROOT = HERE.parents[3]
GENERATED_SCRIPT = PROJECT_ROOT / ".cursor" / "skills" / "campaign-cleanup" / "scripts" / "campaign-cleanup.sh"
LEGACY_GENERATED_SCRIPT = PROJECT_ROOT / ".cursor" / "skills" / "session-handover" / "scripts" / "campaign-cleanup.sh"


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


def touch_bytes(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_inventory_and_apply_protect_current_campaign() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        state(root, "S1", "C1")
        state(root, "S2", "C1")
        state(root, "S3", "C2")

        touch(
            root,
            ".cursor/.tracking/tracker-C1.md",
            "campaign_slug: TICKET-current\n"
            "report_path: docs/agent-tasks/reports/TICKET-report.md\n"
            ".cursor/.artifacts/TICKET-current--step1.md\n",
        )
        touch(root, ".cursor/.tracking/tracker-C2.md")
        touch(root, ".cursor/.artifacts/TICKET-current--step1.md", "campaign_slug: TICKET-current\n")
        touch(root, ".cursor/.artifacts/TICKET-current-extra--step1.md")
        touch(root, ".cursor/.artifacts/TICKET-other--step1.md")
        touch(
            root,
            ".cursor/.artifacts/TICKET-report--step1.md",
            "report_slug: TICKET-current\nreport_path: docs/agent-tasks/reports/TICKET-report.md\n",
        )
        touch(root, ".cursor/.artifacts/C1--step1.md", "campaign_slug: C1\n")
        touch(root, "docs/agent-tasks/reports/TICKET-report.md", "campaign_id: C1\n")
        touch(root, "docs/agent-tasks/reports/archives/TICKET-archive.md", "campaign_id: C1\n")
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
        assert ".cursor/.artifacts/TICKET-report--step1.md" in delete_section
        assert ".cursor/.artifacts/C1--step1.md" in delete_section

        applied = run(script, root, "apply", "--current-session-id", "S1")
        assert applied.returncode == 0, applied.stderr
        assert "deleted: 11" in applied.stdout, applied.stdout
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
            ".cursor/.artifacts/TICKET-report--step1.md",
            ".cursor/.artifacts/C1--step1.md",
            ".cursor/.session/S3.json",
            ".cursor/.session/S3.turns.jsonl",
            ".cursor/.session/handoff-S3.md",
            ".cursor/.session/handoff-consumed-S3-200.md",
            ".cursor/.session/compact-events.jsonl",
        ):
            assert not (root / relative).exists(), f"other runtime remains: {relative}"
        assert (root / "docs/agent-tasks/reports/TICKET-report.md").is_file()
        assert (root / "docs/agent-tasks/reports/archives/TICKET-archive.md").is_file()


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


def test_undetermined_artifact_is_retained_without_blocking_when_current_has_no_keys() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-ownership-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        state(root, "S1", "C1")
        artifact = touch(root, ".cursor/.artifacts/OTHER--step1.md")

        # current tracker 欠落: 全体停止せず、所属不明の artifact だけ保持する
        missing_tracker = run(script, root, "apply", "--current-session-id", "S1")
        assert missing_tracker.returncode == 0, missing_tracker.stderr
        assert artifact.is_file()
        assert "--- undetermined (retained) ---" in missing_tracker.stdout
        assert ".cursor/.artifacts/OTHER--step1.md" in missing_tracker.stdout.split(
            "--- undetermined (retained) ---", 1
        )[1]
        assert ".cursor/.artifacts/OTHER--step1.md" not in missing_tracker.stdout.split(
            "--- delete candidates ---", 1
        )[1].split("--- undetermined (retained) ---", 1)[0]

        # current tracker はあるが所有キーが 0 件: 同様に保持する
        touch(root, ".cursor/.tracking/tracker-C1.md", "report_path: docs/report.md\n")
        empty_keys = run(script, root, "inventory", "--current-session-id", "S1")
        assert empty_keys.returncode == 0, empty_keys.stderr
        assert "--- undetermined (retained) ---" in empty_keys.stdout
        assert artifact.is_file()


def test_other_tracker_claim_breaks_tracker_artifact_cycle() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-cycle-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        state(root, "S1", "C1")
        state(root, "S2", "C2")
        # current tracker には所有キーが無い（循環が起きていた状態）
        current_tracker = touch(root, ".cursor/.tracking/tracker-C1.md", "report_path: docs/report.md\n")
        other_tracker = touch(
            root,
            ".cursor/.tracking/tracker-C2.md",
            "campaign_slug: DONE-slug\n` .cursor/.artifacts/DONE-ref--step1.md `\n",
        )
        claimed_by_slug = touch(root, ".cursor/.artifacts/DONE-slug--step1.md")
        claimed_by_path = touch(root, ".cursor/.artifacts/DONE-ref--step2.md")
        orphan = touch(root, ".cursor/.artifacts/ORPHAN--step1.md")
        # slug は substring 照合しない
        near_miss = touch(root, ".cursor/.artifacts/DONE-slug-extra--step1.md")

        result = run(script, root, "apply", "--current-session-id", "S1")
        assert result.returncode == 0, result.stderr
        assert current_tracker.is_file()
        assert (root / ".cursor/.session/S1.json").is_file()
        assert not other_tracker.exists()
        assert not (root / ".cursor/.session/S2.json").exists()
        assert not claimed_by_slug.exists()
        assert not claimed_by_path.exists()
        assert orphan.is_file()
        assert near_miss.is_file()
        assert "deleted: 4" in result.stdout, result.stdout


def test_current_claim_wins_over_other_tracker_claim() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-collision-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        state(root, "S1", "C1")
        touch(root, ".cursor/.tracking/tracker-C1.md", "campaign_slug: SHARED\n")
        other_tracker = touch(root, ".cursor/.tracking/tracker-C2.md", "campaign_slug: SHARED\n")
        shared = touch(root, ".cursor/.artifacts/SHARED--step1.md")

        result = run(script, root, "apply", "--current-session-id", "S1")
        assert result.returncode == 0, result.stderr
        assert shared.is_file()
        assert not other_tracker.exists()


def test_unreadable_other_tracker_does_not_block_cleanup() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-other-unreadable-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        state(root, "S1", "C1")
        touch(root, ".cursor/.tracking/tracker-C1.md", "report_path: docs/report.md\n")
        other_tracker = touch_bytes(root, ".cursor/.tracking/tracker-C2.md", b"campaign_slug: \xff\n")
        artifact = touch(root, ".cursor/.artifacts/OTHER--step1.md")

        result = run(script, root, "apply", "--current-session-id", "S1")
        assert result.returncode == 0, result.stderr
        assert not other_tracker.exists()
        assert artifact.is_file()
        assert "--- undetermined (retained) ---" in result.stdout


def test_tracker_read_failure_and_broken_other_state_abort_without_deletion() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-read-failure-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        state(root, "S1", "C1")
        tracker = touch_bytes(root, ".cursor/.tracking/tracker-C1.md", b"campaign_slug: \xff\n")
        artifact = touch(root, ".cursor/.artifacts/OTHER--step1.md")

        unreadable = run(script, root, "apply", "--current-session-id", "S1")
        assert unreadable.returncode == 2
        assert tracker.is_file()
        assert artifact.is_file()

        tracker.write_text("campaign_slug: TICKET-current\n", encoding="utf-8")
        broken_state = touch_bytes(root, ".cursor/.session/S2.json", b"{\xff")
        blocked = run(script, root, "apply", "--current-session-id", "S1")
        assert blocked.returncode == 2
        assert broken_state.is_file()
        assert artifact.is_file()


def test_explicit_tracker_artifact_path_is_authoritative() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-cleanup-explicit-path-") as tmp:
        root = Path(tmp)
        script = write_script(root)
        state(root, "S1", "C1")
        touch(
            root,
            ".cursor/.tracking/tracker-C1.md",
            "` .cursor/.artifacts/EXPLICIT--step1.md `\n",
        )
        protected = touch(root, ".cursor/.artifacts/EXPLICIT--step1.md")
        extra = touch(root, ".cursor/.artifacts/EXPLICIT-extra--step1.md")

        result = run(script, root, "apply", "--current-session-id", "S1")
        assert result.returncode == 0, result.stderr
        assert protected.is_file()
        assert not extra.exists()


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


def test_generated_script_uses_skill_owned_path() -> None:
    assert GENERATED_SCRIPT.is_file(), f"generated script is missing: {GENERATED_SCRIPT}"
    assert not LEGACY_GENERATED_SCRIPT.exists(), f"legacy script remains: {LEGACY_GENERATED_SCRIPT}"


def main() -> int:
    tests = (
        test_inventory_and_apply_protect_current_campaign,
        test_current_state_and_path_safety_fail_closed,
        test_undetermined_artifact_is_retained_without_blocking_when_current_has_no_keys,
        test_other_tracker_claim_breaks_tracker_artifact_cycle,
        test_current_claim_wins_over_other_tracker_claim,
        test_unreadable_other_tracker_does_not_block_cleanup,
        test_tracker_read_failure_and_broken_other_state_abort_without_deletion,
        test_explicit_tracker_artifact_path_is_authoritative,
        test_tracked_file_is_rejected_before_delete,
        test_empty_runtime_directories_do_not_abort_under_set_u,
        test_invalid_arguments_and_allowlist_are_rejected,
        test_generated_script_uses_skill_owned_path,
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
