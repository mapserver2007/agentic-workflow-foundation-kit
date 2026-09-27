#!/usr/bin/env python3
"""guard-git-write.sh の git グローバルオプション正規化回帰。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SKILL = HERE.parent
HOOK_TEMPLATE = SKILL / "templates" / "hooks" / "guard-git-write.sh.template"
ENGINE_SCRIPTS = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"


def _render_hook(target: Path) -> Path:
    if str(ENGINE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(ENGINE_SCRIPTS))
    from genlib import load_manifest, render

    hook = target / "guard-git-write.sh"
    hook.write_text(
        render(
            HOOK_TEMPLATE.read_text(encoding="utf-8"),
            load_manifest(str(SKILL / "manifest.yaml")),
        ),
        encoding="utf-8",
    )
    hook.chmod(0o755)
    return hook


def _run(hook: Path, command: str, *, failclose: bool = False) -> dict:
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
                ["/bin/bash", str(hook)],
                input=payload,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
    else:
        result = subprocess.run(
            ["bash", str(hook)],
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


def test_global_options_are_normalized_for_json_route(hook: Path) -> None:
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
        output = _run(hook, command)
        assert output.get("permission") == "deny", (command, output)


def test_failclose_route_asks_for_normalized_deny_classes(hook: Path) -> None:
    for command in (
        "git -C /tmp push origin main",
        "git -c core.commentChar=x push --force",
        'git -C "/tmp/work tree" push origin main',
        "git --git-dir=/tmp -C /tmp push origin main",
    ):
        output = _run(hook, command, failclose=True)
        assert output.get("permission") == "ask", (command, output)


def test_local_git_commands_remain_allowed(hook: Path) -> None:
    for command in (
        "git status",
        "git --work-tree=/tmp status",
        'git --work-tree="/tmp/work tree" status',
    ):
        output = _run(hook, command)
        assert output == {}, (command, output)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="guard-git-write-render-") as temp_dir:
        hook = _render_hook(Path(temp_dir))
        test_global_options_are_normalized_for_json_route(hook)
        test_failclose_route_asks_for_normalized_deny_classes(hook)
        test_local_git_commands_remain_allowed(hook)
    print("[test_guard_git_write] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
