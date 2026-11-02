#!/usr/bin/env python3
"""inspect_local_repository.py のローカル fixture test。"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
if os.fspath(HERE) not in sys.path:
    sys.path.insert(0, os.fspath(HERE))

import inspect_local_repository as inspect_mod  # noqa: E402


def _git_env() -> dict:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in inspect_mod.SANITIZED_GIT_ENV_KEYS
        and not key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
    }


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", os.fspath(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        env=_git_env(),
    )


def commit_all(root: Path, message: str = "fixture") -> None:
    run_git(root, "add", "-A")
    run_git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        message,
    )


class RepositoryFixture:
    def __init__(self, parent: Path, name: str = "repo") -> None:
        self.root = parent / name
        self.root.mkdir()
        run_git(self.root, "init", "-q")
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        commit_all(self.root)
        run_git(self.root, "remote", "add", "origin", "https://github.com/Owner/Repo.git")


class NormalizeUrlTests(unittest.TestCase):
    def test_origin_normalization(self) -> None:
        for value in (
            "https://github.com/owner/repo.git",
            "git@github.com:owner/repo.git",
            "ssh://git@github.com/owner/repo.git",
        ):
            origin = inspect_mod.normalize_origin_url(value)
            self.assertEqual((origin.owner, origin.repo), ("owner", "repo"))
            self.assertEqual(origin.canonical_url, "https://github.com/owner/repo")

    def test_invalid_origin_urls_and_owner_repo(self) -> None:
        invalid = (
            "http://github.com/o/r",
            "https://user@github.com/o/r",
            "https://github.com/o/r/tree/main",
            "https://github.com/o/r?x=1",
            "https://gitlab.com/o/r",
            "https://github.com/./r",
            "https://github.com/o/..",
            "https://github.com/o!/r",
            "https://github.com/o/r!",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(inspect_mod.InspectionError) as caught:
                inspect_mod.normalize_origin_url(value)
            self.assertEqual(caught.exception.code, 2)

    def test_credential_origin_is_not_exposed(self) -> None:
        secret = "ghp_SUPERSECRET"
        with self.assertRaises(inspect_mod.InspectionError) as caught:
            inspect_mod.normalize_origin_url(f"https://user:{secret}@github.com/o/r.git")
        self.assertNotIn(secret, str(caught.exception))


class InspectRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.fixture = RepositoryFixture(self.base)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def inspect(self) -> inspect_mod.RepositoryInspection:
        return inspect_mod.inspect_repository(os.fspath(self.fixture.root))

    def test_clean_branch_uses_origin_as_source_repository(self) -> None:
        result = self.inspect()
        self.assertEqual(result.source_repository, "https://github.com/Owner/Repo")
        self.assertRegex(result.source_revision, r"^[0-9a-f]{40}$")
        self.assertNotEqual(result.source_ref, "detached")
        self.assertEqual(result.uninitialized_submodules, 0)

    def test_detached_head(self) -> None:
        revision = run_git(self.fixture.root, "rev-parse", "HEAD").stdout.decode().strip()
        run_git(self.fixture.root, "checkout", "--detach", "-q", revision)
        self.assertEqual(self.inspect().source_ref, "detached")

    def test_dirty_is_exit_one(self) -> None:
        (self.fixture.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaises(inspect_mod.InspectionError) as caught:
            self.inspect()
        self.assertEqual(caught.exception.code, 1)

    def test_origin_change_is_reflected_without_url_input(self) -> None:
        run_git(self.fixture.root, "remote", "set-url", "origin", "https://github.com/o/other.git")
        self.assertEqual(self.inspect().source_repository, "https://github.com/o/other")

    def test_subdirectory_bare_and_symlink_are_exit_two(self) -> None:
        subdir = self.fixture.root / "sub"
        subdir.mkdir()
        bare = self.base / "bare.git"
        run_git(self.base, "init", "--bare", "-q", os.fspath(bare))
        link = self.base / "link"
        link.symlink_to(self.fixture.root, target_is_directory=True)
        for path in (subdir, bare, link):
            with self.subTest(path=path), self.assertRaises(inspect_mod.InspectionError) as caught:
                inspect_mod.inspect_repository(os.fspath(path))
            self.assertEqual(caught.exception.code, 2)

    def test_missing_and_multiple_origin_are_exit_two(self) -> None:
        run_git(self.fixture.root, "remote", "remove", "origin")
        with self.assertRaises(inspect_mod.InspectionError) as caught:
            self.inspect()
        self.assertEqual(caught.exception.code, 2)
        run_git(self.fixture.root, "remote", "add", "origin", "https://github.com/owner/repo")
        run_git(
            self.fixture.root,
            "config",
            "--add",
            "remote.origin.url",
            "https://github.com/owner/repo-two",
        )
        with self.assertRaises(inspect_mod.InspectionError) as caught:
            self.inspect()
        self.assertEqual(caught.exception.code, 2)

    def test_uninitialized_submodule_count(self) -> None:
        submodule_root = self.base / "submodule"
        submodule_root.mkdir()
        run_git(submodule_root, "init", "-q")
        (submodule_root / "x").write_text("x\n", encoding="utf-8")
        commit_all(submodule_root)
        run_git(
            self.fixture.root,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            os.fspath(submodule_root),
            "deps/sub",
        )
        commit_all(self.fixture.root, "submodule")
        subprocess.run(
            ["git", "-C", os.fspath(self.fixture.root), "submodule", "deinit", "-f", "deps/sub"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            env=_git_env(),
        )
        self.assertEqual(self.inspect().uninitialized_submodules, 1)

    def test_cli_json_strings_use_non_ascii_without_surrogates(self) -> None:
        result = inspect_mod.RepositoryInspection(
            source_repository="https://github.com/o/r",
            source_ref='-分岐:#"\\\'😀',
            source_revision="a" * 40,
            uninitialized_submodules=0,
            raw_origin="https://github.com/o/r",
            source_root="/unused",
            source_root_realpath="/unused",
        )
        output = io.StringIO()
        with mock.patch.object(inspect_mod, "inspect_repository", return_value=result):
            with contextlib.redirect_stdout(output):
                exit_code = inspect_mod.main(["--source-root", "/unused"])
        self.assertEqual(exit_code, 0)
        ref_literal = output.getvalue().splitlines()[1].split(": ", 1)[1]
        self.assertEqual(json.loads(ref_literal), result.source_ref)
        self.assertNotIn("\\ud83d", ref_literal.lower())

    def test_fake_git_records_only_read_only_local_commands(self) -> None:
        fake = self.base / "fake-git"
        log = self.base / "commands.log"
        root = self.base / "fake-root"
        root.mkdir()
        script = f"""#!/usr/bin/env python3
from __future__ import annotations
import os, sys
with open({os.fspath(log)!r}, "a", encoding="utf-8") as stream:
    stream.write(" ".join(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if args[-2:] == ["rev-parse", "--is-bare-repository"]: print("false")
elif args[-2:] == ["rev-parse", "--show-toplevel"]: print({os.fspath(root)!r})
elif args[-3:] == ["config", "--get-all", "remote.origin.url"]: print("https://github.com/o/r")
elif args[-2:] == ["rev-parse", "HEAD"]: print("a" * 40)
elif args[-4:] == ["symbolic-ref", "--quiet", "--short", "HEAD"]: print("main")
elif args[-3:] == ["status", "--porcelain=v1", "--untracked-files=all"]: pass
elif args[-3:] == ["ls-files", "-s", "-z"]: pass
else: sys.exit(9)
"""
        fake.write_text(script, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        before = sorted(path.name for path in root.iterdir())
        inspect_mod.inspect_repository(
            os.fspath(root),
            git_executable=os.fspath(fake),
        )
        after = sorted(path.name for path in root.iterdir())
        self.assertEqual(before, after)
        commands = log.read_text(encoding="utf-8")
        self.assertIn("--no-optional-locks", commands)
        self.assertIn("core.fsmonitor=false", commands)
        self.assertIn("core.hooksPath=/dev/null", commands)
        for forbidden in ("clone", "fetch", "pull", "push", "checkout", "reset", "clean", "stash", "submodule update"):
            self.assertNotIn(forbidden, commands)

    def test_fixture_git_ignores_parent_repository_env(self) -> None:
        missing = os.fspath(self.base / "missing-git-dir")
        (self.fixture.root / "another.txt").write_text("x\n", encoding="utf-8")
        with mock.patch.dict(
            os.environ,
            {
                "GIT_DIR": missing,
                "GIT_WORK_TREE": missing,
                "GIT_INDEX_FILE": missing,
                "GIT_CONFIG_KEY_0": "core.fsmonitor",
                "GIT_CONFIG_VALUE_0": missing,
            },
        ):
            commit_all(self.fixture.root, "under redirected env")
            revision = run_git(self.fixture.root, "rev-parse", "HEAD").stdout.decode().strip()
        self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_malicious_fsmonitor_and_git_environment_are_neutralized(self) -> None:
        marker = self.base / "fsmonitor-ran"
        monitor = self.base / "fsmonitor"
        monitor.write_text(
            "#!/bin/sh\n"
            f"printf invoked > {os.fspath(marker)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        monitor.chmod(monitor.stat().st_mode | stat.S_IXUSR)
        run_git(self.fixture.root, "config", "core.fsmonitor", os.fspath(monitor))
        malicious_config = self.base / "malicious.gitconfig"
        malicious_config.write_text(
            "[remote \"origin\"]\n"
            "  url = https://github.com/attacker/redirected\n"
            "[core]\n"
            f"  fsmonitor = {os.fspath(monitor)}\n",
            encoding="utf-8",
        )
        missing = os.fspath(self.base / "redirected")
        result = inspect_mod.inspect_repository(
            os.fspath(self.fixture.root),
            env={
                "GIT_DIR": missing,
                "GIT_WORK_TREE": missing,
                "GIT_OBJECT_DIRECTORY": missing,
                "GIT_ALTERNATE_OBJECT_DIRECTORIES": missing,
                "GIT_CONFIG": os.fspath(malicious_config),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.fsmonitor",
                "GIT_CONFIG_VALUE_0": os.fspath(monitor),
            },
        )
        self.assertEqual(result.source_repository, "https://github.com/Owner/Repo")
        self.assertFalse(marker.exists())

    def test_invalid_head_from_fake_git_is_exit_two(self) -> None:
        with mock.patch.object(
            inspect_mod,
            "_safe_git",
            side_effect=[
                subprocess.CompletedProcess([], 0, b"false\n"),
                subprocess.CompletedProcess([], 0, (os.fspath(self.fixture.root) + "\n").encode()),
                subprocess.CompletedProcess([], 0, b"https://github.com/owner/repo\n"),
                subprocess.CompletedProcess([], 0, b"short\n"),
            ],
        ):
            with self.assertRaises(inspect_mod.InspectionError) as caught:
                self.inspect()
        self.assertEqual(caught.exception.code, 2)


class RuntimeContractTests(unittest.TestCase):
    def test_python39_syntax_and_future_import(self) -> None:
        scripts = (
            HERE / "inspect_local_repository.py",
            HERE / "validate_design_doc.py",
            HERE / "publish_design_doc.py",
            HERE / "test_inspect_local_repository.py",
            HERE / "test_validate_technology_stack_design.py",
        )
        for path in scripts:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=os.fspath(path), feature_version=(3, 9))
            tree = ast.parse(source)
            future_names = {
                alias.name
                for node in tree.body
                if isinstance(node, ast.ImportFrom) and node.module == "__future__"
                for alias in node.names
            }
            self.assertIn("annotations", future_names, os.fspath(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
