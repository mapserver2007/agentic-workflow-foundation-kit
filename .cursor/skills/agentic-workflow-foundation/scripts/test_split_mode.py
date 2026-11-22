#!/usr/bin/env python3
"""engine の `mode: split`（splitlib / generate / audit）を検査する。"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_SCRIPTS = HERE.parents[1] / "agentic-workflow-engine" / "scripts"
if str(ENGINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ENGINE_SCRIPTS))

import audit  # noqa: E402
import generate  # noqa: E402
import splitlib  # noqa: E402

SOURCE_REL = ".cursor/docs/BP.md"
MAX_BYTES = 600
MIN_BYTES = 120

MANIFEST = """\
marker_id: test-split
project:
  tech_stack_design_filename: "BP.md"
outputs:
  - path: "docs/stack/"
    mode: split
    template: "index.template"
    index_path: "docs/stack.md"
    source_dir: ".cursor/docs"
    source_key: "project.tech_stack_design_filename"
    max_bytes: 600
    min_bytes: 120
    placeholder_check:
      path: "docs/arch.md"
      heading: "束縛"
    required_sections:
      - "## タスク別"
  - path: "docs/arch.md"
    mode: seed
    template: "arch.template"
"""

INDEX_TEMPLATE = """\
# {{_split.title}}

## タスク別

{{#each _split.tasks}}
- {{this.name}}: {{this.starts}} / {{this.refs}} / {{this.files}}
{{/each}}

## 目次

{{#each _split.toc}}
- §{{this.num}} {{this.title}} {{this.file}} {{this.refs}}
{{/each}}

プレースホルダ: {{_split.placeholders_line}}
"""

ARCH_OK = "# arch\n\n## 束縛\n\n| `{{app}}` | x |\n| `{{module}}` | y |\n\n## 参照\n"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _filler(n: int) -> str:
    return "x" * n + "\n"


def blueprint(*, leaf_over_max: bool = False, bad_ref: bool = False, with_table: bool = True,
              extra_section: bool = False, range_ref: bool = False, unnumbered: bool = False,
              missing_ref_in_row: bool = False) -> str:
    parts = ["---\ntitle: Test BP\nversion: 0.1\nstatus: draft\n---\n\n"]
    parts.append("# Test BP\n\nintro text\n\n")
    parts.append("## 0. 表記\n\n" + _filler(60) + "\n")
    parts.append("### 0.1 プレースホルダ\n\n`{{app}}` と `{{module}}`。" + _filler(80) + "\n")
    if with_table:
        refs_for_2 = "—" if missing_ref_in_row else "§1"
        parts.append(
            "### 0.2 タスク別の必読節\n\n"
            "| タスク種別 | 必読節 | 参照先 |\n| --- | --- | --- |\n"
            "| 常時 | §0.1 | — |\n"
            f"| 構成の変更 | §2 | {refs_for_2} |\n"
            "| 規則の変更 | §3 | — |\n"
            "| 概要の確認 | §0.2, §1 | — |\n\n"
        )
    parts.append("## 1. 概要\n\n" + _filler(150) + "\n")
    parts.append("## 2. 構成\n\n概要は §1。" + _filler(20) + "\n")
    parts.append(
        "### 2.1 ツリー\n\n```text\n# fake heading inside a fence\n## still fake\n"
        "app/ # §1\n```\n" + _filler(300) + "\n"
    )
    parts.append("### 2.2 規則\n\n" + _filler(330) + ("参照: §9.9\n" if bad_ref else "") + "\n")
    parts.append("## 3. 規則\n\n" + _filler(40) + "\n")
    parts.append("### 3.1 小さい節 A\n\n" + _filler(30) + "\n")
    parts.append("### 3.2 小さい節 B\n\n" + _filler(30) + ("範囲: §3.1〜§3.2\n" if range_ref else "") + "\n")
    parts.append("#### 3.2.1 深い節\n\n" + _filler(40) + "\n")
    if leaf_over_max:
        parts.append("## 4. 大きい末端\n\n" + _filler(MAX_BYTES + 200) + "\n")
    if extra_section:
        parts.append("## 5. 追加された節\n\n" + _filler(200) + "\n")
    if unnumbered:
        parts.append("## 付録\n\n" + _filler(50) + "\n")
    return "".join(parts)


def _make_repo(root: Path, source: str, *, manifest: str = MANIFEST, arch: str | None = ARCH_OK,
               arch_template: str = "# arch\n") -> Path:
    skill_dir = root / ".cursor" / "skills" / "test-skill"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "templates").mkdir()
    (skill_dir / "manifest.yaml").write_text(manifest, encoding="utf-8")
    (skill_dir / "templates" / "index.template").write_text(INDEX_TEMPLATE, encoding="utf-8")
    (skill_dir / "templates" / "arch.template").write_text(arch_template, encoding="utf-8")
    (root / ".cursor" / "docs").mkdir(parents=True)
    (root / ".cursor" / "docs" / "BP.md").write_text(source, encoding="utf-8")
    (root / "docs").mkdir(exist_ok=True)
    if arch is not None:
        (root / "docs" / "arch.md").write_text(arch, encoding="utf-8")
    return skill_dir


def _quiet(func, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out):
        with contextlib.redirect_stderr(err):
            rc = func(*args, **kwargs)
    return rc, out.getvalue(), err.getvalue()


def _generate(skill_dir: Path, check: bool = False):
    return _quiet(generate.run, str(skill_dir), check)


def _audit(skill_dir: Path):
    return _quiet(audit.run, str(skill_dir))


def _build(source: str):
    return splitlib.build(source, SOURCE_REL, MAX_BYTES, MIN_BYTES)


def _fails(result) -> list:
    return [m for lv, m in result.problems if lv == splitlib.LEVEL_FAIL]


def _warns(result) -> list:
    return [m for lv, m in result.problems if lv == splitlib.LEVEL_WARN]


# --------------------------------------------------------------------------
def test_algorithm_concat_naming_and_fences() -> None:
    result = _build(blueprint())
    joined = "".join(splitlib.strip_header(result.files[n]) for n in result.order)
    _assert(joined == result.body, "連結が本文と一致しない")
    _assert(not result.body.startswith("---"), "frontmatter が本文に残っている")
    _assert(result.violations == [], f"想定外の違反: {result.violations}")
    for name in result.order:
        _assert(re.fullmatch(r"\d{2}_(s[0-9a-z\-]+|intro|x)\.md", name) is not None, f"ファイル名の書式: {name}")
        first = result.files[name].split("\n", 1)[0]
        _assert(splitlib.HEADER_RE.match(first) is not None, f"ヘッダ行の書式: {first!r}")
        _assert(len(splitlib.strip_header(result.files[name]).encode("utf-8")) <= MAX_BYTES, f"上限超過: {name}")
    # フェンスの中の見出し形式の行は、見出しとして扱わない（分割点にならず、目次にも出ない）
    titles = [t["title"] for t in result.ctx["toc"]]
    _assert(not any("fake" in t for t in titles), f"フェンス内の見出しが目次に出た: {titles}")
    _assert("# fake heading inside a fence" in result.body, "フェンス内の行が失われた")
    # 決定論: 同じ入力は同じ出力
    again = _build(blueprint())
    _assert(again.files == result.files and again.ctx == result.ctx, "同じ入力で出力が変わった")
    # プレースホルダの逐語保持と抽出
    _assert(result.placeholders == ["{{app}}", "{{module}}"], f"プレースホルダ: {result.placeholders}")
    _assert(any("{{app}}" in c for c in result.files.values()), "{{app}} が加工された")


def test_algorithm_merge_rules() -> None:
    result = _build(blueprint())
    # 小さい兄弟節（3.1 と 3.2）は結合される。親の本文が小さい 3 は先頭の子に結合される
    by_num = {t["num"]: t["file"] for t in result.ctx["toc"]}
    _assert(by_num["3"] == by_num["3.1"], f"小さい親は先頭の子と同じファイルにする: {by_num}")
    _assert(by_num["3.1"] == by_num["3.2"], f"小さい兄弟は結合する: {by_num}")
    # 上限を超える親（2）は、子（2.1、2.2）に分かれる
    _assert(by_num["2.1"] != by_num["2.2"], f"上限を超える親は子で分ける: {by_num}")
    # 先頭ファイルの slug
    _assert(result.order[0].startswith("01_s0"), f"先頭ファイル名: {result.order[0]}")


def test_algorithm_section_changes_keep_invariants() -> None:
    base = _build(blueprint())
    more = _build(blueprint(extra_section=True))
    _assert(len(more.files) >= len(base.files), "節を足してファイル数が減った")
    for result in (base, more):
        joined = "".join(splitlib.strip_header(result.files[n]) for n in result.order)
        _assert(joined == result.body, "節の増減後に連結が一致しない")
        _assert(not result.violations, f"節の増減後の違反: {result.violations}")
    nums = [t["num"] for t in more.ctx["toc"]]
    _assert("5" in nums and "5" not in [t["num"] for t in base.ctx["toc"]], "追加した節が目次に反映されない")


def test_format_contract_problems() -> None:
    _assert(_fails(_build(blueprint())) == [], f"基準の入力に失敗がある: {_fails(_build(blueprint()))}")
    _assert(_warns(_build(blueprint())) == [], f"基準の入力に警告がある: {_warns(_build(blueprint()))}")
    over = _build(blueprint(leaf_over_max=True))
    _assert(over.violations and over.violations[0][2] == "leaf_over_max", f"上限超過の末端節: {over.violations}")
    _assert(any("サイズ上限" in m for m in _fails(over)), "上限超過が失敗にならない")
    bad = _build(blueprint(bad_ref=True))
    _assert(any("§9.9" in m for m in _fails(bad)), f"参照切れ: {_fails(bad)}")
    no_table = _build(blueprint(with_table=False))
    _assert(any("索引表" in m for m in _fails(no_table)), "索引表の欠落が失敗にならない")
    rng = _build(blueprint(range_ref=True))
    _assert(any("範囲指定" in m for m in _warns(rng)), f"範囲指定の警告: {_warns(rng)}")
    unnumbered = _build(blueprint(unnumbered=True))
    _assert(any("節番号のない見出し" in m for m in _warns(unnumbered)), f"番号なし見出しの警告: {_warns(unnumbered)}")
    missing = _build(blueprint(missing_ref_in_row=True))
    _assert(any("参照先" in m and "§1" in m for m in _warns(missing)), f"参照先の欠落の警告: {_warns(missing)}")
    # 索引の行に属さないファイル（新設節の取りこぼし）
    extra = _build(blueprint(extra_section=True))
    _assert(any("どの索引行にも属さない" in m for m in _fails(extra)), f"取りこぼし: {_fails(extra)}")


def test_generate_audit_cycle() -> None:
    with tempfile.TemporaryDirectory(prefix="split-cycle-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint())
        rc, out, err = _generate(skill_dir)
        _assert(rc == 0, f"生成に失敗: {err}")
        stack = root / "docs" / "stack"
        names = sorted(p.name for p in stack.iterdir())
        _assert(len(names) >= 5, f"分割ファイルが少ない: {names}")
        _assert("{{app}}" in "".join((stack / n).read_text(encoding="utf-8") for n in names), "{{app}} が壊れた")
        index = (root / "docs" / "stack.md").read_text(encoding="utf-8")
        _assert("## タスク別" in index and "`{{app}}`" in index, "索引の内容")
        rc, out, err = _audit(skill_dir)
        _assert(rc == 0, f"audit が失敗: {out} {err}")
        rc, out, _ = _generate(skill_dir, check=True)
        _assert(rc == 0, f"生成直後の --check が差分あり: {out}")

        # 未変更の再生成は何も書かない
        past = 1_000_000_000
        for p in list(stack.iterdir()) + [root / "docs" / "stack.md"]:
            os.utime(p, (past, past))
        rc, out, _ = _generate(skill_dir)
        _assert(rc == 0, "再生成に失敗")
        _assert(all(p.stat().st_mtime_ns == past * 10**9 for p in stack.iterdir()), "未変更のファイルを書き換えた")

        # 分割ファイルの直接編集は drift
        target = stack / names[1]
        target.write_text(target.read_text(encoding="utf-8") + "edit\n", encoding="utf-8")
        _assert(_audit(skill_dir)[0] == 1, "直接編集が audit で失敗にならない")
        _assert(_generate(skill_dir, check=True)[0] == 1, "直接編集が --check で検知されない")
        _assert(_generate(skill_dir)[0] == 0, "再生成に失敗")
        _assert(_audit(skill_dir)[0] == 0, "再生成後に audit が失敗")

        # 残骸ファイルは audit で失敗、generate で削除される
        (stack / "99_stale.md").write_text("stale\n", encoding="utf-8")
        _assert(_audit(skill_dir)[0] == 1, "残骸が audit で失敗にならない")
        _assert(_generate(skill_dir, check=True)[0] == 1, "残骸が --check で検知されない")
        _assert(_generate(skill_dir)[0] == 0, "再生成に失敗")
        _assert(not (stack / "99_stale.md").exists(), "残骸が削除されない")

        # ファイル不在も再生成で直る
        (stack / names[2]).unlink()
        _assert(_audit(skill_dir)[0] == 1, "ファイル不在が audit で失敗にならない")
        _assert(_generate(skill_dir)[0] == 0 and (stack / names[2]).is_file(), "不在ファイルが再生成されない")

        # 索引の直接編集も drift
        (root / "docs" / "stack.md").write_text("edited\n", encoding="utf-8")
        _assert(_audit(skill_dir)[0] == 1, "索引の直接編集が audit で失敗にならない")
        _assert(_generate(skill_dir)[0] == 0 and _audit(skill_dir)[0] == 0, "索引が再生成されない")

        # 正本を小さくすると、不要になったファイルが削除される
        (root / ".cursor" / "docs" / "BP.md").write_text(
            "# Tiny\n\n## 0. 表記\n\n### 0.1 x\n\n`{{app}}` `{{module}}`\n\n### 0.2 y\n\n"
            "| タスク種別 | 必読節 | 参照先 |\n| --- | --- | --- |\n| 常時 | §0.1, §0.2 | — |\n",
            encoding="utf-8",
        )
        _assert(_generate(skill_dir)[0] == 0, "縮小後の再生成に失敗")
        left = sorted(p.name for p in stack.iterdir())
        _assert(len(left) < len(names), f"不要なファイルが残った: {left}")
        _assert(_audit(skill_dir)[0] == 0, "縮小後に audit が失敗")


def test_audit_detects_contract_violations() -> None:
    # プレースホルダの照合: 束縛節に記入欄がない
    with tempfile.TemporaryDirectory(prefix="split-ph-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint(), arch="# arch\n\n## 束縛\n\n| `{{app}}` | x |\n\n## 参照\n")
        _assert(_generate(skill_dir)[0] == 0, "生成に失敗")
        rc, out, _ = _audit(skill_dir)
        _assert(rc == 1 and "{{module}}" in out, f"記入欄の欠落が検知されない: {out}")
        (root / "docs" / "arch.md").write_text("# arch\n\n## 参照\n", encoding="utf-8")
        rc, out, _ = _audit(skill_dir)
        _assert(rc == 1 and "束縛節" in out, f"束縛節の欠落が検知されない: {out}")
        (root / "docs" / "arch.md").write_text(ARCH_OK, encoding="utf-8")
        _assert(_audit(skill_dir)[0] == 0, "復旧後に audit が失敗")
    # 上限を超える末端節: generate は書き出し、audit が失敗にする
    with tempfile.TemporaryDirectory(prefix="split-over-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint(leaf_over_max=True))
        rc, out, _ = _generate(skill_dir)
        _assert(rc == 0 and "サイズ上限" in out, f"generate が警告を出さない: {out}")
        rc, out, _ = _audit(skill_dir)
        _assert(rc == 1 and "サイズ上限" in out, f"audit が上限超過を検知しない: {out}")
    # 参照切れ
    with tempfile.TemporaryDirectory(prefix="split-ref-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint(bad_ref=True))
        _assert(_generate(skill_dir)[0] == 0, "生成に失敗")
        rc, out, _ = _audit(skill_dir)
        _assert(rc == 1 and "§9.9" in out, f"参照切れが検知されない: {out}")
    # 警告は PASS を妨げない
    with tempfile.TemporaryDirectory(prefix="split-warn-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint(range_ref=True))
        _assert(_generate(skill_dir)[0] == 0, "生成に失敗")
        rc, out, _ = _audit(skill_dir)
        _assert(rc == 0 and "WARN(split)" in out, f"警告だけなら PASS: {out}")


def test_seed_template_receives_split_context() -> None:
    """`_split` は全テンプレートに渡る。seed が正本のプレースホルダの記入欄を作り、追加時は audit が失敗にする。"""
    arch_template = (
        "# arch\n\n## 束縛\n\n"
        "{{#if _split.placeholders}}\n"
        "{{#each _split.placeholders}}\n"
        "| `{{this}}` | [TODO] |\n"
        "{{/each}}\n"
        "{{/if}}\n"
        "\n## 参照\n"
    )
    with tempfile.TemporaryDirectory(prefix="split-seed-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint(), arch=None, arch_template=arch_template)
        _assert(_generate(skill_dir)[0] == 0, "生成に失敗")
        arch = (root / "docs" / "arch.md").read_text(encoding="utf-8")
        _assert("| `{{app}}` | [TODO] |" in arch and "| `{{module}}` | [TODO] |" in arch, f"記入欄が作られない: {arch!r}")
        rc, out, _ = _audit(skill_dir)
        _assert(rc == 0, f"生成直後の audit が失敗: {out}")
        # 正本にプレースホルダを足すと、既存の seed は更新されず、audit が失敗にする（追従の契機）
        source = (root / ".cursor" / "docs" / "BP.md").read_text(encoding="utf-8")
        (root / ".cursor" / "docs" / "BP.md").write_text(
            source.replace("`{{app}}` と `{{module}}`。", "`{{app}}` と `{{module}}` と `{{extra}}`。"), encoding="utf-8"
        )
        _assert(_generate(skill_dir)[0] == 0, "再生成に失敗")
        _assert("{{extra}}" not in (root / "docs" / "arch.md").read_text(encoding="utf-8"), "既存の seed を書き換えた")
        rc, out, _ = _audit(skill_dir)
        _assert(rc == 1 and "{{extra}}" in out, f"プレースホルダの追加が検知されない: {out}")
    # `_split` が無い描画（split のエントリがない manifest）でも、テンプレートは失敗しない
    plain = "marker_id: plain\noutputs:\n  - path: \"docs/arch.md\"\n    mode: seed\n    template: \"arch.template\"\n"
    with tempfile.TemporaryDirectory(prefix="split-plain-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint(), manifest=plain, arch=None, arch_template=arch_template)
        _assert(_generate(skill_dir)[0] == 0, "split なしの描画に失敗")
        _assert("{{app}}" not in (root / "docs" / "arch.md").read_text(encoding="utf-8"), "split なしで記入欄が作られた")


def test_generate_safety_and_input_errors() -> None:
    # symlink が出力ディレクトリにあると、何も削除せず exit 2
    with tempfile.TemporaryDirectory(prefix="split-safe-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint())
        _assert(_generate(skill_dir)[0] == 0, "生成に失敗")
        stack = root / "docs" / "stack"
        outside = Path(temp_dir) / "outside.txt"
        outside.write_text("keep\n", encoding="utf-8")
        (stack / "98_link.md").symlink_to(outside)
        before = sorted(p.name for p in stack.iterdir())
        rc, _, err = _generate(skill_dir)
        _assert(rc == 2 and "symlink" in err, f"symlink を拒否しない: {err}")
        _assert(sorted(p.name for p in stack.iterdir()) == before, "拒否の前にファイルを変更した")
        _assert(outside.read_text(encoding="utf-8") == "keep\n", "symlink 先を変更した")
        _assert(_audit(skill_dir)[0] == 2, "audit も symlink を致命的エラーにする")
        (stack / "98_link.md").unlink()
        # 下位ディレクトリがあると、削除せず exit 2
        (stack / "sub").mkdir()
        (stack / "sub" / "keep.txt").write_text("keep\n", encoding="utf-8")
        rc, _, err = _generate(skill_dir)
        _assert(rc == 2 and "下位ディレクトリ" in err, f"下位ディレクトリを拒否しない: {err}")
        _assert((stack / "sub" / "keep.txt").is_file(), "下位ディレクトリの中身を削除した")
    # 設定・入力の不備は exit 2
    cases = {
        "path が浅い": MANIFEST.replace('path: "docs/stack/"', 'path: "stack/"'),
        "path に末尾 / がない": MANIFEST.replace('path: "docs/stack/"', 'path: "docs/stack"'),
        "index が出力ディレクトリの内側": MANIFEST.replace('index_path: "docs/stack.md"', 'index_path: "docs/stack/index.md"'),
        "上限が整数でない": MANIFEST.replace("max_bytes: 600", 'max_bytes: "600"'),
        "下限が上限以上": MANIFEST.replace("min_bytes: 120", "min_bytes: 900"),
        "source_key が解決できない": MANIFEST.replace("project.tech_stack_design_filename", "project.missing_key"),
        "二重の split": MANIFEST + '  - path: "docs/other/"\n    mode: split\n    template: "index.template"\n'
        '    index_path: "docs/other.md"\n    source_dir: ".cursor/docs"\n'
        '    source_key: "project.tech_stack_design_filename"\n    max_bytes: 600\n    min_bytes: 120\n',
    }
    for label, manifest in cases.items():
        with tempfile.TemporaryDirectory(prefix="split-bad-") as temp_dir:
            root = Path(temp_dir) / "repo"
            skill_dir = _make_repo(root, blueprint(), manifest=manifest)
            _assert(_generate(skill_dir)[0] == 2, f"generate が致命的エラーにならない: {label}")
            _assert(_audit(skill_dir)[0] == 2, f"audit が致命的エラーにならない: {label}")
    # 正本の不在、見出しなし
    with tempfile.TemporaryDirectory(prefix="split-nosrc-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, blueprint())
        (root / ".cursor" / "docs" / "BP.md").unlink()
        _assert(_generate(skill_dir)[0] == 2, "正本の不在が致命的エラーにならない")
    with tempfile.TemporaryDirectory(prefix="split-nohead-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill_dir = _make_repo(root, "見出しのない文章\n")
        _assert(_generate(skill_dir)[0] == 2, "見出しなしが致命的エラーにならない")


def main() -> int:
    tests = (
        ("algorithm: concat, naming, fences", test_algorithm_concat_naming_and_fences),
        ("algorithm: merge rules", test_algorithm_merge_rules),
        ("algorithm: section changes", test_algorithm_section_changes_keep_invariants),
        ("format contract problems", test_format_contract_problems),
        ("generate/audit cycle", test_generate_audit_cycle),
        ("audit detects violations", test_audit_detects_contract_violations),
        ("seed template receives split context", test_seed_template_receives_split_context),
        ("generate safety and input errors", test_generate_safety_and_input_errors),
    )
    for label, test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            print(f"[test_split_mode] FAIL: {label}: {exc}", file=sys.stderr)
            return 1
        print(f"[test_split_mode] PASS: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
