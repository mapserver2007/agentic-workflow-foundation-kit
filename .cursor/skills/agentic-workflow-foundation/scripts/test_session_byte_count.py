#!/usr/bin/env python3
"""Context Budget の UTF-8 byte-count 契約を検査する。"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
ROOT = SKILL_DIR.parent.parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates"
HOOK_DIR = ROOT / ".cursor" / "hooks"
BASH = "/bin/bash"

BYTE_HELPER_TEMPLATE = TEMPLATE_DIR / "hooks" / "session-byte-count.sh.template"
HOOK_NAMES = (
    "session-bootstrap.sh",
    "session-budget-tracker.sh",
    "session-shell-tracker.sh",
    "session-response-tracker.sh",
    "session-progress-emitter.sh",
    "session-progress-append.sh",
    "session-compact-observer.sh",
)
OBSERVATION_HOOK_NAMES = tuple(
    name for name in HOOK_NAMES if name != "session-progress-append.sh"
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def install_hooks(root: Path, names: tuple[str, ...] = HOOK_NAMES) -> Path:
    destination = root / ".cursor" / "hooks"
    destination.mkdir(parents=True, exist_ok=True)
    helper_target = destination / "session-byte-count.sh"
    helper_target.write_bytes((HOOK_DIR / "session-byte-count.sh").read_bytes())
    helper_target.chmod(0o700)
    for name in names:
        source = HOOK_DIR / name
        target = destination / name
        target.write_bytes(source.read_bytes())
        target.chmod(0o700)
    return destination


def run_hook(
    root: Path,
    name: str,
    session_id: str,
    payload: dict,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update({
        "CURSOR_PROJECT_DIR": str(root),
        "CTX_BUDGET_SESSION_ID": session_id,
    })
    return subprocess.run(  # noqa: S603 - controlled fixture script and environment
        [BASH, str(root / ".cursor" / "hooks" / name)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        env=env,
        check=False,
        timeout=10,
    )


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def helper_call(helper: Path, operation: str, text: str, limit: int = 0) -> tuple[str, str]:
    program = r'''
source "$1"
case "$2" in
  count) session_byte_count "$4" ;;
  prefix) session_byte_prefix "$3" "$4" ;;
  suffix) session_byte_suffix "$3" "$4" ;;
  *) exit 2 ;;
esac
printf '\n'
IFS= read -r line || true
printf 'stdin=%s\n' "$line"
'''
    result = subprocess.run(  # noqa: S603 - controlled helper fixture
        [BASH, "-c", program, "byte-count-test", str(helper), operation, str(limit), text],
        input="preserved\n",
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert_equal(result.returncode, 0, f"helper {operation} return code")
    output, stdin_line = result.stdout.split("\n", 1)
    assert_equal(stdin_line, "stdin=preserved\n", f"helper {operation} stdin preservation")
    return output, result.stderr


def test_helper_api_and_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="session-byte-count-") as tmp:
        root = Path(tmp)
        helper = root / "session-byte-count.sh"
        helper.write_bytes(BYTE_HELPER_TEMPLATE.read_bytes())
        helper.chmod(0o700)

        fixtures = (
            ("ascii", "ASCII-0123", len("ASCII-0123".encode("utf-8"))),
            ("japanese", "あ" * 17, 17 * 3),
            ("emoji", "😀" * 11, 11 * 4),
        )
        for label, text, expected_bytes in fixtures:
            actual, _ = helper_call(helper, "count", text)
            assert_equal(int(actual), expected_bytes, f"{label} byte count")

        invalid = subprocess.run(  # noqa: S603 - controlled helper fixture
            [
                BASH,
                "-c",
                'source "$1"; session_byte_count "$4"',
                "byte-count-invalid",
                str(helper),
                "count",
                "0",
                b"\xff",
            ],
            capture_output=True,
            check=False,
            timeout=10,
        )
        assert_equal(invalid.returncode, 2, "invalid UTF-8 byte count return code")
        assert_equal(invalid.stdout, b"", "invalid UTF-8 byte count stdout")
        assert_equal(invalid.stderr, b"", "invalid UTF-8 byte count stderr")

        code_point_fixtures = (("A", 1), ("é", 2), ("あ", 3), ("😀", 4))
        for text, size in code_point_fixtures:
            actual, _ = helper_call(helper, "count", text)
            assert_equal(int(actual), size, f"code point size for {text}")
            for limit in range(1, 5):
                prefix, _ = helper_call(helper, "prefix", text, limit)
                suffix, _ = helper_call(helper, "suffix", text, limit)
                expected = text.encode("utf-8")[:limit].decode("utf-8", "ignore")
                expected_suffix = text.encode("utf-8")[-limit:].decode("utf-8", "ignore")
                assert_equal(prefix, expected, f"prefix {text} at {limit}")
                assert_equal(suffix, expected_suffix, f"suffix {text} at {limit}")

        boundary_text = ("あ😀" * 5000) + "終端"
        for limit in (1000, 4096, 6144, 8192):
            prefix, _ = helper_call(helper, "prefix", boundary_text, limit)
            suffix, _ = helper_call(helper, "suffix", boundary_text, limit)
            for label, result in (("prefix", prefix), ("suffix", suffix)):
                encoded = result.encode("utf-8")
                assert len(encoded) <= limit, f"{label} exceeds {limit} bytes"
                encoded.decode("utf-8")
            expected_prefix = boundary_text.encode("utf-8")[:limit].decode("utf-8", "ignore")
            expected_suffix = boundary_text.encode("utf-8")[-limit:].decode("utf-8", "ignore")
            assert_equal(prefix, expected_prefix, f"prefix boundary {limit}")
            assert_equal(suffix, expected_suffix, f"suffix boundary {limit}")


def test_budget_shell_and_response_byte_measurement() -> None:
    japanese = "あ" * 1000
    with tempfile.TemporaryDirectory(prefix="session-byte-hooks-") as tmp:
        root = Path(tmp)
        install_hooks(root)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True, exist_ok=True)

        bootstrap = run_hook(root, "session-bootstrap.sh", "budget-001", {"session_id": "budget-001"})
        assert_equal(bootstrap.returncode, 0, "bootstrap setup")

        budget = run_hook(
            root,
            "session-budget-tracker.sh",
            "budget-001",
            {"prompt": japanese},
        )
        assert_equal(budget.returncode, 0, "budget hook")
        state = json.loads((session_dir / "budget-001.json").read_text(encoding="utf-8"))
        assert_equal(state["prompt_count"], 1, "prompt count")
        assert_equal(state["weighted_prompt_score"], 7, "weighted prompt score")
        turn = read_jsonl(session_dir / "budget-001.turns.jsonl")[0]
        assert_equal(turn["bytes"], 3000, "budget prompt bytes")
        assert len(turn["summary"].encode("utf-8")) <= 1000
        turn["summary"].encode("utf-8").decode("utf-8")

        shell = run_hook(
            root,
            "session-shell-tracker.sh",
            "budget-001",
            {"stdout": japanese},
        )
        assert_equal(shell.returncode, 0, "shell hook")
        state = json.loads((session_dir / "budget-001.json").read_text(encoding="utf-8"))
        assert_equal(state["shell_bytes"], 3000, "shell output bytes")

        response = run_hook(
            root,
            "session-response-tracker.sh",
            "response-001",
            {"text": japanese},
        )
        assert_equal(response.returncode, 0, "response hook")
        response_turn = read_jsonl(session_dir / "response-001.turns.jsonl")[0]
        assert_equal(response_turn["bytes"], 3000, "response bytes")
        assert len(response_turn["summary"].encode("utf-8")) <= 1000
        response_turn["summary"].encode("utf-8").decode("utf-8")


def test_emitter_and_progress_append_byte_contracts() -> None:
    japanese = "あ" * 1000
    long_output = "😀" * 3000
    extra = json.dumps({
        "gate_id": "review",
        "campaign": "byte-count",
        "pr": "https://github.com/owner/repo/pull/1",
        "review_go_id": "a" * 64,
        "source": "review-start-gate",
    }, separators=(",", ":"))
    with tempfile.TemporaryDirectory(prefix="session-byte-progress-") as tmp:
        root = Path(tmp)
        install_hooks(root)
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True, exist_ok=True)

        emitter = run_hook(
            root,
            "session-progress-emitter.sh",
            "emitter-001",
            {"hook_event_name": "afterAgentResponse", "text": japanese},
        )
        assert_equal(emitter.returncode, 0, "emitter response")
        event = read_jsonl(session_dir / "emitter-001.progress.jsonl")[0]
        assert_equal(event["bytes"], len(event["summary"].encode("utf-8")), "emitter summary bytes")
        assert event["bytes"] <= 1000
        event["summary"].encode("utf-8").decode("utf-8")

        shell = run_hook(
            root,
            "session-progress-emitter.sh",
            "emitter-shell-001",
            {
                "hook_event_name": "afterShellExecution",
                "command": "long",
                "output": long_output,
            },
        )
        assert_equal(shell.returncode, 0, "emitter shell")
        shell_event = read_jsonl(session_dir / "emitter-shell-001.progress.jsonl")[0]
        output_tail = shell_event["extra"]["output_tail"]
        assert len(output_tail.encode("utf-8")) <= 6144
        output_tail.encode("utf-8").decode("utf-8")
        assert output_tail.endswith("😀")

        appended = run_hook(
            root,
            "session-progress-append.sh",
            "append-001",
            {},
        )
        # run_hook is not the CLI contract; invoke the writer with its explicit arguments.
        assert_equal(appended.returncode, 2, "append rejects hook payload")
        writer = subprocess.run(  # noqa: S603 - controlled helper fixture
            [
                BASH,
                str(root / ".cursor" / "hooks" / "session-progress-append.sh"),
                "--kind",
                "review_start",
                "--summary",
                japanese,
                "--extra",
                extra,
            ],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "CURSOR_PROJECT_DIR": str(root),
                "CTX_BUDGET_SESSION_ID": "append-001",
            },
            check=False,
            timeout=10,
        )
        assert_equal(writer.returncode, 0, "append UTF-8 summary")
        row = read_jsonl(session_dir / "append-001.progress.jsonl")[0]
        assert row["bytes"] <= 1000
        assert_equal(row["bytes"], len(row["summary"].encode("utf-8")), "append summary bytes")
        row["summary"].encode("utf-8").decode("utf-8")


def test_bootstrap_injection_and_snapshot_limits() -> None:
    handoff = "campaign_id: C1\n## ポインタ\ntracker-C1.md\n" + ("あ" * 3000)
    expected_injected = handoff.encode("utf-8")[:8192].decode("utf-8", "ignore")
    with tempfile.TemporaryDirectory(prefix="session-byte-limits-") as tmp:
        root = Path(tmp)
        install_hooks(root)
        session_dir = root / ".cursor" / ".session"
        tracking_dir = root / ".cursor" / ".tracking"
        session_dir.mkdir(parents=True, exist_ok=True)
        tracking_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "handoff-old.md").write_text(handoff, encoding="utf-8")

        bootstrap = run_hook(root, "session-bootstrap.sh", "bootstrap-001", {"session_id": "bootstrap-001"})
        assert_equal(bootstrap.returncode, 0, "handoff bootstrap")
        bootstrap_output = json.loads(bootstrap.stdout)
        context = bootstrap_output.get("additional_context", "")
        assert expected_injected in context, "handoff was not truncated by UTF-8 bytes"
        assert list(session_dir.glob("handoff-consumed-old-*.md"))

        tracker = ("# tracker\n" + ("あ" * 2000) + "TRACKER_TAIL_MARKER\n")
        (tracking_dir / "tracker-C1.md").write_text(tracker, encoding="utf-8")
        state_path = session_dir / "snapshot-001.json"
        state_path.write_text(
            json.dumps({
                "session_id": "snapshot-001",
                "campaign_id": "C1",
                "prompt_count": 15,
                "shell_bytes": 0,
                "compact_count": 1,
            }),
            encoding="utf-8",
        )
        observer = run_hook(
            root,
            "session-compact-observer.sh",
            "snapshot-001",
            {
                "context_usage_percent": 80,
                "context_tokens": 160000,
                "context_window_size": 200000,
                "trigger": "auto",
            },
        )
        assert_equal(observer.returncode, 0, "compact observer")
        snapshot = (session_dir / "pre-compact-snapshot-001.md").read_bytes()
        assert len(snapshot) <= 8192, "snapshot exceeds byte limit"
        snapshot.decode("utf-8")
        assert b"tracker-C1.md" in snapshot
        assert b"TRACKER_TAIL_MARKER" not in snapshot


def test_missing_helper_failure_policy() -> None:
    with tempfile.TemporaryDirectory(prefix="session-byte-failure-") as tmp:
        root = Path(tmp)
        install_hooks(root)
        helper = root / ".cursor" / "hooks" / "session-byte-count.sh"
        helper.unlink()
        session_dir = root / ".cursor" / ".session"
        session_dir.mkdir(parents=True, exist_ok=True)
        payloads = {
            "session-bootstrap.sh": {"session_id": "missing-001"},
            "session-budget-tracker.sh": {"prompt": "x"},
            "session-shell-tracker.sh": {"stdout": "x"},
            "session-response-tracker.sh": {"text": "x"},
            "session-progress-emitter.sh": {"prompt": "x"},
            "session-compact-observer.sh": {"context_usage_percent": 80},
        }
        for name, payload in payloads.items():
            result = run_hook(root, name, "missing-001", payload)
            assert_equal(result.returncode, 0, f"{name} fail-open return")
            assert_equal(result.stdout, "{}\n", f"{name} fail-open output")

        extra = json.dumps({
            "gate_id": "review",
            "campaign": "missing-helper",
            "pr": "https://github.com/owner/repo/pull/1",
            "review_go_id": "b" * 64,
            "source": "review-start-gate",
        }, separators=(",", ":"))
        writer = subprocess.run(  # noqa: S603 - controlled helper fixture
            [
                BASH,
                str(root / ".cursor" / "hooks" / "session-progress-append.sh"),
                "--kind",
                "review_start",
                "--extra",
                extra,
            ],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "CURSOR_PROJECT_DIR": str(root),
                "CTX_BUDGET_SESSION_ID": "missing-001",
            },
            check=False,
            timeout=10,
        )
        assert_equal(writer.returncode, 2, "append fail-closed return")
        assert_equal(writer.stdout, "", "append fail-closed output")
        assert not list(session_dir.glob("*.progress.jsonl")), "failed append wrote a log"


def test_static_contracts() -> None:
    manifest = (SKILL_DIR / "manifest.yaml").read_text(encoding="utf-8")
    hooks_json = (TEMPLATE_DIR / "hooks.json.template").read_text(encoding="utf-8")
    readme = (TEMPLATE_DIR / "hooks" / "README.md.template").read_text(encoding="utf-8")
    internals = (
        TEMPLATE_DIR / "docs" / "references" / "context-budget-internals.md.template"
    ).read_text(encoding="utf-8")
    assert ".cursor/hooks/session-byte-count.sh" in manifest
    assert "hooks/session-byte-count.sh.template" in manifest
    assert "session_byte_prefix" in manifest and "session_byte_suffix" in manifest
    assert "session-byte-count.sh" not in hooks_json
    for name in OBSERVATION_HOOK_NAMES:
        source = (TEMPLATE_DIR / "hooks" / f"{name}.template").read_text(encoding="utf-8")
        assert "BASH_SOURCE" in source, f"{name} does not resolve helper from BASH_SOURCE"
        assert "BYTE_HELPER" in source, f"{name} does not load byte helper"
        for legacy in ("printf '%.1000s'", "head -c", "tail -c", "1000文字"):
            assert legacy not in source, f"{name} retains legacy byte operation: {legacy}"
    append_source = (TEMPLATE_DIR / "hooks" / "session-progress-append.sh.template").read_text(encoding="utf-8")
    assert "session_byte_prefix 1000" in append_source
    assert "session_byte_count" in append_source
    assert "fail 2" in append_source
    assert "UTF-8 byte-count" in readme
    assert "最大 1000 UTF-8 bytes" in readme
    assert "直近最大 20 行" in readme and "20 行すべての保持を保証しない" in readme
    assert "tracker-{campaign_id}.md" in readme and "handoff-{session_id}.md" in readme
    assert "UTF-8 byte-count" in internals
    assert "最大 1000 UTF-8 bytes" in internals
    assert "全件保持は保証しない" in internals
    assert "prompt_count" in internals and "送信回数" in internals


def main() -> int:
    tests = (
        test_helper_api_and_boundaries,
        test_budget_shell_and_response_byte_measurement,
        test_emitter_and_progress_append_byte_contracts,
        test_bootstrap_injection_and_snapshot_limits,
        test_missing_helper_failure_policy,
        test_static_contracts,
    )
    for test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_session_byte_count] FAIL: {test.__name__}: {exc}")
            return 1
    print(f"[test_session_byte_count] PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
