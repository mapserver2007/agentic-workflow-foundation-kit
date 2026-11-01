#!/usr/bin/env python3
"""validate / publish helper のローカル fixture test。"""
from __future__ import annotations

import ast
import contextlib
import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
if os.fspath(HERE) not in sys.path:
    sys.path.insert(0, os.fspath(HERE))

import inspect_local_repository as inspect_mod  # noqa: E402
import publish_design_doc as publish_mod  # noqa: E402
import validate_design_doc as validate_mod  # noqa: E402


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", os.fspath(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def commit(root: Path, message: str) -> None:
    git(root, "add", "-A")
    subprocess.run(
        [
            "git",
            "-C",
            os.fspath(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            message,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def make_document(
    inspection: inspect_mod.RepositoryInspection,
    *,
    declarations: Dict[int, str] | None = None,
    section9_body: str | None = None,
    titles: Dict[int, str] | None = None,
    frontmatter_extra: str = "",
    stack_slug: str = "runtime-unknowntech",
) -> str:
    declarations = declarations or {}
    titles = titles or {}
    lines = [
        "---",
        "status: reverse-draft",
        'title: "Fixture design"',
        'generated_at: "2026-10-30"',
        f"source_repository: {json.dumps(inspection.source_repository, ensure_ascii=False)}",
        f"source_ref: {json.dumps(inspection.source_ref, ensure_ascii=False)}",
        f"source_revision: {json.dumps(inspection.source_revision, ensure_ascii=False)}",
        f"stack_slug: {json.dumps(stack_slug, ensure_ascii=False)}",
    ]
    if frontmatter_extra:
        lines.extend(frontmatter_extra.splitlines())
    lines.extend(["---", "", "# Fixture design", "", "---", "", "## 目次", ""])
    for part, bounds in validate_mod.PART_SECTIONS.items():
        lines.append(f"### Part {part}")
        for section in range(bounds[0], bounds[1] + 1):
            title = titles.get(section, f"任意の節題{section}")
            lines.append(f"{section}. [{title}](#{section}-{title})")
        lines.append("")
    lines.extend(["---", ""])
    for part, bounds in validate_mod.PART_SECTIONS.items():
        if part != 1:
            lines.extend(["---", ""])
        lines.extend([f"## Part {part}: 任意の章題（{validate_mod.PART_ROLE_LABELS[part]}）", ""])
        for section in range(bounds[0], bounds[1] + 1):
            if section != bounds[0]:
                lines.extend(["---", ""])
            lines.append(f"### {section}. {titles.get(section, f'任意の節題{section}')}")
            if section == 9:
                lines.extend(
                    (
                        section9_body
                        or "\n".join(
                            [
                                "観測された技術を列挙する。",
                                "| レイヤ | 技術 | バージョン方針 | 備考 |",
                                "| --- | --- | --- | --- |",
                                "| Runtime | UnknownTech | [要確認] | 観測: fixture |",
                            ]
                        )
                    ).splitlines()
                )
            else:
                lines.append(declarations.get(section, "[要確認]: fixtureで未確定"))
            lines.append("")
    return "\n".join(lines)


class FixtureCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / "source"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "tracked.txt").write_text("evidence\n", encoding="utf-8")
        commit(self.repo, "initial")
        git(self.repo, "remote", "add", "origin", "https://github.com/Owner/Repo.git")
        self.inspection = inspect_mod.inspect_repository(os.fspath(self.repo))
        self.source_repository = self.inspection.source_repository
        self.candidate = self.base / "candidate.md"
        self.write_document(make_document(self.inspection))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_document(self, text: str) -> None:
        self.candidate.write_text(text, encoding="utf-8")

    def validate(self, *, syntax_only: bool = False) -> validate_mod.ValidationResult:
        return validate_mod.validate_document(
            os.fspath(self.candidate),
            source_root=None if syntax_only else os.fspath(self.repo),
            syntax_only=syntax_only,
            quality=False,
        )

    def assert_invalid(self, text: str, code: int = 1, *, syntax_only: bool = True) -> None:
        self.write_document(text)
        with self.assertRaises(validate_mod.ValidationError) as caught:
            self.validate(syntax_only=syntax_only)
        self.assertEqual(caught.exception.code, code)


class StructureAndDeclarationTests(FixtureCase):
    def test_valid_unknown_technology_and_renamed_titles(self) -> None:
        result = self.validate()
        self.assertEqual(result.frontmatter.source_repository, self.source_repository)
        self.assertEqual(result.frontmatter.stack_slug, "runtime-unknowntech")
        self.assertEqual(result.evidence_count, 0)

    def test_navigation_metadata_roles_responsibilities_and_separators_are_required(self) -> None:
        original = self.candidate.read_text(encoding="utf-8")
        variants = (
            ("toc", original.replace("## 目次\n", "", 1)),
            ("fake-heading", original.replace("### Part 1\n", "### 1. 目次内の偽見出し\n### Part 1\n", 1)),
            ("role", original.replace("（どう動かす）", "", 1)),
            ("separator", original.replace("\n---\n\n### 2.", "\n\n### 2.", 1)),
            ("title", original.replace('title: "Fixture design"\n', "", 1)),
            ("date", original.replace('generated_at: "2026-10-30"\n', "", 1)),
            ("date-json", original.replace('generated_at: "2026-10-30"', "generated_at: 2026-10-30", 1)),
            ("toc-target", original.replace("](#1-任意の節題1)", "](#1-不一致)", 1)),
        )
        for label, text in variants:
            with self.subTest(label=label):
                self.assert_invalid(text)

    def test_part_and_section_missing_duplicate_and_order(self) -> None:
        original = self.candidate.read_text(encoding="utf-8")
        variants = (
            original.replace("## Part 2: 任意の章題（何を）\n", "", 1),
            original.replace("## Part 2: 任意の章題（何を）", "## Part 1: 重複（なぜ）", 1),
            original.replace("## Part 1: 任意の章題", "## Part X", 1),
            original.replace("### 6. 任意の節題6\n", "", 1),
            original.replace("### 6. 任意の節題6", "### 5. 重複", 1),
            original.replace("### 1. 任意の節題1", "### 2. 順序不正", 1),
        )
        for text in variants:
            with self.subTest(sample=text[:80]):
                self.assert_invalid(text)

    def test_appendix_is_rejected_in_every_form(self) -> None:
        original = self.candidate.read_text(encoding="utf-8")
        variants = (
            ("h2", original + "\n---\n\n## Appendix\n\nAppendix の本文。\n"),
            ("h3", original + "\n---\n\n### Appendix A: 比較\n\nAppendix A の本文。\n"),
            ("toc-link", original.replace("## 目次\n", "## 目次\n\n* [Appendix A: 比較](#appendix-a-比較)\n", 1)),
            ("toc-heading", original.replace("### Part 1\n", "### Appendix\n### Part 1\n", 1)),
        )
        for label, text in variants:
            with self.subTest(label=label):
                self.assert_invalid(text)

    def test_ledger_references_are_rejected(self) -> None:
        text = make_document(self.inspection, declarations={1: "evidence: tracked.txt を [E1] で参照する"})
        self.assert_invalid(text)

    def test_last_section_extends_to_end_of_document(self) -> None:
        text = self.candidate.read_text(encoding="utf-8") + "\n§24 の末尾に続く本文。\n"
        self.write_document(text)
        self.validate()

    def test_section_in_wrong_part_is_rejected(self) -> None:
        text = self.candidate.read_text(encoding="utf-8")
        heading = "### 9. 任意の節題9"
        body_start = text.index(heading)
        body_end = text.index("### 10.", body_start)
        block = text[body_start:body_end]
        text = text[:body_start] + text[body_end:]
        insert_at = text.index("## Part 3:")
        text = text[:insert_at] + block + text[insert_at:]
        self.assert_invalid(text)

    def test_declaration_forms_and_placeholders(self) -> None:
        accepted = (
            "説明だけ",
            "[要確認]: 実装から意図を確定できない",
            "該当なし: CI設定を探索したが存在しない",
        )
        for declaration in accepted:
            with self.subTest(declaration=declaration):
                self.write_document(make_document(self.inspection, declarations={1: declaration}))
                self.validate()
        rejected = ("", "[要確認]:", "[要確認]: TODO", "該当なし: <根拠>", "該当なし: ...")
        for declaration in rejected:
            with self.subTest(declaration=declaration):
                text = make_document(self.inspection, declarations={1: declaration})
                self.assert_invalid(text)

    def test_fenced_and_html_comment_declarations_are_ignored(self) -> None:
        declarations = {
            1: "```\n根拠トークンではない\n```\n説明だけ",
            2: "<!-- [要確認]: コメントだけ -->\n説明だけ",
        }
        self.write_document(make_document(self.inspection, declarations=declarations))
        self.validate()
        self.assert_invalid(make_document(self.inspection, declarations={1: "```\nevidence: tracked.txt\n```\n説明だけ"}))

    def test_fence_closes_only_with_plain_same_marker(self) -> None:
        declaration = (
            "```\n"
            "```not-a-close\n"
            "fence の内側\n"
            "```\n"
            "[要確認]: 正しい終端後の宣言"
        )
        self.write_document(make_document(self.inspection, declarations={1: declaration}))
        self.validate()


class Section9CompatibilityTests(FixtureCase):
    def assert_bad_section9(self, body: str) -> None:
        self.assert_invalid(make_document(self.inspection, section9_body=body))

    def test_note_zero_or_one_is_accepted(self) -> None:
        base = [
            "| レイヤ | 技術 | バージョン方針 | 備考 |",
            "| --- | --- | --- | --- |",
            "| Runtime | Mystery | — | 観測: fixture |",
        ]
        for notes in ([], ["> 観測できた事実"]):
            self.write_document(make_document(self.inspection, section9_body="\n".join(notes + base)))
            self.validate()

    def test_separator_after_section9_table_is_a_boundary(self) -> None:
        self.write_document(
            make_document(
                self.inspection,
                section9_body="\n".join(
                    [
                        "| レイヤ | 技術 | バージョン方針 | 備考 |",
                        "| --- | --- | --- | --- |",
                        "| Runtime | Mystery | — | 観測: fixture |",
                    ]
                ),
            )
        )
        self.validate()

    def test_invalid_table_shapes_and_policy(self) -> None:
        bad_bodies = (
            "| レイヤ | 技術 | バージョン方針 |\n| --- | --- | --- |\n| A | B | — |",
            "| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |",
            "| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |\n| A | B | 1.x | evidence: tracked.txt |",
            "| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |\n| Aレイヤ | B | — | evidence: tracked.txt |",
            "| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |\n| A | B | 観測: 1 | evidence: tracked.txt |",
            '| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |\n| A | B | — | "x\'y"; evidence: tracked.txt |',
            "| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |\n| A | B\\|C | — | evidence: tracked.txt |",
            "> note 1\n> note 2\n| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |\n| A | B | — | evidence: tracked.txt |",
            "| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |\ntext\n| A | B | — | evidence: tracked.txt |",
            "| レイヤ | 技術 | バージョン方針 | 備考 |\n| --- | --- | --- | --- |\n| A | B | — | evidence: tracked.txt |\n### hidden",
        )
        for body in bad_bodies:
            with self.subTest(body=body):
                self.assert_bad_section9(body)

    def test_fenced_numbered_heading_anywhere_is_rejected(self) -> None:
        body = (
            "```\n### 9. fake\n```\n"
            "| レイヤ | 技術 | バージョン方針 | 備考 |\n"
            "| --- | --- | --- | --- |\n"
            "| A | B | — | evidence: tracked.txt |"
        )
        self.assert_bad_section9(body)


class EvidenceContractTests(FixtureCase):
    def document_with_section1(self, declaration: str) -> str:
        return make_document(self.inspection, declarations={1: declaration})

    def test_token_terminators_and_fragments(self) -> None:
        rejected = (
            "evidence: tracked.txt 説明",
            "evidence: tracked.txt; 説明",
            "evidence: tracked.txt, 説明",
            "evidence: tracked.txt) 説明",
            "evidence: tracked.txt| 説明",
            "evidence: `tracked.txt` 説明",
            "evidence: tracked.txt#L1",
            "evidence: tracked.txt#L1-L99",
            "evidence: tracked.txt#anchor",
            "evidence: tracked.txt#Lx",
            "evidence: `tracked.txt",
            "evidence:",
            "evidence: tracked.txt\\bad",
        )
        for declaration in rejected:
            with self.subTest(declaration=declaration):
                self.assert_invalid(self.document_with_section1(declaration))

    def test_tracked_exact_names_non_ascii_and_pathspec_magic(self) -> None:
        for name in ("*", ":(top)", "証跡.txt"):
            (self.repo / name).write_text(name, encoding="utf-8")
        commit(self.repo, "pathspec names")
        self.inspection = inspect_mod.inspect_repository(os.fspath(self.repo))
        for name in ("*", "証跡.txt"):
            with self.subTest(name=name):
                self.assert_invalid(self.document_with_section1(f"evidence: `{name}`"))
        # `)` は v1 token の終端なので文書には書けないが、tracked 判定自体が
        # pathspec を渡さない完全一致 set であることは内部契約を直接固定する。
        tracked = validate_mod._tracked_files(self.repo)
        validate_mod._validate_evidence_files(
            [validate_mod.Evidence(":(top)", None, 1)],
            self.repo,
            tracked,
        )

    def test_missing_absolute_parent_directory_untracked_and_excluded(self) -> None:
        (self.repo / "untracked.txt").write_text("x", encoding="utf-8")
        (self.repo / ".env").write_text("SECRET=x", encoding="utf-8")
        directory = self.repo / "folder"
        directory.mkdir()
        cases = (
            "missing.txt",
            "/etc/hosts",
            "../tracked.txt",
            "folder",
            "untracked.txt",
            ".env",
        )
        for value in cases:
            with self.subTest(value=value):
                self.assert_invalid(
                    self.document_with_section1(f"evidence: `{value}`"),
                    syntax_only=False,
                )

    def test_symlink_evidence_is_rejected(self) -> None:
        link = self.repo / "linked.txt"
        link.symlink_to("tracked.txt")
        commit(self.repo, "symlink")
        self.inspection = inspect_mod.inspect_repository(os.fspath(self.repo))
        self.assert_invalid(
            self.document_with_section1("evidence: linked.txt"),
            syntax_only=False,
        )

    def test_intermediate_symlink_evidence_is_rejected(self) -> None:
        external = self.base / "external-evidence"
        external.mkdir()
        (external / "nested.txt").write_text("outside\n", encoding="utf-8")
        (self.repo / "linked-dir").symlink_to(external, target_is_directory=True)
        with self.assertRaises(validate_mod.ValidationError):
            validate_mod._validate_evidence_files(
                [validate_mod.Evidence("linked-dir/nested.txt", None, 1)],
                self.repo,
                {"linked-dir/nested.txt"},
            )

    def test_ignored_file_is_rejected(self) -> None:
        (self.repo / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
        commit(self.repo, "ignore fixture")
        ignored = self.repo / "secret.ignored"
        ignored.write_text("ignored\n", encoding="utf-8")
        self.assertEqual(git(self.repo, "check-ignore", "secret.ignored").strip(), b"secret.ignored")
        self.inspection = inspect_mod.inspect_repository(os.fspath(self.repo))
        self.assert_invalid(
            self.document_with_section1("evidence: secret.ignored"),
            syntax_only=False,
        )

    def test_validator_sanitizes_git_environment_and_fsmonitor(self) -> None:
        marker = self.base / "validator-fsmonitor-ran"
        monitor = self.base / "validator-fsmonitor"
        monitor.write_text(
            "#!/bin/sh\n"
            f"printf invoked > {os.fspath(marker)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        monitor.chmod(0o700)
        git(self.repo, "config", "core.fsmonitor", os.fspath(monitor))
        malicious_config = self.base / "validator-malicious.gitconfig"
        malicious_config.write_text(
            "[remote \"origin\"]\n"
            "  url = https://github.com/attacker/redirected\n",
            encoding="utf-8",
        )
        missing = os.fspath(self.base / "redirected")
        with mock.patch.dict(
            os.environ,
            {
                "GIT_DIR": missing,
                "GIT_WORK_TREE": missing,
                "GIT_OBJECT_DIRECTORY": missing,
                "GIT_CONFIG": os.fspath(malicious_config),
            },
        ):
            self.validate()
        self.assertFalse(marker.exists())

    def test_source_root_required_except_syntax_only(self) -> None:
        with self.assertRaises(validate_mod.ValidationError) as caught:
            validate_mod.validate_document(os.fspath(self.candidate), quality=False)
        self.assertEqual(caught.exception.code, 2)
        result = validate_mod.validate_document(os.fspath(self.candidate), syntax_only=True, quality=False)
        self.assertIsNone(result.inspection)

    def test_exclusion_lists_match_reference(self) -> None:
        reference = (SKILL_DIR / "references" / "evidence-signals.md").read_text(encoding="utf-8")
        expected = {
            "EXCLUDED_DIR_NAMES": set(validate_mod.EXCLUDED_DIR_NAMES),
            "EXCLUDED_FILE_NAMES": set(validate_mod.EXCLUDED_FILE_NAMES),
            "EXCLUDED_FILE_PREFIXES": set(validate_mod.EXCLUDED_FILE_PREFIXES),
            "EXCLUDED_SUFFIXES": set(validate_mod.EXCLUDED_SUFFIXES),
            "BINARY_EXTENSIONS": set(validate_mod.BINARY_EXTENSIONS),
        }
        for label, values in expected.items():
            match = re.search(
                rf"`{label}`:\n\n```text\n(?P<body>.*?)\n```",
                reference,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match, label)
            self.assertEqual(set(match.group("body").splitlines()), values, label)


class ProvenanceFrontmatterAndLeakTests(FixtureCase):
    def test_dirty_and_head_move_are_exit_one(self) -> None:
        (self.repo / "dirty.txt").write_text("dirty", encoding="utf-8")
        with self.assertRaises(validate_mod.ValidationError) as dirty:
            self.validate()
        self.assertEqual(dirty.exception.code, 1)
        (self.repo / "dirty.txt").unlink()
        (self.repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
        commit(self.repo, "move head")
        with self.assertRaises(validate_mod.ValidationError) as moved:
            self.validate()
        self.assertEqual(moved.exception.code, 1)

    def test_origin_change_is_exit_one(self) -> None:
        git(self.repo, "remote", "set-url", "origin", "https://github.com/Other/Repository.git")
        with self.assertRaises(validate_mod.ValidationError) as moved:
            self.validate()
        self.assertEqual(moved.exception.code, 1)

    def test_json_frontmatter_special_characters(self) -> None:
        special = '-ref:#"\\\'日本語😀'
        frontmatter = "\n".join(
            [
                "---",
                "status: reverse-draft",
                'title: "Fixture design"',
                'generated_at: "2026-10-30"',
                f"source_repository: {json.dumps(self.source_repository, ensure_ascii=False)}",
                f"source_ref: {json.dumps(special, ensure_ascii=False)}",
                f"source_revision: {json.dumps('a' * 40)}",
                'stack_slug: "runtime-unknowntech"',
                "---",
            ]
        )
        text = make_document(self.inspection)
        text = frontmatter + text[text.index("\n# Fixture design") :]
        self.write_document(text)
        result = self.validate(syntax_only=True)
        self.assertEqual(result.frontmatter.source_ref, special)
        self.assertNotIn("\\ud83d", text.lower())

    def test_frontmatter_missing_duplicate_and_non_json(self) -> None:
        original = self.candidate.read_text(encoding="utf-8")
        variants = (
            original.replace("status: reverse-draft\n", "", 1),
            original.replace("status: reverse-draft", "status: reverse-draft\nstatus: reverse-draft", 1),
            original.replace('stack_slug: "runtime-unknowntech"\n', "", 1),
            original.replace(
                'stack_slug: "runtime-unknowntech"',
                'stack_slug: "runtime-unknowntech"\nstack_slug: "duplicate"',
                1,
            ),
            original.replace(
                f"source_ref: {json.dumps(self.inspection.source_ref)}",
                "source_ref: main",
                1,
            ),
            original.replace('stack_slug: "runtime-unknowntech"', "stack_slug: runtime-unknowntech", 1),
            original.replace(self.inspection.source_revision, "short", 1),
        )
        for text in variants:
            self.assert_invalid(text)

    def test_stack_slug_format_and_length(self) -> None:
        accepted = ("a", "python-fastapi-postgresql", "stack2-runtime3")
        for slug in accepted:
            with self.subTest(slug=slug):
                self.write_document(make_document(self.inspection, stack_slug=slug))
                self.validate()
        rejected = (
            "",
            "Python-fastapi",
            "-python",
            "python-",
            "python--fastapi",
            "../escape",
            "python_fastapi",
            "あ",
            "a" * 64,
        )
        for slug in rejected:
            with self.subTest(slug=slug):
                self.assert_invalid(make_document(self.inspection, stack_slug=slug))

    def test_uppercase_source_revision_is_rejected(self) -> None:
        text = self.candidate.read_text(encoding="utf-8").replace(
            self.inspection.source_revision,
            "A" * 40,
            1,
        )
        self.assert_invalid(text)

    def test_non_inclusion_rejects_sensitive_forms_and_allows_api_path(self) -> None:
        allowed = make_document(
            self.inspection,
            declarations={1: f"[要確認]: /api/v1 と {self.source_repository} は許容"},
        )
        self.write_document(allowed)
        self.validate()
        forbidden = (
            os.fspath(self.repo),
            os.path.realpath(self.repo),
            os.path.expanduser("~"),
            "git@github.com:Owner/Repo.git",
            "ssh://git@github.com/Owner/Repo.git",
            "https://user:password@github.com/Owner/Repo",
            "ghp_secret",
            "github_pat_secret",
            "AKIAEXAMPLE",
            "-----BEGIN PRIVATE KEY-----",
        )
        for value in forbidden:
            if value == "/":
                continue
            with self.subTest(value=value):
                text = make_document(self.inspection, declarations={1: f"[要確認]: {value}"})
                self.assert_invalid(text, syntax_only=False)


class PublishTests(FixtureCase):
    published_at = datetime.datetime(2026, 11, 1, 11, 44, 30)
    output_dir_name = "Repo-20261101114430"

    def setUp(self) -> None:
        super().setUp()
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.output = (
            self.workspace
            / "gen"
            / self.output_dir_name
            / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"
        )

    def publish(self, approve: bool = False, workspace: Path | None = None) -> Path:
        return publish_mod.publish_document(
            os.fspath(self.candidate),
            os.fspath(self.repo),
            workspace_root=os.fspath(workspace or self.workspace),
            approve_overwrite=approve,
            quality=False,
            published_at=self.published_at,
        )

    def test_atomic_publish_and_approved_replace(self) -> None:
        output = self.publish()
        self.assertEqual(output, self.output)
        first = output.read_bytes()
        text = self.candidate.read_text(encoding="utf-8").replace(
            "[要確認]: fixtureで未確定",
            "該当なし: fixtureで対象なし",
            1,
        )
        self.write_document(text)
        with self.assertRaises(publish_mod.PublishError) as unapproved:
            self.publish()
        self.assertEqual(unapproved.exception.code, 1)
        self.assertEqual(output.read_bytes(), first)
        self.publish(approve=True)
        self.assertNotEqual(output.read_bytes(), first)

    def test_publish_uses_repository_and_timestamp_not_stack_slug(self) -> None:
        self.write_document(make_document(self.inspection, stack_slug="python-fastapi-postgresql"))
        output = self.publish()
        self.assertEqual(output, self.output)
        self.assertTrue(output.is_file())
        self.assertNotIn("python-fastapi-postgresql", output.parts)

    def test_invalid_candidate_and_head_move_preserve_existing(self) -> None:
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"existing")
        self.write_document(self.candidate.read_text(encoding="utf-8").replace("## Part 2:", "## Missing:"))
        with self.assertRaises(publish_mod.PublishError):
            self.publish(approve=True)
        self.assertEqual(self.output.read_bytes(), b"existing")
        self.write_document(make_document(self.inspection))
        (self.repo / "new.txt").write_text("new", encoding="utf-8")
        commit(self.repo, "head moved")
        with self.assertRaises(publish_mod.PublishError) as moved:
            self.publish(approve=True)
        self.assertEqual(moved.exception.code, 1)
        self.assertEqual(self.output.read_bytes(), b"existing")

    def test_symlink_output_path_and_candidate_under_gen_are_rejected(self) -> None:
        external = self.base / "external"
        external.mkdir()
        (self.workspace / "gen").symlink_to(external, target_is_directory=True)
        with self.assertRaises(publish_mod.PublishError) as symlink:
            self.publish()
        self.assertEqual(symlink.exception.code, 2)

        (self.workspace / "gen").unlink()
        under_gen = self.workspace / "gen" / "candidate.md"
        under_gen.parent.mkdir()
        under_gen.write_bytes(self.candidate.read_bytes())
        with self.assertRaises(publish_mod.PublishError) as nested:
            publish_mod.publish_document(
                os.fspath(under_gen),
                os.fspath(self.repo),
                workspace_root=os.fspath(self.workspace),
                quality=False,
            )
        self.assertEqual(nested.exception.code, 2)

    def test_output_directory_and_output_file_symlinks_are_rejected(self) -> None:
        external = self.base / "external"
        external.mkdir()

        directory_workspace = self.base / "directory-link-workspace"
        (directory_workspace / "gen").mkdir(parents=True)
        (directory_workspace / "gen" / self.output_dir_name).symlink_to(
            external,
            target_is_directory=True,
        )
        with self.assertRaises(publish_mod.PublishError) as directory_link:
            self.publish(workspace=directory_workspace)
        self.assertEqual(directory_link.exception.code, 2)

        file_workspace = self.base / "file-link-workspace"
        output_dir = file_workspace / "gen" / self.output_dir_name
        output_dir.mkdir(parents=True)
        target = external / "existing.md"
        target.write_bytes(b"protected")
        (output_dir / "TECHNOLOGY_STACK_UNIFIED_DESIGN.md").symlink_to(target)
        with self.assertRaises(publish_mod.PublishError) as file_link:
            self.publish(approve=True, workspace=file_workspace)
        self.assertEqual(file_link.exception.code, 2)
        self.assertEqual(target.read_bytes(), b"protected")

    def test_candidate_snapshot_is_validated_and_published_without_reread(self) -> None:
        original = self.candidate.read_bytes()
        original_validate = publish_mod.validate_bytes

        def mutate_after_snapshot(data: bytes, **kwargs: object) -> validate_mod.ValidationResult:
            self.candidate.write_bytes(b"invalid replacement")
            return original_validate(data, **kwargs)

        with mock.patch.object(publish_mod, "validate_bytes", side_effect=mutate_after_snapshot):
            self.publish()
        self.assertEqual(self.output.read_bytes(), original)
        self.assertNotEqual(self.candidate.read_bytes(), original)

    def test_missing_and_non_utf8_candidate_are_exit_two(self) -> None:
        self.candidate.unlink()
        with self.assertRaises(publish_mod.PublishError) as missing:
            self.publish()
        self.assertEqual(missing.exception.code, 2)
        self.candidate.write_bytes(b"\xff\xfe")
        with self.assertRaises(publish_mod.PublishError) as non_utf8:
            self.publish()
        self.assertEqual(non_utf8.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_candidate_and_workspace_symlinks_are_rejected(self) -> None:
        real_candidate = self.candidate
        candidate_link = self.base / "candidate-link.md"
        candidate_link.symlink_to(real_candidate)
        self.candidate = candidate_link
        with self.assertRaises(publish_mod.PublishError) as candidate_error:
            self.publish()
        self.assertEqual(candidate_error.exception.code, 2)
        self.candidate = real_candidate

        real_workspace = self.base / "real-workspace"
        real_workspace.mkdir()
        workspace_link = self.base / "workspace-link"
        workspace_link.symlink_to(real_workspace, target_is_directory=True)
        with self.assertRaises(publish_mod.PublishError) as workspace_error:
            self.publish(workspace=workspace_link)
        self.assertEqual(workspace_error.exception.code, 2)

    def test_unapproved_create_race_preserves_competing_file(self) -> None:
        original_link = os.link

        def create_competing_file(*args: object, **kwargs: object) -> None:
            self.output.write_bytes(b"competitor")
            original_link(*args, **kwargs)

        with mock.patch.object(publish_mod.os, "link", side_effect=create_competing_file):
            with self.assertRaises(publish_mod.PublishError) as raced:
                self.publish()
        self.assertEqual(raced.exception.code, 1)
        self.assertEqual(self.output.read_bytes(), b"competitor")

    def test_success_stdout_uses_workspace_relative_path(self) -> None:
        output = io.StringIO()
        legacy = lambda data, **kw: validate_mod.validate_bytes(data, **{**kw, "quality": False})  # noqa: E731
        with mock.patch.object(publish_mod, "validate_bytes", legacy), contextlib.redirect_stdout(output):
            exit_code = publish_mod.main(
                [
                    "--candidate",
                    os.fspath(self.candidate),
                    "--source-root",
                    os.fspath(self.repo),
                    "--workspace-root",
                    os.fspath(self.workspace),
                ]
            )
        self.assertEqual(exit_code, 0)
        pass_line = next(line for line in output.getvalue().splitlines() if " PASS: " in line)
        self.assertRegex(
            pass_line,
            r"^\[publish_design_doc\] PASS: gen/Repo-\d{14}/TECHNOLOGY_STACK_UNIFIED_DESIGN\.md$",
        )
        self.assertNotIn(os.fspath(self.workspace), pass_line)

    def test_review_counts_use_effective_masked_lines(self) -> None:
        text = make_document(self.inspection)
        text += (
            "\n宣言: 有効1\n"
            "宣言: 有効2 宣言: 同じ行では一件\n"
            "```\n宣言: 無効\n[要確認]\n該当なし: 無効\nevidence: ignored.txt\n```\n"
            "<!-- 宣言: 無効 [要確認] 該当なし: 無効 evidence: ignored.txt -->\n"
        )
        self.assertEqual(publish_mod.review_counts(text), (2, 24, 0, 0))


class RuntimeContractTests(unittest.TestCase):
    def test_expected_url_input_is_absent_from_public_contract(self) -> None:
        paths = (
            SKILL_DIR / "SKILL.md",
            HERE / "inspect_local_repository.py",
            HERE / "validate_design_doc.py",
            HERE / "publish_design_doc.py",
        )
        for path in paths:
            self.assertNotIn("--expected-url", path.read_text(encoding="utf-8"), path.name)
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("gen/<repository>-<yyyyMMddHHmmss>/TECHNOLOGY_STACK_UNIFIED_DESIGN.md", skill)

    def test_document_skeleton_has_questions_for_sections_10_through_23(self) -> None:
        skeleton = (SKILL_DIR / "references" / "document-skeleton.md").read_text(encoding="utf-8")
        for section in range(10, 24):
            match = re.search(
                rf"^### {section}\..*?\n(?P<body>.*?)(?=^### |\Z)",
                skeleton,
                flags=re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(match, f"§{section}")
            self.assertIn("？", match.group("body"), f"§{section}")

    def test_python39_syntax_and_future_import(self) -> None:
        scripts = sorted(HERE.glob("*.py"))
        self.assertEqual(
            {path.name for path in scripts},
            {
                "assemble_candidate.py",
                "document_quality.py",
                "inspect_local_repository.py",
                "publish_design_doc.py",
                "survey_repository.py",
                "test_document_quality.py",
                "test_inspect_local_repository.py",
                "test_validate_technology_stack_design.py",
                "validate_design_doc.py",
            },
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
            self.assertIn("annotations", future_names, path.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
