#!/usr/bin/env python3
"""session-progress-emitter template のイベント契約と fail-open を検査する。"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
TEMPLATE = SKILL_DIR / "templates" / "hooks" / "session-progress-emitter.sh.template"
HOOKS_TEMPLATE = SKILL_DIR / "templates" / "hooks.json.template"
README_TEMPLATE = SKILL_DIR / "templates" / "hooks" / "README.md.template"
MANIFEST = SKILL_DIR / "manifest.yaml"
BASH_EXECUTABLE = "/bin/bash"


def run_hook(script: Path, root: Path, payload: str, *, session_id: str = "test-emit-001") -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update({
        "CURSOR_PROJECT_DIR": str(root),
        "CTX_BUDGET_SESSION_ID": session_id,
    })
    return subprocess.run(  # noqa: S603 - Runs a controlled temporary test fixture.
        [BASH_EXECUTABLE, str(script)],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_event_contract() -> None:
    payloads = (
        ({"prompt": "hi", "model": "main-model"}, "prompt"),
        ({"hook_event_name": "afterAgentThought", "text": "thinking"}, "thought"),
        ({"hook_event_name": "afterAgentResponse", "text": "hello"}, "response"),
        ({"hook_event_name": "afterShellExecution", "command": "true", "output": "ok"}, "shell"),
        ({
            "hook_event_name": "subagentStart",
            "subagent_id": "s1",
            "subagent_type": "generalPurpose",
            "subagent_model": "sub-model",
            "model": "main-model",
            "task": "example",
        }, "subagent_start"),
        ({
            "hook_event_name": "subagentStop",
            "subagent_id": "s1",
            "subagent_type": "generalPurpose",
            "status": "completed",
            "duration_ms": 1000,
            "model": "main-model",
            "task": "example",
        }, "subagent_stop"),
    )
    with tempfile.TemporaryDirectory(prefix="progress-emitter-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        script = root / "session-progress-emitter.sh"
        script.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o700)
        for payload, _ in payloads:
            result = run_hook(script, root, json.dumps(payload))
            assert_equal(result.returncode, 0, "hook exit code")
            assert_equal(result.stdout, "{}\n", "hook stdout")

        rows = [
            json.loads(line)
            for line in (session_dir / "test-emit-001.progress.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert_equal([row["kind"] for row in rows], [kind for _, kind in payloads], "event kinds")
        for row in rows:
            assert set(("at", "session_id", "kind", "bytes", "summary", "extra")).issubset(row), "common fields missing"
            assert_equal(row["session_id"], "test-emit-001", "session ID")
        assert_equal(rows[0]["extra"]["model"], "main-model", "prompt model")
        assert_equal(rows[3]["extra"]["output_tail"], "ok", "shell output_tail")
        assert_equal(rows[4]["extra"]["subagent_model"], "sub-model", "start model")
        if "subagent_model" in rows[5]["extra"]:
            raise AssertionError("stop event must not contain subagent_model")
        assert_equal(rows[5]["extra"]["subagent_id"], "s1", "stop ID")


def test_shell_exit_code_and_output_tail() -> None:
    cases = (
        (
            {
                "hook_event_name": "afterShellExecution",
                "command": "gate",
                "output": "",
                "stdout": "=== session-start gate: PASS ===\n",
                "exit_code": "",
                "exitCode": 0,
            },
            {"exit_code": 0, "output_tail": "=== session-start gate: PASS ==="},
        ),
        (
            {
                "hook_event_name": "afterShellExecution",
                "command": "gate",
                "output": "primary",
                "stdout": "fallback",
                "status_code": 2,
            },
            {"exit_code": 2, "output_tail": "primary"},
        ),
        (
            {
                "hook_event_name": "afterShellExecution",
                "command": "gate",
                "result": {"msg": "obj"},
            },
            {"output_tail": '{"msg":"obj"}'},
        ),
    )
    with tempfile.TemporaryDirectory(prefix="progress-emitter-shell-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        script = root / "session-progress-emitter.sh"
        script.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o700)

        for index, (payload, expected_extra) in enumerate(cases):
            session_id = f"shell-extra-{index}"
            result = run_hook(script, root, json.dumps(payload), session_id=session_id)
            assert_equal(result.returncode, 0, f"shell case {index} exit code")
            assert_equal(result.stdout, "{}\n", f"shell case {index} stdout")
            rows = [
                json.loads(line)
                for line in (session_dir / f"{session_id}.progress.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            assert_equal(len(rows), 1, f"shell case {index} row count")
            assert_equal(rows[0]["kind"], "shell", f"shell case {index} kind")
            for key, value in expected_extra.items():
                assert_equal(rows[0]["extra"].get(key), value, f"shell case {index} extra.{key}")

        # Long output keeps only the last ~6KiB.
        long_body = ("A" * 7000) + "TAIL_MARKER"
        long_result = run_hook(
            script,
            root,
            json.dumps({
                "hook_event_name": "afterShellExecution",
                "command": "long",
                "output": long_body,
                "exit_code": 1,
            }),
            session_id="shell-extra-long",
        )
        assert_equal(long_result.returncode, 0, "long shell exit code")
        long_row = json.loads((session_dir / "shell-extra-long.progress.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert_equal(long_row["extra"]["exit_code"], 1, "long shell exit_code")
        assert long_row["extra"]["output_tail"].endswith("TAIL_MARKER"), "long shell output_tail must keep end"
        assert len(long_row["extra"]["output_tail"].encode("utf-8")) <= 6144, "long shell output_tail must be truncated"


def test_payload_session_fallback_and_fail_open() -> None:
    with tempfile.TemporaryDirectory(prefix="progress-emitter-fallback-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        script = root / "session-progress-emitter.sh"
        script.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o700)

        env = dict(os.environ)
        env["CURSOR_PROJECT_DIR"] = str(root)
        env.pop("CTX_BUDGET_SESSION_ID", None)
        payload = json.dumps({"prompt": "fallback", "conversation_id": "fallback-001"})
        result = subprocess.run(  # noqa: S603 - Runs a controlled temporary test fixture.
            [BASH_EXECUTABLE, str(script)],
            input=payload,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        assert_equal(result.returncode, 0, "fallback hook exit code")
        assert_equal(result.stdout, "{}\n", "fallback hook stdout")
        assert (session_dir / "fallback-001.progress.jsonl").is_file(), "conversation_id fallback did not write"

        invalid = run_hook(script, root, "not-json")
        assert_equal(invalid.returncode, 0, "invalid JSON exit code")
        assert_equal(invalid.stdout, "{}\n", "invalid JSON stdout")
        unsafe = run_hook(script, root, json.dumps({"prompt": "bad"}), session_id="../unsafe")
        assert_equal(unsafe.returncode, 0, "unsafe session ID exit code")
        assert_equal(unsafe.stdout, "{}\n", "unsafe session ID stdout")

        command_dir = root / "without-jq"
        command_dir.mkdir()
        for command in ("cat", "wc", "tr", "date", "pwd"):
            executable = shutil.which(command)
            if executable is None:
                raise AssertionError(f"test prerequisite missing: {command}")
            (command_dir / command).symlink_to(executable)
        no_jq_env = dict(os.environ)
        no_jq_env.update({
            "CURSOR_PROJECT_DIR": str(root),
            "CTX_BUDGET_SESSION_ID": "no-jq-001",
            "PATH": str(command_dir),
        })
        no_jq = subprocess.run(  # noqa: S603 - Runs a controlled temporary test fixture.
            [BASH_EXECUTABLE, str(script)],
            input=json.dumps({"prompt": "no jq"}),
            text=True,
            capture_output=True,
            env=no_jq_env,
            check=False,
        )
        assert_equal(no_jq.returncode, 0, "jq unavailable exit code")
        assert_equal(no_jq.stdout, "{}\n", "jq unavailable stdout")
        assert not (session_dir / "no-jq-001.progress.jsonl").exists(), "jq unavailable must not write"


def test_concurrent_writes_preserve_jsonl() -> None:
    if shutil.which("flock") is None:
        return

    with tempfile.TemporaryDirectory(prefix="progress-emitter-concurrent-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        script = root / "session-progress-emitter.sh"
        script.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o700)

        env = dict(os.environ)
        env.update({
            "CURSOR_PROJECT_DIR": str(root),
            "CTX_BUDGET_SESSION_ID": "concurrent-001",
        })
        processes = [
            subprocess.Popen(  # noqa: S603 - Runs a controlled temporary test fixture.
                [BASH_EXECUTABLE, str(script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            for _ in range(32)
        ]

        for index, process in enumerate(processes):
            assert process.stdin is not None
            process.stdin.write(json.dumps({"prompt": f"concurrent-{index}"}))
            process.stdin.close()

        for process in processes:
            process.wait(timeout=5)
            assert_equal(process.returncode, 0, "concurrent hook exit code")
            assert process.stdout is not None
            assert process.stderr is not None
            assert_equal(process.stdout.read(), "{}\n", "concurrent hook stdout")
            assert_equal(process.stderr.read(), "", "concurrent hook stderr")

        rows = [
            json.loads(line)
            for line in (session_dir / "concurrent-001.progress.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert_equal(len(rows), 32, "concurrent JSONL row count")
        assert_equal(
            {row["summary"] for row in rows},
            {f"concurrent-{index}" for index in range(32)},
            "concurrent JSONL summaries",
        )


def test_lock_wait_is_bounded_and_fail_open() -> None:
    if shutil.which("flock") is None:
        return

    with tempfile.TemporaryDirectory(prefix="progress-emitter-lock-") as tmp:
        root = Path(tmp)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True)
        script = root / "session-progress-emitter.sh"
        script.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        script.chmod(0o700)
        lock_file = session_dir / "test-emit-001.lock"

        with lock_file.open("w", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            started_at = time.monotonic()
            result = run_hook(script, root, json.dumps({"prompt": "blocked"}))
            elapsed = time.monotonic() - started_at
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

        assert_equal(result.returncode, 0, "bounded lock hook exit code")
        assert_equal(result.stdout, "{}\n", "bounded lock hook stdout")
        assert elapsed < 2, f"lock wait exceeded bound: {elapsed:.2f}s"
        assert not (session_dir / "test-emit-001.progress.jsonl").exists(), "bounded lock must not write"


def test_static_registration_contract() -> None:
    hooks = HOOKS_TEMPLATE.read_text(encoding="utf-8")
    for event in (
        '"beforeSubmitPrompt"',
        '"afterAgentThought"',
        '"afterAgentResponse"',
        '"afterShellExecution"',
        '"subagentStart"',
        '"subagentStop"',
    ):
        assert event in hooks, f"missing hook event {event}"
    assert hooks.count(".cursor/hooks/session-progress-emitter.sh") == 6, "emitter registration count"

    manifest = MANIFEST.read_text(encoding="utf-8")
    for needle in ("subagentStart", "subagentStop", "{session_id}.progress.jsonl", "session-progress-emitter.sh"):
        assert needle in manifest, f"manifest missing {needle}"
    readme = README_TEMPLATE.read_text(encoding="utf-8")
    assert "subagent_stop" in readme and "subagent_model` は含めない" in readme, "README contract missing"
    assert "`shell` の `extra`" in readme and "output_tail" in readme, "README shell extra contract missing"


def main() -> int:
    tests = (
        test_event_contract,
        test_shell_exit_code_and_output_tail,
        test_payload_session_fallback_and_fail_open,
        test_concurrent_writes_preserve_jsonl,
        test_lock_wait_is_bounded_and_fail_open,
        test_static_registration_contract,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_session_progress_emitter] FAIL: {test.__name__}: {exc}")
            return 1
    print(f"[test_session_progress_emitter] PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
