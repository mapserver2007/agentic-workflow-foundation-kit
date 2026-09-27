#!/usr/bin/env python3
"""guard-git-write.sh の git グローバルオプション正規化回帰。"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
HOOK = ROOT / ".cursor" / "hooks" / "guard-git-write.sh"


def _run(command: str, *, failclose: bool = False) -> dict:
    payload = json.dumps({"command": command}) if not failclose else '{"command":"' + command
    env = dict()
    if failclose:
        with tempfile.TemporaryDirectory(prefix="guard-git-write-path-") as temp_dir:
            path_dir = Path(temp_dir)
            for name in ("cat", "tr"):
                target = shutil.which(name)
                if target is None:
                    raise AssertionError(f"{name} が見つからず failclose 経路を検証できません")
                (path_dir / name).symlink_to(target)
            env["PATH"] = str(path_dir)
            result = subprocess.run(
                ["/bin/bash", str(HOOK)],
                input=payload,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
    else:
        result = subprocess.run(
            ["bash", str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        raise AssertionError(
            f"Hook が終了コード {result.returncode} を返しました: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Hook の JSON 出力を解釈できません: {result.stdout!r}") from exc


def test_global_options_are_normalized_for_json_route() -> None:
    deny_commands = (
        "git -C /tmp push --force",
        "git --git-dir=/tmp push --force",
        "git --git-dir /tmp push --force",
        "git --work-tree=/tmp push --force",
        "git --work-tree /tmp push --force",
        "git -c core.commentChar=x push --force",
        "git -C /tmp push origin main",
        "git -c core.commentChar=x push origin main",
        'git -C "/tmp/work tree" push origin main',
        "git -C '/tmp/work tree' push origin main",
        "git --git-dir=/tmp -C /tmp push origin main",
        'git --git-dir="/tmp/work tree" push origin main',
        'git --git-dir=/tmp -C "/tmp/work tree" push --force',
    )
    for command in deny_commands:
        output = _run(command)
        assert output.get("permission") == "deny", (command, output)


def test_failclose_route_asks_for_normalized_deny_classes() -> None:
    for command in (
        "git -C /tmp push origin main",
        "git -c core.commentChar=x push --force",
        'git -C "/tmp/work tree" push origin main',
        "git --git-dir=/tmp -C /tmp push origin main",
    ):
        output = _run(command, failclose=True)
        assert output.get("permission") == "ask", (command, output)


def test_local_git_commands_remain_allowed() -> None:
    for command in (
        "git status",
        "git --work-tree=/tmp status",
        'git --work-tree="/tmp/work tree" status',
    ):
        output = _run(command)
        assert output == {}, (command, output)


def main() -> int:
    if not HOOK.is_file():
        print("SKIP: generated guard-git-write.sh not found (pre-generate)")
        return 0
    test_global_options_are_normalized_for_json_route()
    test_failclose_route_asks_for_normalized_deny_classes()
    test_local_git_commands_remain_allowed()
    print("[test_guard_git_write] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
