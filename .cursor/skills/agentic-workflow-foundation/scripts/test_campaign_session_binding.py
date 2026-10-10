#!/usr/bin/env python3
"""campaign_id / session_id の mint・bind と tracker lookup を検査する。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
TEMPLATE_DIR = SKILL_DIR / "templates"
BASH_EXECUTABLE = "/bin/bash"

BOOTSTRAP_TEMPLATE = TEMPLATE_DIR / "hooks" / "session-bootstrap.sh.template"
BYTE_HELPER_TEMPLATE = TEMPLATE_DIR / "hooks" / "session-byte-count.sh.template"
EVALUATOR_TEMPLATE = TEMPLATE_DIR / "hooks" / "session-budget-evaluator.sh.template"
OBSERVER_TEMPLATE = TEMPLATE_DIR / "hooks" / "session-compact-observer.sh.template"
START_GATE_TEMPLATE = (
    TEMPLATE_DIR / "skills" / "session-handover" / "scripts" / "session-start-gate.sh.template"
)
PLAN_GATE_TEMPLATE = (
    TEMPLATE_DIR / "skills" / "session-handover" / "scripts" / "plan-gate.sh.template"
)
ORCHESTRATOR_TEMPLATE = TEMPLATE_DIR / "skills" / "workflow-orchestrator" / "SKILL.md.template"
MANIFEST = SKILL_DIR / "manifest.yaml"

RENDER_VALUES = {
    "{{framework.budget_thresholds.max_injection_bytes}}": "8192",
    "{{framework.budget_thresholds.max_snapshot_bytes}}": "8192",
    "{{framework.budget_thresholds.checkpoint_interval_prompts}}": "15",
    "{{framework.budget_thresholds.yellow.prompt_count}}": "35",
    "{{framework.budget_thresholds.yellow.shell_bytes}}": "768000",
    "{{framework.budget_thresholds.red.prompt_count}}": "70",
    "{{framework.budget_thresholds.red.shell_bytes}}": "4194304",
    "{{framework.budget_thresholds.compact_yellow_percent}}": "60",
    "{{framework.budget_thresholds.compact_red_percent}}": "78",
    "{{framework.budget_thresholds.compact_freshness_sec}}": "300",
    "{{framework.budget_thresholds.compact_thrashing_count}}": "3",
    "{{project.tracking_artifact}}": ".cursor/.tracking/tracker-{campaign_id}.md",
}


def render_template(template: Path) -> str:
    text = template.read_text(encoding="utf-8")
    text = re.sub(
        r"\{\{#each framework\.handoff\.recovery_constraints\}\}.*?\{\{/each\}\}",
        "- recovery constraint",
        text,
        flags=re.DOTALL,
    )
    for source, value in RENDER_VALUES.items():
        text = text.replace(source, value)
    if re.search(r"\{\{.*?\}\}", text, flags=re.DOTALL):
        raise AssertionError(f"unresolved template marker in {template}")
    return text


def write_script(template: Path, root: Path, name: str) -> Path:
    helper = root / "session-byte-count.sh"
    if not helper.exists():
        helper.write_text(render_template(BYTE_HELPER_TEMPLATE), encoding="utf-8")
        helper.chmod(0o700)
    script = root / name
    script.write_text(render_template(template), encoding="utf-8")
    script.chmod(0o700)
    return script


def run_hook(script: Path, root: Path, session_id: str, payload: dict) -> dict:
    env = dict(os.environ)
    env.update({
        "CURSOR_PROJECT_DIR": str(root),
        "CTX_BUDGET_SESSION_ID": session_id,
    })
    result = subprocess.run(  # noqa: S603 - controlled fixture script and environment
        [BASH_EXECUTABLE, str(script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"{script.name} failed for {session_id}: {result.returncode}: "
            f"{result.stdout} {result.stderr}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{script.name} returned invalid JSON: {result.stdout!r}") from exc


def read_state(root: Path, session_id: str) -> dict:
    return json.loads(
        (root / ".cursor" / ".session" / f"{session_id}.json").read_text(encoding="utf-8")
    )


def write_state(root: Path, session_id: str, **updates: object) -> None:
    path = root / ".cursor" / ".session" / f"{session_id}.json"
    state = read_state(root, session_id)
    state.update(updates)
    path.write_text(json.dumps(state), encoding="utf-8")


def test_runtime_mint_bind_and_tracker_lookup() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-session-binding-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        tracking_dir = root / ".cursor" / ".tracking"
        session_dir.mkdir(parents=True)
        tracking_dir.mkdir(parents=True)

        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        evaluator = write_script(EVALUATOR_TEMPLATE, root, "session-budget-evaluator.sh")
        observer = write_script(OBSERVER_TEMPLATE, root, "session-compact-observer.sh")

        run_hook(bootstrap, root, "S1", {"session_id": "S1"})
        assert read_state(root, "S1")["campaign_id"] == "S1", "創設 session は campaign_id を mint する"
        assert read_state(root, "S1")["campaign_id_source"] == "session_start"
        assert not (tracking_dir / "tracker-S1.md").exists(), "bootstrap は tracker を作成しない"

        write_state(root, "S1", prompt_count=70)
        evaluator_output = run_hook(evaluator, root, "S1", {})
        assert "followup_message" in evaluator_output, "Red followup が発火しない"
        followup = evaluator_output["followup_message"]
        assert "`campaign_id: S1`" in followup, "followup の campaign_id がコマンド置換で失われた"
        expected_tracker_path = str(tracking_dir / "tracker-S1.md")
        assert f"`tracker_path: {expected_tracker_path}`" in followup, "followup の tracker_path が不正"
        handoff_s1 = session_dir / "handoff-S1.md"
        assert handoff_s1.is_file(), "Red が handoff manifest を作成しない"
        handoff_text = handoff_s1.read_text(encoding="utf-8")
        assert "campaign_id: S1" in handoff_text, "handoff に campaign_id が転記されない"
        assert "tracker_path:" in handoff_text, "handoff に tracker_path が転記されない"

        (tracking_dir / "tracker-S1.md").write_text(
            "# campaign S1\n## 完了チェック\n- [ ] keep\n",
            encoding="utf-8",
        )
        run_hook(bootstrap, root, "S2", {"session_id": "S2"})
        state_s2 = read_state(root, "S2")
        assert state_s2["campaign_id"] == "S1", "Red 後の S2 が創設 campaign に bind しない"
        assert state_s2["campaign_id_source"] == "handoff"
        assert (tracking_dir / "tracker-S1.md").is_file(), "S2 が tracker-S1 を失う"
        assert not (tracking_dir / "tracker-S2.md").exists(), "S2 用 tracker が誤作成された"
        assert list(session_dir.glob("handoff-consumed-S1-*.md")), "handoff が consume されない"

        observer_output = run_hook(
            observer,
            root,
            "S2",
            {
                "context_usage_percent": 80,
                "context_tokens": 160000,
                "context_window_size": 200000,
                "trigger": "auto",
            },
        )
        assert "user_message" in observer_output, "compact observer の通知がない"
        snapshot = session_dir / "pre-compact-S2.md"
        assert snapshot.is_file(), "S2 snapshot が作成されない"
        assert "tracker-S1.md" in snapshot.read_text(encoding="utf-8"), "snapshot が campaign tracker を参照しない"
        assert not (tracking_dir / "tracker-S2.md").exists(), "observer が SESSION_ID tracker を作成した"


def test_multi_handoff_select_binds_campaign() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-session-multi-handoff-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        tracking_dir = root / ".cursor" / ".tracking"
        session_dir.mkdir(parents=True)
        tracking_dir.mkdir(parents=True)
        (session_dir / "handoff-A.md").write_text(
            "campaign_id: C1\n\n## ポインタ\ntracker-C1.md\n",
            encoding="utf-8",
        )
        (session_dir / "handoff-B.md").write_text(
            "campaign_id: C2\n\n## ポインタ\ntracker-C2.md\n",
            encoding="utf-8",
        )
        (tracking_dir / "tracker-C1.md").write_text("# campaign C1\n", encoding="utf-8")

        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        observer = write_script(OBSERVER_TEMPLATE, root, "session-compact-observer.sh")

        output = run_hook(bootstrap, root, "S5", {"session_id": "S5"})
        state_before = read_state(root, "S5")
        assert state_before["campaign_id"] == "S5", "2+ 選択前に自動 bind した"
        assert state_before["campaign_id_source"] == "session_start"
        context = output.get("additional_context", "")
        assert "[CONTEXT_BUDGET_HANDOFF_SELECT]" in context
        assert "campaign_id_source" in context
        assert ".campaign_id = $cid" in context
        assert (session_dir / "handoff-A.md").is_file()
        assert (session_dir / "handoff-B.md").is_file()

        write_state(root, "S5", campaign_id="C1", campaign_id_source="handoff")
        consumed = session_dir / "handoff-consumed-A-1.md"
        (session_dir / "handoff-A.md").rename(consumed)

        run_hook(
            observer,
            root,
            "S5",
            {"context_usage_percent": 80, "trigger": "auto"},
        )
        snapshot = (session_dir / "pre-compact-S5.md").read_text(encoding="utf-8")
        assert "tracker-C1.md" in snapshot, "選択後 bind した campaign tracker を参照しない"
        assert not (tracking_dir / "tracker-S5.md").exists(), "選択後も創設 session の tracker を誤作成した"
        assert (tracking_dir / "tracker-C1.md").is_file()
        assert not (tracking_dir / "tracker-C2.md").exists()


def test_no_handoff_mints_and_does_not_guess_existing_tracker() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-session-no-handoff-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        tracking_dir = root / ".cursor" / ".tracking"
        session_dir.mkdir(parents=True)
        tracking_dir.mkdir(parents=True)
        (tracking_dir / "tracker-OLD.md").write_text("old", encoding="utf-8")
        (tracking_dir / "tracker-OTHER.md").write_text("other", encoding="utf-8")

        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        observer = write_script(OBSERVER_TEMPLATE, root, "session-compact-observer.sh")

        run_hook(bootstrap, root, "S3", {"session_id": "S3"})
        state_s3 = read_state(root, "S3")
        assert state_s3["campaign_id"] == "S3", "handoff 無しで新 campaign を mint しない"
        assert state_s3["campaign_id_source"] == "session_start"

        legacy_handoff = session_dir / "handoff-legacy.md"
        legacy_handoff.write_text(
            "# Handoff Manifest\n\n## ポインタ\ntracker-OLD.md\n",
            encoding="utf-8",
        )
        run_hook(bootstrap, root, "S4", {"session_id": "S4"})
        state_s4 = read_state(root, "S4")
        assert state_s4["campaign_id"] == "S4", "campaign_id のない handoff を推測 bind した"
        assert state_s4["campaign_id_source"] == "session_start"

        run_hook(
            observer,
            root,
            "S4",
            {"context_usage_percent": 80, "trigger": "manual"},
        )
        assert (tracking_dir / "tracker-S4.md").is_file(), "observer が新 campaign の tracker を作成しない"
        assert (tracking_dir / "tracker-OLD.md").is_file()
        assert (tracking_dir / "tracker-OTHER.md").is_file()


def test_handoff_reconciliation_uses_matching_origin() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-session-origin-snapshot-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        (session_dir / "handoff-sess-a.md").write_text(
            "campaign_id: C-A\n\n## 直近のユーザー依頼\nresume\n",
            encoding="utf-8",
        )
        matching_snapshot = session_dir / "pre-compact-sess-a.md"
        matching_snapshot.write_text(
            "# MATCHING_SNAPSHOT_BODY\n- [x] complete\n",
            encoding="utf-8",
        )
        other_snapshot = session_dir / "pre-compact-sess-b.md"
        other_snapshot.write_text(
            "# OTHER_SNAPSHOT_BODY\n- [ ] incomplete\n",
            encoding="utf-8",
        )
        os.utime(matching_snapshot, (1, 1))
        os.utime(other_snapshot, (2, 2))

        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        output = run_hook(bootstrap, root, "NEW", {"session_id": "NEW"})
        context = output.get("additional_context", "")

        assert "[CONTEXT_BUDGET_HANDOFF]" in context
        assert "警告（スナップショット突合）" not in context, "別 session の最新 snapshot を突合した"
        assert "MATCHING_SNAPSHOT_BODY" not in context, "一致 snapshot 本文を追加注入した"
        assert "OTHER_SNAPSHOT_BODY" not in context, "別 session の snapshot 本文を混入した"


def test_handoff_pointer_warning_uses_raw_manifest() -> None:
    cases = (
        ("without-pointer-incomplete", "## 直近のユーザー依頼\nresume\n", "- [ ] pending\n", True),
        ("with-pointer-incomplete", "## ポインタ\ntracker-C.md\n", "- [ ] pending\n", False),
        ("without-pointer-complete", "## 直近のユーザー依頼\nresume\n", "- [x] done\n", False),
    )
    for label, handoff_body, snapshot_body, expect_warning in cases:
        with tempfile.TemporaryDirectory(prefix=f"campaign-session-pointer-{label}-") as tmp:
            root = Path(tmp)
            session_dir = root / ".cursor" / ".session"
            session_dir.mkdir(parents=True)
            (session_dir / "handoff-origin.md").write_text(
                f"campaign_id: C\n\n{handoff_body}",
                encoding="utf-8",
            )
            (session_dir / "pre-compact-origin.md").write_text(
                f"# snapshot\n{snapshot_body}",
                encoding="utf-8",
            )

            bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
            output = run_hook(bootstrap, root, f"NEW-{label}", {"session_id": f"NEW-{label}"})
            context = output.get("additional_context", "")
            has_warning = "警告（スナップショット突合）" in context
            assert has_warning == expect_warning, f"{label}: 突合 WARN の判定が不正"


def test_handoff_presence_blocks_snapshot_fallback() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-session-handoff-no-match-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        (session_dir / "handoff-origin.md").write_text(
            "campaign_id: C\n\n## ポインタ\ntracker-C.md\n",
            encoding="utf-8",
        )
        (session_dir / "pre-compact-other.md").write_text("OTHER_BODY", encoding="utf-8")

        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        output = run_hook(bootstrap, root, "NEW-NO-MATCH", {"session_id": "NEW-NO-MATCH"})
        context = output.get("additional_context", "")
        assert "[CONTEXT_BUDGET_HANDOFF]" in context
        assert "[CONTEXT_BUDGET_SNAPSHOT_FALLBACK]" not in context
        assert "OTHER_BODY" not in context

    with tempfile.TemporaryDirectory(prefix="campaign-session-empty-handoff-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        empty_handoff = session_dir / "handoff-empty.md"
        empty_handoff.write_text("", encoding="utf-8")
        (session_dir / "pre-compact-other.md").write_text("OTHER_BODY", encoding="utf-8")

        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        output = run_hook(bootstrap, root, "NEW-EMPTY", {"session_id": "NEW-EMPTY"})
        assert "additional_context" not in output, "空 handoff から snapshot fallback した"
        assert empty_handoff.is_file(), "注入できなかった handoff を consume した"

    with tempfile.TemporaryDirectory(prefix="campaign-session-multi-handoff-snapshot-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        (session_dir / "handoff-A.md").write_text("campaign_id: A\n", encoding="utf-8")
        (session_dir / "handoff-B.md").write_text("campaign_id: B\n", encoding="utf-8")
        (session_dir / "pre-compact-A.md").write_text("SNAPSHOT_BODY", encoding="utf-8")

        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        output = run_hook(bootstrap, root, "NEW-MULTI", {"session_id": "NEW-MULTI"})
        context = output.get("additional_context", "")
        assert "[CONTEXT_BUDGET_HANDOFF_SELECT]" in context
        assert "[CONTEXT_BUDGET_SNAPSHOT_SELECT]" not in context
        assert "SNAPSHOT_BODY" not in context


def test_no_handoff_snapshot_matrix() -> None:
    with tempfile.TemporaryDirectory(prefix="campaign-session-no-snapshot-") as tmp:
        root = Path(tmp)
        (root / ".cursor" / ".session").mkdir(parents=True)
        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        output = run_hook(bootstrap, root, "NEW-ZERO", {"session_id": "NEW-ZERO"})
        assert "additional_context" not in output
        assert read_state(root, "NEW-ZERO")["campaign_id"] == "NEW-ZERO"

    with tempfile.TemporaryDirectory(prefix="campaign-session-one-snapshot-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        (session_dir / "pre-compact-only.md").write_text("ONLY_SNAPSHOT_BODY", encoding="utf-8")
        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        output = run_hook(bootstrap, root, "NEW-ONE", {"session_id": "NEW-ONE"})
        context = output.get("additional_context", "")
        assert "[CONTEXT_BUDGET_SNAPSHOT_FALLBACK]" in context
        assert "ONLY_SNAPSHOT_BODY" in context
        assert read_state(root, "NEW-ONE")["campaign_id"] == "NEW-ONE"

    with tempfile.TemporaryDirectory(prefix="campaign-session-multi-snapshot-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        (session_dir / "pre-compact-A.md").write_text("SNAPSHOT_A_BODY", encoding="utf-8")
        (session_dir / "pre-compact-B.md").write_text("SNAPSHOT_B_BODY", encoding="utf-8")
        bootstrap = write_script(BOOTSTRAP_TEMPLATE, root, "session-bootstrap.sh")
        output = run_hook(bootstrap, root, "NEW-MANY", {"session_id": "NEW-MANY"})
        context = output.get("additional_context", "")
        assert "[CONTEXT_BUDGET_SNAPSHOT_SELECT]" in context
        assert "pre-compact-A.md" in context and "pre-compact-B.md" in context
        assert "SNAPSHOT_A_BODY" not in context and "SNAPSHOT_B_BODY" not in context
        assert read_state(root, "NEW-MANY")["campaign_id"] == "NEW-MANY"


def test_template_contracts() -> None:
    manifest = MANIFEST.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP_TEMPLATE.read_text(encoding="utf-8")
    evaluator = EVALUATOR_TEMPLATE.read_text(encoding="utf-8")
    observer = OBSERVER_TEMPLATE.read_text(encoding="utf-8")
    start_gate = START_GATE_TEMPLATE.read_text(encoding="utf-8")
    plan_gate = PLAN_GATE_TEMPLATE.read_text(encoding="utf-8")
    orchestrator = ORCHESTRATOR_TEMPLATE.read_text(encoding="utf-8")

    assert 'tracking_artifact: ".cursor/.tracking/tracker-{campaign_id}.md"' in manifest
    assert "campaign_id_field: \"campaign_id\"" in manifest
    assert "tracker_path_pattern: \".cursor/.tracking/tracker-{campaign_id}.md\"" in manifest
    assert "campaign_id" in bootstrap and "campaign_id" in evaluator and "campaign_id" in observer
    for source in (bootstrap, evaluator, observer):
        assert "tracker-${SESSION_ID}" not in source, "SESSION_ID から tracker を作る実装が残っている"
    for source in (evaluator, observer):
        assert "{{project.tracking_artifact}}" in source
        assert 'tracker-${CAMPAIGN_ID}.md' not in source, "tracker パスが manifest を迂回して固定されている"
    assert "bind_campaign_from_handoff" in bootstrap
    assert "HANDOFF_COUNT >= 2" in bootstrap
    assert ".campaign_id = $cid | .campaign_id_source = $source" in bootstrap
    assert "${tracking_base//\\{campaign_id\\}/*}" in start_gate
    assert "${tracking_base//\\{campaign_id\\}/*}" in plan_gate
    assert "campaign_slug" in orchestrator and "campaign_id" in orchestrator


def main() -> int:
    tests = (
        test_runtime_mint_bind_and_tracker_lookup,
        test_multi_handoff_select_binds_campaign,
        test_no_handoff_mints_and_does_not_guess_existing_tracker,
        test_handoff_reconciliation_uses_matching_origin,
        test_handoff_pointer_warning_uses_raw_manifest,
        test_handoff_presence_blocks_snapshot_fallback,
        test_no_handoff_snapshot_matrix,
        test_template_contracts,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_campaign_session_binding] FAIL: {test.__name__}: {exc}")
            return 1
    print(f"[test_campaign_session_binding] PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
