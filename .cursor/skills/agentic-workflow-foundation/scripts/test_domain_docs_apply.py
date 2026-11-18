#!/usr/bin/env python3
"""domain_docs_apply.py の状態表・所有権・fill-only・refresh・ロールバックを回帰検査する。"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ENGINE_DIR = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ENGINE_DIR))
import domain_docs_apply as da  # noqa: E402
import domain_docs_gate as gate  # noqa: E402
import generate  # noqa: E402
import genlib  # noqa: E402
import tech_contract as tc  # noqa: E402
from yaml_emitter import dump_yaml_text  # noqa: E402

DESIGN_DOC = """\
# Design

## 概要

目的を述べる。

## 業務フロー

### 1. 設置

設置の流れ。

```text
## fenced is not a heading
```

### 2. 注文 ###

注文の流れ。

## API設計

API の説明。
"""

# ER 図の既定の本文。実在のテーブル名（`主要テーブル/コレクション構成` の既定の本文）だけを使う。
DEFAULT_ER = "```mermaid\nerDiagram\n    items ||--o{ order_items : snapshot\n```"

# `run_cli` が `contract_guidance_texts` の代わりに返す、契約の guidance の本文。
GUIDANCE_TEXTS: list[str] = []

SPEC_FILES = [
    {
        "slug": "setup",
        "title": "設置",
        "summary": "設置する。",
        "evidence": "1. 設置",
        "body": "## 概要\n\n設置の概要。\n\n## 制約\n\n制約の本文。",
    },
    {
        "slug": "order",
        "title": "注文",
        "summary": "注文する。",
        "evidence": "2. 注文",
        "body": "## 概要\n\n注文の概要。",
    },
]


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect(exc_type: type, label: str, fn) -> Exception:
    try:
        fn()
    except exc_type as exc:
        return exc
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"{label}: expected {exc_type.__name__}, got {type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"{label}: {exc_type.__name__} was not raised")


# `_skeletons()` の manifest が宣言する契約節（api / data_model / workflow）の title と同じ集合。
TITLES = {
    "docs/api.md": frozenset({"proto-first"}),
    "docs/data-models.md": frozenset({"スキーマ適用"}),
    "docs/workflows.md": frozenset({"ローカル検証"}),
}


def _skeletons() -> dict[str, str]:
    manifest = {
        "domain_docs": {
            "primary_language": "Go",
            "framework": "gRPC",
            "architecture": "Clean",
            "api_style": "gRPC",
            "database": "MySQL",
            "api_sections": [{"title": "proto-first", "guidance": "kit 所有の節"}],
            "data_model_sections": [{"title": "スキーマ適用", "guidance": "kit 所有の節"}],
            "workflow_sections": [{"title": "ローカル検証", "guidance": "kit 所有の節"}],
        }
    }
    skeletons = {}
    for rel in da.OWNERSHIP:
        template = (da.TEMPLATES_DIR / f"{rel}.template").read_text(encoding="utf-8")
        skeletons[rel] = genlib.render(template, manifest)
    return skeletons


OLD_BLOCK = """\
design_doc:
  schema_version: 1
  source_path: "designs/docs/designdoc.md"
  source_fingerprint: "{fingerprint}"
  projection:
    spec:
      purpose:
        evidence: "概要"
        body: |-
          旧形式の本文。

          空行を含む。
  digest: "{digest}"
"""


def make_repo(
    base: Path,
    skeletons: dict[str, str],
    *,
    pin: str = "none",
    design: bool = True,
    docs: bool = True,
    name: str = "repo",
) -> Path:
    root = base / name
    root.mkdir(parents=True)
    doc = root / da.DESIGN_DOC_PATHS[0]
    if design:
        doc.parent.mkdir(parents=True)
        doc.write_text(DESIGN_DOC, encoding="utf-8")
    manifest = "project:\n  name: test\n"
    if pin == "fresh":
        fingerprint = tc.source_fingerprint(doc) if design else "1" * 64
        manifest += (
            "design_doc:\n"
            f"  source_path: \"{da.DESIGN_DOC_PATHS[0].as_posix()}\"\n"
            f"  source_fingerprint: \"{fingerprint}\"\n"
        )
    elif pin == "stale":
        manifest += (
            "design_doc:\n"
            f"  source_path: \"{da.DESIGN_DOC_PATHS[0].as_posix()}\"\n"
            f"  source_fingerprint: \"{'0' * 64}\"\n"
        )
    elif pin == "old":
        manifest += OLD_BLOCK.format(fingerprint=tc.source_fingerprint(doc), digest="a" * 64)
        manifest += "other_key: true\n"
    (root / "manifest.yaml").write_text(manifest, encoding="utf-8")
    if docs:
        for rel, text in skeletons.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return root


def targets_for(root: Path, skeletons: dict[str, str], *, refresh: bool = False) -> dict:
    return da.build_targets(root, root / "manifest.yaml", skeletons, refresh=refresh, titles=TITLES)


def make_result(
    targets: dict,
    spec_files: list[dict] | None = None,
    overrides: dict[tuple[str, str], str] | None = None,
) -> dict:
    spec_files = SPEC_FILES if spec_files is None else spec_files
    overrides = overrides or {}
    rows = "\n".join(
        f"- [{item['title']}]({item['slug']}.md) — {item['summary']}（根拠: `{item['evidence']}`）"
        for item in spec_files
    ) or "（なし）"
    features = "\n\n".join(
        f"### {item['title']}\n\n**詳細**: [{item['title']}](spec/{item['slug']}.md)"
        for item in spec_files
    ) or "（なし）"
    sections = []
    omissions = []
    for item in targets["files"]:
        for name in item["sections"]:
            key = (item["file"], name)
            if key in overrides and overrides[key] is None:
                # None を渡した節は、根拠が無いものとして見送る。
                omissions.append({"file": item["file"], "heading": name, "reason": "根拠が無い"})
                continue
            if key in overrides:
                body = overrides[key]
            elif key == (da.ER_FILE, "主要テーブル/コレクション構成"):
                body = "テーブルは items と order_items である。"
            elif key == (da.ER_FILE, da.ER_SECTION):
                body = DEFAULT_ER
            elif key == (da.README_PATH, "収録仕様"):
                body = rows
            elif key == (da.SPEC_PATH, "機能仕様"):
                body = features
            else:
                body = f"{name} の起案本文。\n\n### 詳細\n\n補足。"
            sections.append({"file": item["file"], "heading": name, "evidence": "概要", "body": body})
    result = {"sections": sections, "spec_files": [dict(item) for item in spec_files]}
    if omissions:
        result["omissions"] = omissions
    return result


def plan_for(root, skeletons, targets, result, *, refresh=False):
    return da.build_plan(
        root, root / "manifest.yaml", skeletons, targets, result, refresh=refresh, titles=TITLES
    )


def apply_fill(root, skeletons, spec_files=None, overrides=None):
    targets = targets_for(root, skeletons)
    plan = plan_for(root, skeletons, targets, make_result(targets, spec_files, overrides))
    da.commit(root, plan.writes)
    return targets, plan


def run_cli(root: Path, skeletons: dict[str, str], *args: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(da, "render_skeletons", return_value=skeletons), \
            patch.object(da, "contract_section_titles", return_value=TITLES), \
            patch.object(da, "contract_guidance_texts", side_effect=lambda _manifest: list(GUIDANCE_TEXTS)), \
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = da.main([args[0], "--manifest", str(root / "manifest.yaml"), *args[1:]])
    return code, stdout.getvalue(), stderr.getvalue()


def write_result(root: Path, result: dict) -> None:
    (root / "tmp").mkdir(exist_ok=True)
    (root / da.RESULT_RELATIVE).write_text(dump_yaml_text(result), encoding="utf-8")


def manifest_design_doc(root: Path):
    return genlib.load_manifest(str(root / "manifest.yaml")).get("design_doc")


# --------------------------------------------------------------------------
def test_state_table() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-state-") as temp_dir:
        base = Path(temp_dir)

        root = make_repo(base, skeletons, design=False, name="none")
        targets = targets_for(root, skeletons)
        _assert((targets["action"], targets["pin"]) == ("skip", "none"), "none/none must skip")

        root = make_repo(base, skeletons, design=False, pin="fresh", name="lost")
        _expect(da.FatalError, "none/pin", lambda: targets_for(root, skeletons))

        root = make_repo(base, skeletons, name="both")
        (root / da.DESIGN_DOC_PATHS[1]).write_text(DESIGN_DOC, encoding="utf-8")
        _expect(da.FatalError, "both docs", lambda: targets_for(root, skeletons))

        root = make_repo(base, skeletons, name="unpinned")
        targets = targets_for(root, skeletons)
        _assert((targets["action"], targets["pin"]) == ("fill", "unpinned"), "doc/unpinned must fill")
        names = {item["file"]: item["sections"] for item in targets["files"]}
        _assert("収録仕様" in names[da.README_PATH], "README section must be fillable")
        _assert("API 詳細" in names["docs/api.md"], "API 詳細 must be fillable")
        _assert("ER図・関係性" in names["docs/data-models.md"], "ER section must be fillable")
        _assert("参照" not in names["docs/api.md"], "kit-owned section listed")
        # 契約節は api / data-models / workflows の契約の配列だけが対象。architecture / spec は対象外。
        _assert("proto-first" in names["docs/api.md"], "api_sections placeholder must be fillable")
        _assert("スキーマ適用" in names["docs/data-models.md"], "data_model_sections must be fillable")
        _assert("ローカル検証" in names["docs/workflows.md"], "workflow_sections must be fillable")
        placeholders = {i["file"]: i.get("placeholders", []) for i in targets["files"]}
        _assert(placeholders == {
            "docs/spec.md": [], "docs/spec/README.md": [], "docs/architecture.md": [],
            "docs/api.md": ["proto-first"], "docs/data-models.md": ["スキーマ適用"],
            "docs/workflows.md": ["ローカル検証"],
        }, f"placeholders wrong: {placeholders}")
        # subagent は docs を読めないので、契約節の引用の本文を targets の guidance で渡す（`>` は除く）。
        guidance = {i["file"]: i.get("guidance", {}) for i in targets["files"]}
        _assert(guidance == {
            "docs/spec.md": {}, "docs/spec/README.md": {}, "docs/architecture.md": {},
            "docs/api.md": {"proto-first": "kit 所有の節"},
            "docs/data-models.md": {"スキーマ適用": "kit 所有の節"},
            "docs/workflows.md": {"ローカル検証": "kit 所有の節"},
        }, f"guidance wrong: {guidance}")

        root = make_repo(base, skeletons, pin="fresh", name="fresh-fill")
        _assert(targets_for(root, skeletons)["action"] == "fill", "fresh with skeleton must fill")

        root = make_repo(base, skeletons, pin="stale", name="stale")
        targets = targets_for(root, skeletons)
        _assert((targets["action"], targets["pin"]) == ("stale", "stale"), "stale must be reported")

        # すべて埋め済みなら skip。
        root = make_repo(base, skeletons, pin="fresh", name="filled")
        apply_fill(root, skeletons)
        targets = targets_for(root, skeletons)
        _assert(targets["action"] == "skip", f"filled docs must skip: {targets['action']}")
        refresh = targets_for(root, skeletons, refresh=True)
        _assert(refresh["action"] == "refresh", "refresh action missing")
        _expect(da.FatalError, "refresh unpinned", lambda: targets_for(
            make_repo(base, skeletons, name="refresh-unpinned"), skeletons, refresh=True))

        root = make_repo(base, skeletons, pin="fresh", name="bad-path")
        text = (root / "manifest.yaml").read_text(encoding="utf-8").replace(
            "designs/docs/designdoc.md", "designs/docs/other.md")
        (root / "manifest.yaml").write_text(text, encoding="utf-8")
        _expect(da.FatalError, "source_path mismatch", lambda: targets_for(root, skeletons))

        root = make_repo(base, skeletons, pin="fresh", name="bad-fp")
        text = (root / "manifest.yaml").read_text(encoding="utf-8")
        text = text.replace(tc.source_fingerprint(root / da.DESIGN_DOC_PATHS[0]), "xyz")
        (root / "manifest.yaml").write_text(text, encoding="utf-8")
        _expect(da.FatalError, "bad fingerprint", lambda: targets_for(root, skeletons))


def test_heading_names_trailing_hash_and_fence() -> None:
    with tempfile.TemporaryDirectory(prefix="domain-docs-headings-") as temp_dir:
        doc = Path(temp_dir) / "designdoc.md"
        doc.write_text(
            "# A\n\n## B ##\n\n### C#\n\n```md\n## fenced\n```\n\n~~~\n# tilde\n~~~\n",
            encoding="utf-8",
        )
        names = da.heading_names(doc)
        _assert("B" in names and "C#" in names, f"heading names wrong: {names}")
        _assert("fenced" not in names and "tilde" not in names, "fenced heading registered")


def test_pin_preserves_following_keys_and_migrates_old_format() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-pin-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons, pin="old")
        manifest = root / "manifest.yaml"
        raw = manifest.read_text(encoding="utf-8").replace(
            "other_key: true\n", "other_key: true\n# note: keep\nnested:\n  a: 1\n")
        manifest.write_text(raw, encoding="utf-8")
        code, out, err = run_cli(root, skeletons, "pin")
        _assert(code == 0, f"pin failed: {err}")
        loaded = genlib.load_manifest(str(manifest))
        _assert(
            loaded["design_doc"] == {
                "source_path": "designs/docs/designdoc.md",
                "source_fingerprint": tc.source_fingerprint(root / da.DESIGN_DOC_PATHS[0]),
            },
            f"old keys not dropped: {loaded['design_doc']}",
        )
        text = manifest.read_text(encoding="utf-8")
        _assert(text.endswith("other_key: true\n# note: keep\nnested:\n  a: 1\n"), f"following keys lost: {text!r}")
        _assert("projection" not in text and "approval" not in text, "old design_doc keys remain")
        before = manifest.read_bytes()
        _assert(run_cli(root, skeletons, "pin")[0] == 0, "second pin failed")
        _assert(manifest.read_bytes() == before, "pin is not idempotent")

        # design_doc が無い manifest には末尾へ追加する。
        plain = make_repo(Path(temp_dir), skeletons, name="plain")
        _assert(run_cli(plain, skeletons, "pin")[0] == 0, "pin on plain manifest failed")
        _assert(manifest_design_doc(plain)["source_path"] == "designs/docs/designdoc.md", "block not appended")


def test_ownership_matches_templates() -> None:
    skeletons = _skeletons()
    for rel, owned in da.OWNERSHIP.items():
        names = [da._heading_name(h) for h in generate.structural_headings(skeletons[rel])]
        for name in owned:
            _assert(name in names, f"{rel}: owned heading {name!r} is not in the template")
        _assert("参照" not in owned, f"{rel}: 参照 must stay kit-owned")
    data_models = [da._heading_name(h) for h in generate.structural_headings(skeletons["docs/data-models.md"])]
    _assert("ER図・関係性" in data_models and "ER図・関係性" in da.OWNERSHIP["docs/data-models.md"],
            "ER図・関係性 must be owned by domain-docs")
    for rel in ("docs/api.md", "docs/data-models.md", "docs/workflows.md"):
        text = skeletons[rel]
        _assert("[TODO]" in text, f"{rel}: skeleton lost its TODO markers")
    # 偽の図の雛形をテンプレートに持たない（omission 時に偽の図が残らない）。
    for rel, text in skeletons.items():
        _assert("```mermaid" not in text, f"{rel}: skeleton must not carry a sample diagram")
        for pattern, meaning in gate.SAMPLE_PATTERNS:
            _assert(pattern.search(text) is None, f"{rel}: skeleton carries {meaning}")


def test_fill_only_keeps_hand_edits() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-fill-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons)
        api = root / "docs/api.md"
        edited = skeletons["docs/api.md"].replace(
            "## エンドポイント一覧\n\n[TODO] 主要エンドポイントのパス・メソッド・概要を記述する。",
            "## エンドポイント一覧\n\n手で書いた一覧。",
        )
        _assert(edited != skeletons["docs/api.md"], "fixture edit did not apply")
        api.write_text(edited, encoding="utf-8")
        before_other = (root / "docs/architecture.md").read_text(encoding="utf-8")
        targets = targets_for(root, skeletons)
        _assert("エンドポイント一覧" not in {n for i in targets["files"] if i["file"] == "docs/api.md" for n in i["sections"]},
                "hand-edited section must not be a target")
        result = make_result(targets)
        # 手編集済みの節を結果に含めても書かれない（KEPT として報告される）。
        result["sections"].append({
            "file": "docs/api.md", "heading": "エンドポイント一覧", "evidence": "API設計", "body": "上書き候補",
        })
        plan = plan_for(root, skeletons, targets, result)
        _assert(any("KEPT: docs/api.md#エンドポイント一覧" in note for note in plan.notes), f"no KEPT note: {plan.notes}")
        da.commit(root, plan.writes)
        text = api.read_text(encoding="utf-8")
        _assert("手で書いた一覧。" in text and "上書き候補" not in text, "hand edit was overwritten")
        _assert("API設計概要 の起案本文。" in text, "skeleton section was not filled")
        _assert("## proto-first\n\n> kit 所有の節\n\nproto-first の起案本文。" in text, "placeholder quote lost or body missing")
        headings = generate.structural_headings(skeletons["docs/api.md"])
        _assert(generate.structural_headings(text) == headings, "structural headings changed")
        _assert("## 参照" in text, "kit-owned parts lost")
        # 契約節は api / data-models / workflows で、引用を残して `[TODO]` だけ置換される。
        _assert("[TODO]" not in text, "api.md must have no TODO left after fill")
        data_models_text = (root / "docs/data-models.md").read_text(encoding="utf-8")
        _assert("## スキーマ適用\n\n> kit 所有の節\n\nスキーマ適用 の起案本文。" in data_models_text,
                "data_model_sections placeholder must be filled")
        _assert("## ローカル検証\n\n> kit 所有の節\n\nローカル検証 の起案本文。" in (root / "docs/workflows.md").read_text(encoding="utf-8"),
                "workflow_sections placeholder must be filled")
        _assert("items ||--o{ order_items" in data_models_text and "ENTITY_A" not in data_models_text,
                "ER section must be filled from the table names")
        _assert((root / "docs/architecture.md").read_text(encoding="utf-8") != before_other, "architecture not filled")
        _assert((root / "docs/spec/setup.md").is_file() and (root / "docs/spec/order.md").is_file(), "spec files missing")
        spec_text = (root / "docs/spec/setup.md").read_text(encoding="utf-8")
        _assert(spec_text.startswith("# 設置\n") and "## 関連仕様" in spec_text, "spec file shape wrong")
        _assert(spec_text.count("## 概要") == 1, "spec body lost")
        pinned = manifest_design_doc(root)
        _assert(set(pinned) == {"source_path", "source_fingerprint"}, f"pin keys: {pinned}")
        _assert(targets_for(root, skeletons)["action"] == "skip", "filled repo must skip")
        # 再実行（結果が同じでも、埋め済みの節は変わらない）。
        before = {rel: (root / rel).read_bytes() for rel in da.OWNERSHIP}
        again = targets_for(root, skeletons)
        _assert(not any(item["sections"] for item in again["files"]), "fillable sections remain")
        _assert(all((root / rel).read_bytes() == data for rel, data in before.items()), "files changed on rerun")


def test_rejects_unowned_and_invalid_sections() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-invalid-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons)
        targets = targets_for(root, skeletons)

        def check(label: str, mutate, error=da.ApplyError) -> str:
            result = make_result(targets)
            mutate(result)
            exc = _expect(error, label, lambda: plan_for(root, skeletons, targets, result))
            return str(exc)

        def add(file: str, heading: str, body: str = "本文", evidence: str = "概要"):
            return lambda r: r["sections"].append(
                {"file": file, "heading": heading, "evidence": evidence, "body": body})

        check("ER section without diagram", add("docs/data-models.md", "ER図・関係性"))
        check("参照 section", add("docs/api.md", "参照"))
        check("contract section outside the owner file", add("docs/api.md", "スキーマ適用"))
        check("unknown file", add("docs/tech-stack.md", "技術スタック一覧とバージョン方針"))
        check("outside path", add("../outside.md", "x"))
        check("duplicate", lambda r: r["sections"].append(dict(r["sections"][0])))

        def replace_first(**changes):
            def mutate(result):
                result["sections"][0].update(changes)
            return mutate

        check("missing evidence heading", replace_first(evidence="存在しない見出し"))
        check("mustache", replace_first(body="本文 {{x}}"))
        check("todo marker", replace_first(body="[TODO] 本文"))
        check("image link", replace_first(body="![図](a.png)"))
        check("reference image", replace_first(body="![図][image]\n\n[image]: diagram.png"))
        check("collapsed image", replace_first(body="![図][]\n\n[図]: diagram.png"))
        check("shortcut image", replace_first(body="![図]\n\n[図]: diagram.png"))
        linked = make_result(targets)
        linked["sections"][0]["body"] = "本文。[詳細](https://example.test)\n\n[id]: https://example.test"
        plan_for(root, skeletons, targets, linked)
        check("er diagram", replace_first(body="```mermaid\nerDiagram\n  A ||--o{ B : has\n```"))
        check("empty body", replace_first(body="  "))
        check("multiline evidence", replace_first(evidence="概要\n業務フロー"))
        message = check("structural heading clash", replace_first(body="本文\n\n## 参照\n\n追加"))
        _assert("参照" in message, f"clash message: {message}")
        check("unknown key", lambda r: r["sections"][0].update({"extra": "x"}))
        check("missing key", lambda r: r["sections"][0].pop("body"))
        check("unknown top-level key", lambda r: r.update({"unknown": []}))
        check("unanswered target", lambda r: r["sections"].pop())

        def omit(result):
            first = result["sections"].pop(0)
            result.setdefault("omissions", []).append(
                {"file": first["file"], "heading": first["heading"], "reason": "根拠が無い"})
        result = make_result(targets)
        omit(result)
        plan = plan_for(root, skeletons, targets, result)
        _assert(plan.writes, "omission should still allow other sections")
        check("omission without reason", lambda r: (omit(r), r["omissions"][-1].update({"reason": ""})))
        check("omission and section duplicate", lambda r: r.update({"omissions": [
            {"file": r["sections"][0]["file"], "heading": r["sections"][0]["heading"], "reason": "x"}]}))
        check("omission of unowned", lambda r: r.update({"omissions": [
            {"file": "docs/api.md", "heading": "参照", "reason": "x"}]}))

        # 見出し構成が壊れた既存ファイルは書かない。
        broken = (root / "docs/architecture.md")
        broken.write_text(broken.read_text(encoding="utf-8").replace("## 依存関係方針", "## 依存"), encoding="utf-8")
        new_targets = targets_for(root, skeletons)
        _assert(any(i.get("mismatch") for i in new_targets["files"]), "mismatch not reported in targets")
        result = make_result(new_targets)
        result["sections"].append({
            "file": "docs/architecture.md", "heading": "システム全体構成", "evidence": "概要", "body": "本文"})
        _expect(da.ApplyError, "section mismatch", lambda: plan_for(root, skeletons, new_targets, result))


def test_contract_placeholders_fill_only() -> None:
    """契約節（api / data-models / workflows）だけが、引用を残して `[TODO]` だけ置換される。fill-only 限定。"""
    skeletons = _skeletons()

    # 検出は、そのファイルの契約の配列の title と一致する節だけ。ほかのファイルの title は効かない。
    for rel, expected in (
        ("docs/api.md", {"proto-first": "> kit 所有の節"}),
        ("docs/data-models.md", {"スキーマ適用": "> kit 所有の節"}),
        ("docs/workflows.md", {"ローカル検証": "> kit 所有の節"}),
    ):
        found = da.placeholder_quotes(rel, skeletons[rel], generate.structural_headings(skeletons[rel]), TITLES)
        _assert(found == expected, f"{rel}: placeholders wrong: {found}")
        _assert(not set(found) & set(da.OWNERSHIP[rel]) and "参照" not in found,
                f"{rel}: owned or kit-owned section detected as placeholder")
    # architecture / spec / README は契約節の対象外。title を渡しても対象にならない。
    every_title = frozenset().union(*TITLES.values())
    for rel in ("docs/spec.md", "docs/architecture.md", "docs/spec/README.md"):
        found = da.placeholder_quotes(
            rel, skeletons[rel], generate.structural_headings(skeletons[rel]),
            {rel: every_title})
        _assert(found == {}, f"{rel}: must have no placeholders: {found}")
    # 別のファイルの title では対象にならない。title が空なら対象は無い。
    for label, titles in (
        ("other file title", {"docs/api.md": frozenset({"スキーマ適用"})}),
        ("other title", {"docs/api.md": frozenset({"別の節"})}),
        ("empty titles", {}),
        ("none titles", None),
    ):
        found = da.placeholder_quotes(
            "docs/api.md", skeletons["docs/api.md"], generate.structural_headings(skeletons["docs/api.md"]), titles)
        _assert(found == {}, f"{label}: shape match alone must not be a placeholder: {found}")
    _assert(sum(len(names) for names in da.OWNERSHIP.values()) == 23, "ownership table size changed")

    with tempfile.TemporaryDirectory(prefix="domain-docs-placeholder-") as temp_dir:
        base = Path(temp_dir)

        # 引用は apply が器から復元する。body に引用を書く結果は拒否する。
        root = make_repo(base, skeletons, name="quote")
        targets = targets_for(root, skeletons)

        # title が契約に無ければ、器の形が一致しても targets に載らず、結果に含めても拒否される。
        untitled = da.build_targets(root, root / "manifest.yaml", skeletons, refresh=False, titles={})
        for rel, name in (("docs/api.md", "proto-first"), ("docs/data-models.md", "スキーマ適用"),
                          ("docs/workflows.md", "ローカル検証")):
            item = next(i for i in untitled["files"] if i["file"] == rel)
            _assert(name not in item["sections"] and "placeholders" not in item,
                    f"untitled shape must not be a target: {item}")
        result = make_result(targets)
        _expect(da.ApplyError, "untitled placeholder", lambda: da.build_plan(
            root, root / "manifest.yaml", skeletons, untitled, result, refresh=False, titles={}))

        def with_body(heading: str, body: str):
            def mutate(result):
                for section in result["sections"]:
                    if section["heading"] == heading:
                        section["body"] = body
            return mutate

        for heading in ("proto-first", "スキーマ適用", "ローカル検証"):
            for label, body in (
                ("leading blockquote", "> 別の引用\n\n本文"),
                ("kit quote repeated", "本文\n\n> kit 所有の節\n\n続き"),
            ):
                result = make_result(targets)
                with_body(heading, body)(result)
                _expect(da.ApplyError, f"{heading}: {label}", lambda: plan_for(root, skeletons, targets, result))

        # evidence: 契約節は固定値 `contract` を使える。所有権表の節では使えない。
        result = make_result(targets)
        for section in result["sections"]:
            if section["heading"] in ("proto-first", "スキーマ適用", "ローカル検証"):
                section["evidence"] = "contract"
        plan_for(root, skeletons, targets, result)
        owned_contract = make_result(targets)
        owned_contract["sections"][0]["evidence"] = "contract"
        _expect(da.ApplyError, "contract evidence on an owned section", lambda: plan_for(
            root, skeletons, targets, owned_contract))

        # 根拠が無いときは omission で見送れる。引用と `[TODO]` は器のまま残る。
        result = make_result(targets)
        result["sections"] = [s for s in result["sections"] if s["heading"] != "proto-first"]
        result.setdefault("omissions", []).append(
            {"file": "docs/api.md", "heading": "proto-first", "reason": "根拠が無い"})
        plan = plan_for(root, skeletons, targets, result)
        da.commit(root, plan.writes)
        text = (root / "docs/api.md").read_text(encoding="utf-8")
        _assert("## proto-first\n\n> kit 所有の節\n\n[TODO]" in text, "omitted placeholder must stay as skeleton")

        # 手で書いた契約節は対象にならず、結果に含めても上書きされない。
        root = make_repo(base, skeletons, name="hand")
        data_models = root / "docs/data-models.md"
        edited = skeletons["docs/data-models.md"].replace("> kit 所有の節\n\n[TODO]", "> kit 所有の節\n\n手書きの契約。")
        _assert(edited != skeletons["docs/data-models.md"], "fixture edit did not apply")
        data_models.write_text(edited, encoding="utf-8")
        targets = targets_for(root, skeletons)
        item = next(i for i in targets["files"] if i["file"] == "docs/data-models.md")
        _assert("スキーマ適用" not in item["sections"] and "placeholders" not in item,
                f"hand-edited placeholder must not be a target: {item}")
        result = make_result(targets)
        result["sections"].append(
            {"file": "docs/data-models.md", "heading": "スキーマ適用", "evidence": "概要", "body": "上書き候補"})
        plan = plan_for(root, skeletons, targets, result)
        _assert(any("KEPT: docs/data-models.md#スキーマ適用" in note for note in plan.notes), f"no KEPT note: {plan.notes}")
        da.commit(root, plan.writes)
        text = data_models.read_text(encoding="utf-8")
        _assert("手書きの契約。" in text and "上書き候補" not in text, "hand-edited placeholder was overwritten")

        # refresh では契約節を対象にせず、結果に含めても拒否する。引用付きの本文は refresh でも残る。
        root = make_repo(base, skeletons, pin="fresh", name="refresh")
        apply_fill(root, skeletons)
        filled = (root / "docs/api.md").read_text(encoding="utf-8")
        _assert("## proto-first\n\n> kit 所有の節\n\nproto-first の起案本文。" in filled, "fill did not write placeholder")
        refresh_targets = targets_for(root, skeletons, refresh=True)
        for rel, name in (("docs/api.md", "proto-first"), ("docs/data-models.md", "スキーマ適用"),
                          ("docs/workflows.md", "ローカル検証")):
            refresh_item = next(i for i in refresh_targets["files"] if i["file"] == rel)
            _assert(name not in refresh_item["sections"] and "placeholders" not in refresh_item,
                    f"refresh must not target placeholders: {refresh_item}")
            result = make_result(refresh_targets)
            result["sections"].append({"file": rel, "heading": name, "evidence": "概要", "body": "更新"})
            _expect(da.ApplyError, f"placeholder in refresh: {name}", lambda: plan_for(
                root, skeletons, refresh_targets, result, refresh=True))
        updated = make_result(refresh_targets, overrides={("docs/api.md", "API設計概要"): "更新後の概要。"})
        plan = plan_for(root, skeletons, refresh_targets, updated, refresh=True)
        refreshed = plan.writes["docs/api.md"].decode("utf-8")
        _assert("更新後の概要。" in refreshed, "refresh did not update the owned section")
        _assert("## proto-first\n\n> kit 所有の節\n\nproto-first の起案本文。" in refreshed,
                "refresh changed the placeholder section")


def test_spec_file_rules() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-specfiles-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons)
        targets = targets_for(root, skeletons)

        def check(label: str, spec_files: list[dict], overrides=None) -> None:
            _expect(da.ApplyError, label, lambda: plan_for(
                root, skeletons, targets, make_result(targets, spec_files, overrides)))

        def variant(**changes) -> list[dict]:
            items = [dict(item) for item in SPEC_FILES]
            items[0].update(changes)
            return items

        check("bad slug", variant(slug="../tablet"))
        check("upper slug", variant(slug="Setup"))
        check("reserved slug", variant(slug="readme"))
        check("duplicate slug", variant(slug="order"))
        check("evidence missing", variant(evidence="存在しない"))
        check("duplicate evidence", variant(evidence="2. 注文"))
        check("no overview", variant(body="## 前提\n\n本文"))
        check("related section", variant(body="## 概要\n\n本文\n\n## 関連仕様\n\n手書き"))
        check("h1 in body", variant(body="# 見出し\n\n## 概要\n\n本文"))
        check("mustache in title", variant(title="{{x}}"))
        check("multiline summary", variant(summary="a\nb"))
        check("todo in body", variant(body="## 概要\n\n[TODO]"))
        check("unknown key", variant(extra="x"))

        # 3者が一致しない結果は拒否する。
        check("readme without row", SPEC_FILES, {(da.README_PATH, "収録仕様"): "- [設置](setup.md) — 設置する。（根拠: `1. 設置`）"})
        check("readme without evidence", SPEC_FILES, {(da.README_PATH, "収録仕様"):
              "- [設置](setup.md) — 設置する。\n- [注文](order.md) — 注文する。（根拠: `2. 注文`）"})
        check("readme wrong evidence", SPEC_FILES, {(da.README_PATH, "収録仕様"):
              "- [設置](setup.md) — 設置する。（根拠: `概要`）\n- [注文](order.md) — 注文する。（根拠: `2. 注文`）"})
        check("spec without link", SPEC_FILES, {(da.SPEC_PATH, "機能仕様"): "### 設置\n\n**詳細**: [設置](spec/setup.md)"})
        check("readme extra row", SPEC_FILES, {(da.README_PATH, "収録仕様"):
              "- [設置](setup.md) — 設置する。（根拠: `1. 設置`）\n- [注文](order.md) — 注文する。（根拠: `2. 注文`）\n"
              "- [余分](extra.md) — なし。（根拠: `概要`）"})

        # 既存ファイルとの衝突・対応付け。
        apply_fill(root, skeletons)
        (root / "docs/spec/manual.md").write_text("# 手書き\n", encoding="utf-8")
        later = targets_for(root, skeletons, refresh=True)
        check_refresh = lambda label, spec, overrides=None: _expect(da.ApplyError, label, lambda: plan_for(  # noqa: E731
            root, skeletons, later, make_result(later, spec, overrides), refresh=True))
        check_refresh("hand-added file without row", SPEC_FILES)
        (root / "docs/spec/manual.md").unlink()
        later = targets_for(root, skeletons, refresh=True)
        rename = [dict(item) for item in SPEC_FILES]
        rename[0]["slug"] = "setup-renamed"
        _expect(da.ApplyError, "same evidence different slug", lambda: plan_for(
            root, skeletons, later, make_result(later, rename), refresh=True))
        conflict = [dict(item) for item in SPEC_FILES]
        conflict[0]["evidence"] = "概要"
        _expect(da.ApplyError, "same slug different evidence", lambda: plan_for(
            root, skeletons, later, make_result(later, conflict), refresh=True))

        # README の行が根拠見出しを持たない既存ファイルは、同じ slug を引き当てる。
        readme = root / da.README_PATH
        readme.write_text(readme.read_text(encoding="utf-8").replace("（根拠: `1. 設置`）", ""), encoding="utf-8")
        legacy = targets_for(root, skeletons, refresh=True)
        legacy_result = make_result(legacy, SPEC_FILES)
        for section in legacy_result["sections"]:
            if (section["file"], section["heading"]) == (da.README_PATH, "収録仕様"):
                section["body"] = section["body"].replace("設置する。（根拠: `1. 設置`）", "設置する。")
        plan_for(root, skeletons, legacy, legacy_result, refresh=True)


def test_direct_edit_detection() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-direct-") as temp_dir:
        base = Path(temp_dir)
        cases = {
            "owned doc": lambda root: (root / "docs/api.md").write_text("changed\n", encoding="utf-8"),
            "new spec file": lambda root: ((root / "docs/spec").mkdir(exist_ok=True),
                                           (root / "docs/spec/extra.md").write_text("# x\n", encoding="utf-8")),
            "design doc": lambda root: (root / da.DESIGN_DOC_PATHS[0]).write_text(DESIGN_DOC + "\n追記\n", encoding="utf-8"),
            "manifest": lambda root: (root / "manifest.yaml").write_text("project:\n  name: other\n", encoding="utf-8"),
        }
        for label, edit in cases.items():
            root = make_repo(base, skeletons, name=label.replace(" ", "-"))
            targets = targets_for(root, skeletons)
            result = make_result(targets)
            edit(root)
            _expect(da.ApplyError, label, lambda: plan_for(root, skeletons, targets, result))


def test_rollback_on_write_failure() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-rollback-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons)
        targets = targets_for(root, skeletons)
        plan = plan_for(root, skeletons, targets, make_result(targets))
        _assert(len(plan.writes) >= 3, "fixture must write several files")
        before = {rel: (root / rel).read_bytes() for rel in plan.writes if (root / rel).exists()}
        order = list(plan.writes)
        failing = root / order[-1]
        original = da._write_bytes
        calls = []

        def broken(path: Path, payload: bytes) -> None:
            calls.append(path)
            if path == failing and payload == plan.writes[order[-1]]:
                raise OSError("injected failure")
            original(path, payload)

        with patch.object(da, "_write_bytes", side_effect=broken):
            exc = _expect(da.FatalError, "write failure", lambda: da.commit(root, plan.writes))
        _assert("元へ戻しました" in str(exc), f"unexpected message: {exc}")
        for rel, data in before.items():
            _assert((root / rel).read_bytes() == data, f"not restored: {rel}")
        for rel in plan.writes:
            if rel not in before:
                _assert(not (root / rel).exists(), f"new file not removed: {rel}")

        # 戻し自体が失敗したときは、変更されたファイルを列挙して致命的エラーにする。
        def doubly_broken(path: Path, payload: bytes) -> None:
            if path == failing:
                raise OSError("injected failure")
            if len(calls) > 50:
                raise OSError("restore failure")
            if payload in before.values():
                raise OSError("restore failure")
            original(path, payload)

        with patch.object(da, "_write_bytes", side_effect=doubly_broken):
            exc = _expect(da.FatalError, "restore failure", lambda: da.commit(root, plan.writes))
        _assert("戻せない" in str(exc), f"unexpected message: {exc}")

        # 置換が終わった直後の割り込みでも、登録済みのファイルは commit 開始時の内容へ戻す。
        target_rel = order[0]
        target = root / target_rel
        snapshot = {rel: (root / rel).read_bytes() for rel in plan.writes if (root / rel).exists()}

        interrupted = False

        def write_then_interrupt(path: Path, payload: bytes) -> None:
            nonlocal interrupted
            original(path, payload)
            if path == target and not interrupted:
                interrupted = True
                raise KeyboardInterrupt()

        with patch.object(da, "_write_bytes", side_effect=write_then_interrupt):
            exc = _expect(da.FatalError, "interrupt after replace", lambda: da.commit(root, plan.writes))
        _assert("元へ戻しました" in str(exc), f"unexpected message: {exc}")
        if target_rel in snapshot:
            _assert(target.read_bytes() == snapshot[target_rel], "interrupted write was not restored")
        else:
            _assert(not target.exists(), "interrupted new file was not removed")


def test_cli_fill_flow_and_stale_pin() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-cli-") as temp_dir:
        base = Path(temp_dir)

        # Design Doc が無いときは skip し、targets だけを書く。
        root = make_repo(base, skeletons, design=False, name="nodoc")
        code, out, _ = run_cli(root, skeletons, "state")
        _assert(code == 0 and "action=skip" in out, f"nodoc state: {code} {out}")
        code, out, _ = run_cli(root, skeletons, "apply")
        _assert(code == 0 and "対象なし" in out, f"nodoc apply: {code} {out}")

        # 初回 fill: fingerprint を固定し、targets と result を片付ける。
        root = make_repo(base, skeletons, name="first")
        code, out, _ = run_cli(root, skeletons, "state")
        _assert(code == 0 and "action=fill" in out and "pin=unpinned" in out, f"state: {out}")
        targets = genlib.load_manifest(str(root / da.TARGETS_RELATIVE))
        write_result(root, make_result(targets))
        code, out, err = run_cli(root, skeletons, "apply")
        _assert(code == 0 and "適用完了" in out, f"first apply: {code} {out} {err}")
        _assert(not (root / da.TARGETS_RELATIVE).exists() and not (root / da.RESULT_RELATIVE).exists(),
                "targets/result must be removed")
        _assert(manifest_design_doc(root)["source_fingerprint"] == tc.source_fingerprint(root / da.DESIGN_DOC_PATHS[0]),
                "fingerprint not pinned")

        # 結果ファイル不足と検証失敗は exit 1、targets 無しは exit 2。
        root2 = make_repo(base, skeletons, name="errors")
        _assert(run_cli(root2, skeletons, "apply")[0] == 2, "apply without targets must be exit 2")
        _assert(run_cli(root2, skeletons, "state")[0] == 0, "state failed")
        code, _, err = run_cli(root2, skeletons, "apply")
        _assert(code == 1 and "結果ファイル" in err, f"missing result: {code} {err}")
        write_result(root2, {"sections": [{"file": "docs/api.md", "heading": "参照", "evidence": "概要", "body": "x"}]})
        code, _, err = run_cli(root2, skeletons, "apply")
        _assert(code == 1 and "ERROR" in err, f"invalid result: {code} {err}")
        _assert(run_cli(root2, skeletons, "apply", "--approve", "x")[0] == 2, "--approve without --refresh")
        _assert(run_cli(root2, skeletons, "apply", "--refresh")[0] == 2, "mode mismatch must be exit 2")

        # stale の fill-only は fingerprint を更新しない。
        root3 = make_repo(base, skeletons, pin="stale", name="stale-fill")
        code, out, _ = run_cli(root3, skeletons, "state")
        _assert("action=stale" in out, f"stale state: {out}")
        targets = genlib.load_manifest(str(root3 / da.TARGETS_RELATIVE))
        write_result(root3, make_result(targets))
        _assert(run_cli(root3, skeletons, "apply")[0] == 0, "stale fill failed")
        _assert(manifest_design_doc(root3)["source_fingerprint"] == "0" * 64, "stale fill updated the fingerprint")


def test_cli_refresh_requires_approval() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-refresh-") as temp_dir:
        base = Path(temp_dir)
        root = make_repo(base, skeletons, pin="fresh")
        apply_fill(root, skeletons)
        # Design Doc を更新して stale にする。
        doc = root / da.DESIGN_DOC_PATHS[0]
        doc.write_text(DESIGN_DOC.replace("API の説明。", "API の説明（更新）。"), encoding="utf-8")
        code, out, _ = run_cli(root, skeletons, "state")
        _assert("action=stale" in out and "sections=0" in out, f"stale state: {out}")

        code, out, _ = run_cli(root, skeletons, "state", "--refresh")
        _assert(code == 0 and "action=refresh" in out, f"refresh state: {out}")
        targets = genlib.load_manifest(str(root / da.TARGETS_RELATIVE))
        owned_total = sum(len(v) for v in da.OWNERSHIP.values())
        _assert(sum(len(i["sections"]) for i in targets["files"]) == owned_total, "refresh must list all owned sections")
        result = make_result(targets, overrides={("docs/api.md", "API設計概要"): "更新後の概要。"})
        write_result(root, result)
        before = {rel: (root / rel).read_bytes() for rel in da.OWNERSHIP}
        before_manifest = (root / "manifest.yaml").read_bytes()

        code, out, _ = run_cli(root, skeletons, "apply", "--refresh")
        _assert(code == 0 and "PLAN:" in out and "更新後の概要。" in out, f"preview: {out}")
        _assert(all((root / rel).read_bytes() == data for rel, data in before.items()), "preview wrote docs")
        _assert((root / "manifest.yaml").read_bytes() == before_manifest, "preview wrote the manifest")
        digest = out.split("digest=")[1].split()[0]
        code, _, err = run_cli(root, skeletons, "apply", "--refresh", "--approve", "0" * 64)
        _assert(code == 1 and "digest" in err, f"wrong digest accepted: {code} {err}")
        _assert(all((root / rel).read_bytes() == data for rel, data in before.items()), "wrong digest wrote docs")

        code, out, err = run_cli(root, skeletons, "apply", "--refresh", "--approve", digest)
        _assert(code == 0, f"approve failed: {err}")
        api = (root / "docs/api.md").read_text(encoding="utf-8")
        _assert("更新後の概要。" in api and "## API設計概要" in api, "refresh body missing")
        _assert("## proto-first" in api and "## 参照" in api, "kit-owned sections lost")
        _assert(manifest_design_doc(root)["source_fingerprint"] == tc.source_fingerprint(doc), "fingerprint not refreshed")
        _assert(run_cli(root, skeletons, "state")[1].count("action=skip") == 1, "state after refresh must skip")

        # 見送り: docs は変えず、fingerprint だけ更新する。
        doc.write_text(DESIGN_DOC.replace("API の説明。", "API の説明（再更新）。"), encoding="utf-8")
        _assert("action=stale" in run_cli(root, skeletons, "state")[1], "second stale missing")
        _assert(run_cli(root, skeletons, "state", "--refresh")[0] == 0, "second refresh state failed")
        snapshot = {rel: (root / rel).read_bytes() for rel in da.OWNERSHIP}
        code, out, err = run_cli(root, skeletons, "apply", "--refresh", "--decline")
        _assert(code == 0 and "見送り" in out, f"decline: {code} {out} {err}")
        _assert(all((root / rel).read_bytes() == data for rel, data in snapshot.items()), "decline wrote docs")
        _assert(manifest_design_doc(root)["source_fingerprint"] == tc.source_fingerprint(doc), "decline did not pin")
        _assert(run_cli(root, skeletons, "apply", "--decline")[0] == 2, "--decline without --refresh")


def test_refresh_replaces_existing_spec_files() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-refresh-spec-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons, pin="fresh")
        apply_fill(root, skeletons)
        setup = root / "docs/spec/setup.md"
        before = setup.read_text(encoding="utf-8")
        updated = [dict(item) for item in SPEC_FILES]
        updated[0]["body"] = "## 概要\n\n更新した概要。"
        targets = targets_for(root, skeletons, refresh=True)
        # fill-only 相当の結果でも既存の機能仕様は再作成しない（refresh では置換する）。
        plan = plan_for(root, skeletons, targets, make_result(targets, updated), refresh=True)
        _assert("docs/spec/setup.md" in plan.writes, "refresh did not replace the existing spec file")
        _assert("docs/spec/order.md" not in plan.writes, "unchanged spec file was rewritten")
        _assert(any("更新した概要。" in diff for diff in plan.diffs), "diff missing")
        _assert(setup.read_text(encoding="utf-8") == before, "plan wrote the file")

        # 見出しが消えた機能は ORPHAN として報告するだけ。
        doc = root / da.DESIGN_DOC_PATHS[0]
        doc.write_text(DESIGN_DOC.replace("### 2. 注文 ###", "### 2. 別の見出し"), encoding="utf-8")
        orphan_targets = targets_for(root, skeletons, refresh=True)
        only_setup = [dict(SPEC_FILES[0])]
        result = make_result(orphan_targets, SPEC_FILES[:1])
        result["spec_files"] = only_setup
        _expect(da.ApplyError, "orphan row left in README", lambda: plan_for(
            root, skeletons, orphan_targets, result, refresh=True))
        # 消えた見出しの機能は、収録仕様と機能仕様に残したまま ORPHAN として報告される。
        keep_rows = make_result(orphan_targets, SPEC_FILES, {
            (da.README_PATH, "収録仕様"): (
                "- [設置](setup.md) — 設置する。（根拠: `1. 設置`）\n"
                "- [注文](order.md) — 注文する。（根拠: `2. 注文`）"
            ),
        })
        keep_rows["spec_files"] = [dict(SPEC_FILES[0])]
        plan = plan_for(root, skeletons, orphan_targets, keep_rows, refresh=True)
        _assert(any(note.startswith("ORPHAN:") and "order.md" in note for note in plan.notes), f"no ORPHAN note: {plan.notes}")
        _assert((root / "docs/spec/order.md").is_file(), "orphan file must not be deleted")


def test_domain_docs_skill_template_contract() -> None:
    template_path = da.TEMPLATES_DIR / "skills/domain-docs/SKILL.md.template"
    rendered = genlib.render(template_path.read_text(encoding="utf-8"), {})
    _assert(rendered == template_path.read_text(encoding="utf-8"), "template must render without substitution")
    for required in (
        "name: domain-docs",
        "tmp/domain-docs-result.yaml",
        "## 所有権表",
        "docs/spec/{slug}.md",
        "結果ファイル以外は編集しない",
        "schema_version",
        "sections",
        "omissions",
        "spec_files",
        "[TODO]",
        "erDiagram",
        "画像リンク",
        "## 契約節",
        "placeholders",
        "docs/api.md",
        "data-models.md",
        "workflows.md",
        "## 持ち込む内容",
        "## 図の引継ぎ",
        "## ER図・関係性",
        "supporting_evidence",
        "`contract`",
        "files[].guidance",
        "tmp/domain-docs-findings.yaml",
        "apply --check",
        "業務フロー",
        "## エラーハンドリング",
    ):
        _assert(required in rendered, f"skill contract missing: {required}")
    _assert("field-guide" not in rendered, "field-guide must not be referenced")
    for rel, owned in da.OWNERSHIP.items():
        _assert(rel in rendered, f"ownership file missing: {rel}")
        for name in owned:
            _assert(name in rendered, f"ownership heading missing: {rel}#{name}")
    _assert(sum(len(names) for names in da.OWNERSHIP.values()) == 23, "ownership size changed")
    _assert("参照" in rendered, "kit-owned exclusion missing: 参照")
    # 所有権表の行と OWNERSHIP が一致する（表に無い節は書けない）。
    table_rows = {
        tuple(cell.strip().strip("`") for cell in line.strip("|").split("|"))
        for line in rendered.splitlines()
        if line.startswith("| `docs/")
    }
    expected_rows = {(rel, name) for rel, names in da.OWNERSHIP.items() for name in names}
    _assert(table_rows == expected_rows, f"ownership table drifted: {sorted(table_rows ^ expected_rows)}")


def test_generated_skill_is_cataloged_and_linked() -> None:
    """生成スキルが seed の outputs[] に登録され、foundation SKILL.md の参照先と一致すること。"""
    seed = genlib.load_manifest(str(da.SEED_MANIFEST))
    entries = [out for out in seed.get("outputs") or [] if out.get("path") == ".cursor/skills/domain-docs/SKILL.md"]
    _assert(len(entries) == 1, f"domain-docs must be cataloged exactly once: {len(entries)}")
    entry = entries[0]
    _assert(entry.get("template") == "skills/domain-docs/SKILL.md.template", "template path mismatch")
    _assert(entry.get("mode") == "render", "domain-docs must be render mode")
    _assert("feature" not in entry, "domain-docs must not be feature-gated")
    _assert((da.TEMPLATES_DIR / entry["template"]).is_file(), "cataloged template is missing")

    skill_text = (da.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    _assert("(../domain-docs/SKILL.md)" in skill_text, "foundation SKILL.md must link the generated skill")
    _assert("field-guide" not in skill_text, "foundation SKILL.md must not reference field-guide")
    _assert("独立スキル [`domain-docs`]" not in skill_text, "domain-docs must not be described as independent")

    generated = ROOT / ".cursor" / "skills" / "domain-docs" / "SKILL.md"
    _assert(generated.is_file(), "generated domain-docs SKILL.md is missing; run generate")
    template_text = (da.TEMPLATES_DIR / entry["template"]).read_text(encoding="utf-8")
    _assert(generated.read_text(encoding="utf-8") == genlib.render(template_text, {}), "generated skill drifted")


def test_zero_state_e2e_ends_skip_fresh() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-e2e-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons, name="e2e")
        code, out, err = run_cli(root, skeletons, "state")
        _assert(code == 0 and "action=fill" in out and "pin=unpinned" in out, f"state: {out} {err}")
        targets = genlib.load_manifest(str(root / da.TARGETS_RELATIVE))
        write_result(root, make_result(targets))
        code, out, err = run_cli(root, skeletons, "apply")
        _assert(code == 0 and "適用完了" in out, f"apply: {out} {err}")
        before = {rel: (root / rel).read_bytes() for rel in da.OWNERSHIP}
        code, out, err = run_cli(root, skeletons, "state")
        _assert(code == 0 and "action=skip" in out and "pin=fresh" in out, f"after: {out} {err}")
        code, out, _ = run_cli(root, skeletons, "state")
        _assert(code == 0 and "action=skip" in out, "rerun state changed")
        _assert(all((root / rel).read_bytes() == data for rel, data in before.items()), "rerun changed docs")


def test_refresh_invalid_result_does_not_write() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-refresh-invalid-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons, pin="fresh")
        apply_fill(root, skeletons)
        before = {rel: (root / rel).read_bytes() for rel in da.OWNERSHIP}
        code, out, err = run_cli(root, skeletons, "state", "--refresh")
        _assert(code == 0 and "action=refresh" in out, f"refresh state: {out} {err}")
        write_result(root, {"sections": [{"file": "docs/api.md", "heading": "参照", "evidence": "概要", "body": "x"}]})
        code, _, err = run_cli(root, skeletons, "apply", "--refresh")
        _assert(code == 1 and "ERROR" in err, f"invalid refresh accepted: {code} {err}")
        _assert(all((root / rel).read_bytes() == data for rel, data in before.items()), "invalid refresh wrote docs")


def test_real_repo_docs_keep_structure() -> None:
    """本リポジトリの6つの docs が、kit の器の見出しを順に保っていること。全文一致は求めない。"""
    manifest_path = ROOT / "manifest.yaml"
    skeletons = da.render_skeletons(manifest_path)
    _assert(set(skeletons) == set(da.OWNERSHIP), f"skeleton set mismatch: {sorted(skeletons)}")
    # title は resolved manifest から取る（apply の cmd_state / cmd_apply と同じ経路）。
    titles = da.contract_section_titles(manifest_path)
    domain_docs = genlib.load_manifest(str(manifest_path)).get("domain_docs") or {}
    for rel, key in da.CONTRACT_SECTION_KEYS.items():
        declared = {section["title"] for section in domain_docs.get(key) or []}
        _assert(titles[rel] == declared, f"contract_section_titles must match root manifest {key}: {sorted(titles[rel])}")
    info = da.analyze(ROOT, skeletons, titles)
    for rel, entry in info.items():
        _assert(entry["exists"], f"{rel} is missing")
        _assert(not entry["mismatch"], f"{rel}: {entry['mismatch']}")
    # 契約節（placeholder）は、そのファイルの契約の配列と一致する。他のファイルへ広がらない。
    for rel, entry in info.items():
        expected = titles.get(rel, frozenset())
        _assert(set(entry["placeholder_quotes"]) == set(expected),
                f"{rel}: placeholders must equal the contract titles: {sorted(entry['placeholder_quotes'])} vs {sorted(expected)}")



def test_er_section_validation() -> None:
    skeletons = _skeletons()
    # er_entities の解析: 宣言、関係、属性ブロック、解釈できない行。
    entities, unparsed = da.er_entities(
        "```mermaid\nerDiagram\n    items {\n        bigint item_id PK\n    }\n"
        "    items ||--o{ order_items : has\n    orders }o..|| items : ref\n    lonely\n```"
    )
    _assert(entities == {"items", "order_items", "orders", "lonely"} and not unparsed,
            f"er_entities wrong: {entities} {unparsed}")
    _assert(da.er_entities("```mermaid\nerDiagram\n    this is not valid\n```")[1] == ["this is not valid"],
            "unparsed line not reported")
    unclosed_entities, unclosed_unparsed = da.er_entities(
        "```mermaid\nerDiagram\n    items {\n        bigint item_id PK\n```"
    )
    _assert(unclosed_entities == {"items"} and unclosed_unparsed == ["エンティティ宣言の閉じ波括弧がありません"],
            f"unclosed entity accepted: {unclosed_entities} {unclosed_unparsed}")
    with tempfile.TemporaryDirectory(prefix="domain-docs-er-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons)
        targets = targets_for(root, skeletons)
        tables = ("docs/data-models.md", "主要テーブル/コレクション構成")
        er_key = ("docs/data-models.md", da.ER_SECTION)

        def build(er_body, extra=None):
            overrides = {er_key: er_body, **(extra or {})}
            return plan_for(root, skeletons, targets, make_result(targets, overrides=overrides))

        def fence(code):
            return "```mermaid\nerDiagram\n" + code + "\n```"

        plan = build(fence("    items ||--o{ order_items : has"))
        text = plan.writes["docs/data-models.md"].decode("utf-8")
        _assert("## ER図・関係性\n\n```mermaid\nerDiagram" in text, "ER body not written")
        # 契約節の本文にあるテーブル名も、ER 図のエンティティとして使える。
        build(fence("    ledger ||--o{ items : has"), {
            ("docs/data-models.md", "スキーマ適用"): "ledger テーブルを持つ。"})
        # 属性ブロックを持つ宣言も受け付ける。
        build(fence("    items {\n        bigint item_id PK\n    }\n    items ||--o{ order_items : has"))

        def rejected(label, body, expect=None):
            exc = _expect(da.ApplyError, label, lambda: build(body))
            if expect:
                _assert(expect in str(exc), f"{label}: unexpected message: {exc}")

        rejected("sample entity", fence("    ENTITY_A ||--o{ ENTITY_B : has"), "雛形名")
        rejected("unknown entity", fence("    ghost ||--o{ items : has"), "ghost")
        rejected("no diagram", "テーブルの関係を文章で書く。", "erDiagram")
        rejected("no fence", "erDiagram\n    items ||--o{ order_items : has", "erDiagram")
        rejected("unparsed line", fence("    items ||--o{ order_items : has\n    not a relation"), "解釈できない")
        rejected("unclosed entity", fence("    items {\n        bigint item_id PK"), "閉じ波括弧")
        rejected("image link", "![図](a.png)\n" + fence("    items ||--o{ order_items : has"), "画像リンク")
        # テーブルの記述に無い名前は、ER 図以外の本文が無いと使えない（エンティティの実在検証）。
        exc = _expect(da.ApplyError, "table body without the entity", lambda: build(
            fence("    items ||--o{ order_items : has"), {tables: "テーブルの記述は別にある。"}))
        _assert("items" in str(exc), f"missing entity not named: {exc}")

        # `erDiagram` は ER 図の節以外では書けない。
        other = make_result(targets)
        for section in other["sections"]:
            if section["heading"] == "主要テーブル/コレクション構成":
                section["body"] = fence("    items ||--o{ order_items : has")
        _expect(da.ApplyError, "erDiagram outside the ER section", lambda: plan_for(root, skeletons, targets, other))

        # 根拠が無いときは omission で見送れる。器は `[TODO]` だけが残り、偽の図は無い。
        plan = plan_for(root, skeletons, targets, make_result(targets, overrides={er_key: None}))
        text = plan.writes["docs/data-models.md"].decode("utf-8")
        _assert("## ER図・関係性\n\n[TODO]" in text and "ENTITY_A" not in text, "omitted ER must stay a bare TODO")


def test_schema_v2_supporting_evidence() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-v2-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons)
        targets = targets_for(root, skeletons)

        def check(label, mutate, version=2, error=da.ApplyError):
            result = make_result(targets)
            result["schema_version"] = version
            mutate(result)
            _expect(error, label, lambda: plan_for(root, skeletons, targets, result))

        # v1（キー無し）は現行どおり。v2 で supporting_evidence を使える。
        plan_for(root, skeletons, targets, make_result(targets))
        result = make_result(targets)
        result["schema_version"] = 2
        result["sections"][0]["supporting_evidence"] = ["API設計", "1. 設置"]
        result["spec_files"][0]["supporting_evidence"] = ["API設計"]
        plan = plan_for(root, skeletons, targets, result)
        _assert("docs/spec/setup.md" in plan.writes, "v2 spec file not planned")
        _assert("API設計" not in plan.writes["docs/spec/README.md"].decode("utf-8"),
                "supporting evidence must not appear in the README rows")

        v1 = make_result(targets)
        v1["sections"][0]["supporting_evidence"] = ["API設計"]
        _expect(da.ApplyError, "v1 with supporting_evidence", lambda: plan_for(root, skeletons, targets, v1))
        check("unknown version", lambda r: None, version=3)
        check("bool version", lambda r: None, version=True)
        check("unknown heading", lambda r: r["sections"][0].update({"supporting_evidence": ["存在しない"]}))
        check("not a list", lambda r: r["sections"][0].update({"supporting_evidence": "API設計"}))
        check("duplicates", lambda r: r["sections"][0].update({"supporting_evidence": ["API設計", "API設計"]}))
        check("multiline", lambda r: r["sections"][0].update({"supporting_evidence": ["API設計\n概要"]}))
        check("spec file unknown heading", lambda r: r["spec_files"][0].update({"supporting_evidence": ["存在しない"]}))
        # 一意性は主根拠だけに適用する。補助根拠は他の機能仕様の主根拠と重なってよい。
        ok = make_result(targets)
        ok["schema_version"] = 2
        ok["spec_files"][0]["supporting_evidence"] = ["2. 注文"]
        plan_for(root, skeletons, targets, ok)


def test_new_spec_evidence_is_business_flow_child() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-flow-") as temp_dir:
        base = Path(temp_dir)
        root = make_repo(base, skeletons, name="flow")
        targets = targets_for(root, skeletons)
        wrong = [dict(item) for item in SPEC_FILES]
        wrong[0]["evidence"] = "API設計"
        exc = _expect(da.ApplyError, "evidence outside 業務フロー", lambda: plan_for(
            root, skeletons, targets, make_result(targets, wrong)))
        _assert("業務フロー" in str(exc), f"unexpected message: {exc}")

        # 業務フロー見出しが無い設計書では、この検査を行わない。
        root = make_repo(base, skeletons, name="no-flow")
        doc = root / da.DESIGN_DOC_PATHS[0]
        doc.write_text(DESIGN_DOC.replace("## 業務フロー", "## 流れ"), encoding="utf-8")
        targets = targets_for(root, skeletons)
        plan_for(root, skeletons, targets, make_result(targets, wrong))

        # 既存の機能仕様は、根拠が 業務フロー 直下でなくても変えない（refresh で同じ根拠を使える）。
        root = make_repo(base, skeletons, pin="fresh", name="legacy")
        legacy = [dict(item) for item in SPEC_FILES]
        legacy[0]["evidence"] = "API設計"
        # 既存の機能仕様を直接置く（旧い試行の結果を模す）。
        apply_fill(root, skeletons, spec_files=SPEC_FILES)
        readme = root / da.README_PATH
        readme.write_text(readme.read_text(encoding="utf-8").replace("`1. 設置`", "`API設計`"), encoding="utf-8")
        later = targets_for(root, skeletons, refresh=True)
        plan_for(root, skeletons, later, make_result(later, legacy), refresh=True)


def test_check_mode_runs_the_gate_without_writing() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-check-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons)
        code, out, err = run_cli(root, skeletons, "state")
        _assert(code == 0, f"state failed: {err}")
        targets = genlib.load_manifest(str(root / da.TARGETS_RELATIVE))
        before_docs = {rel: (root / rel).read_bytes() for rel in da.OWNERSHIP}
        before_manifest = (root / "manifest.yaml").read_bytes()
        findings_path = root / da.FINDINGS_RELATIVE

        # G-DOCFILL-001（FAIL）: 見本の状態図が残っている。
        sample = "```mermaid\nstateDiagram-v2\n    [*] --> Created\n    Created --> Processing\n```"
        bad = make_result(targets, overrides={("docs/workflows.md", "状態管理・状態遷移"): sample})
        write_result(root, bad)
        code, out, err = run_cli(root, skeletons, "apply", "--check")
        _assert(code == 1 and "G-DOCFILL-001" in out + err, f"gate FAIL not reported: {code} {out} {err}")
        findings = genlib.load_manifest(str(findings_path))
        _assert(findings["status"] == "FAIL" and findings["findings"][0]["id"] == "G-DOCFILL-001",
                f"findings wrong: {findings}")
        _assert(all((root / rel).read_bytes() == data for rel, data in before_docs.items()), "check wrote docs")
        _assert((root / da.TARGETS_RELATIVE).is_file() and (root / da.RESULT_RELATIVE).is_file(),
                "check removed the targets/result")

        # 通常の apply も、同じ FAIL で書込みしない。
        code, _, err = run_cli(root, skeletons, "apply")
        _assert(code == 1 and "決定論ゲート" in err, f"apply must fail on the gate: {code} {err}")
        _assert(all((root / rel).read_bytes() == data for rel, data in before_docs.items()), "failed apply wrote docs")

        # 修復後: PASS（WARN は報告だけ）。書込み・pin・片付けはしない。
        write_result(root, make_result(targets))
        code, out, err = run_cli(root, skeletons, "apply", "--check")
        _assert(code == 0 and "CHECK: PASS" in out, f"check should pass: {code} {out} {err}")
        _assert("WARN: G-DOCFILL-005" in out, f"missing WARN for spec without error handling: {out}")
        findings = genlib.load_manifest(str(findings_path))
        _assert(findings["status"] == "PASS", f"findings status wrong: {findings}")
        _assert(all((root / rel).read_bytes() == data for rel, data in before_docs.items()), "check wrote docs")
        _assert((root / "manifest.yaml").read_bytes() == before_manifest, "check pinned the manifest")
        _assert((root / da.TARGETS_RELATIVE).is_file() and (root / da.RESULT_RELATIVE).is_file(),
                "check removed the targets/result")
        _assert(not (root / "docs/spec/setup.md").exists(), "check created a spec file")

        # --check は --approve / --decline と併用できない。
        _assert(run_cli(root, skeletons, "apply", "--check", "--refresh", "--approve", "x")[0] == 2,
                "--check with --approve must be exit 2")

        # apply 本体: 適用し、targets / result / findings を片付ける。
        code, out, err = run_cli(root, skeletons, "apply")
        _assert(code == 0 and "適用完了" in out, f"apply failed: {code} {out} {err}")
        _assert(not findings_path.exists() and not (root / da.TARGETS_RELATIVE).exists(), "apply left findings behind")


def test_pin_keeps_verified_fingerprint_when_the_doc_changes_before_commit() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-pin-race-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons, pin="fresh")
        apply_fill(root, skeletons)
        doc = root / da.DESIGN_DOC_PATHS[0]
        doc.write_text(DESIGN_DOC.replace("API の説明。", "API の説明（更新）。"), encoding="utf-8")
        verified = tc.source_fingerprint(doc)
        _assert(run_cli(root, skeletons, "state", "--refresh")[0] == 0, "refresh state failed")
        before = (root / "manifest.yaml").read_bytes()
        original = da._plan_pin

        def change_after_pin(root, manifest_path, doc, plan, fingerprint):
            original(root, manifest_path, doc, plan, fingerprint)
            doc.write_text(doc.read_text(encoding="utf-8") + "\n途中変更。\n", encoding="utf-8")
            _assert(fingerprint == verified, "pin used a fingerprint reread from the changed file")

        with patch.object(da, "_plan_pin", side_effect=change_after_pin):
            code, _, err = run_cli(root, skeletons, "apply", "--refresh", "--decline")
        _assert(code == 1 and "変更されました" in err, f"changed doc was pinned: {code} {err}")
        _assert((root / "manifest.yaml").read_bytes() == before, "decline wrote the manifest after the doc changed")


def test_missing_skeleton_template_is_fatal() -> None:
    missing = Path("/tmp/domain-docs-missing-template.md.template")
    exc = _expect(da.FatalError, "missing template", lambda: da._read_skeleton_template(missing))
    _assert("読み込み失敗" in str(exc), f"unexpected message: {exc}")
    with tempfile.TemporaryDirectory(prefix="domain-docs-bad-template-") as temp_dir:
        path = Path(temp_dir) / "bad.md.template"
        path.write_bytes(b"\xff")
        exc = _expect(da.FatalError, "bad encoding", lambda: da._read_skeleton_template(path))
        _assert("読み込み失敗" in str(exc), f"unexpected message: {exc}")


def test_state_warns_about_vocabulary_in_the_contract() -> None:
    skeletons = _skeletons()
    with tempfile.TemporaryDirectory(prefix="domain-docs-vocab-") as temp_dir:
        root = make_repo(Path(temp_dir), skeletons)
        doc = root / da.DESIGN_DOC_PATHS[0]
        doc.write_text(DESIGN_DOC + "\n失敗は `conflict_dining` を返す。ファイルは `item.go`。\n", encoding="utf-8")
        try:
            GUIDANCE_TEXTS[:] = ["失敗時は conflict_dining は 409 とする。", "Go の規約。"]
            code, out, err = run_cli(root, skeletons, "state")
            _assert(code == 0 and "WARN" in out and "conflict_dining" in out, f"vocabulary WARN missing: {code} {out}")
            _assert("item.go" not in out, "non snake_case spans must not be reported")
            GUIDANCE_TEXTS[:] = ["方式だけを述べる。"]
            code, out, _ = run_cli(root, skeletons, "state")
            _assert(code == 0 and "WARN" not in out, f"unexpected WARN: {out}")
        finally:
            GUIDANCE_TEXTS[:] = []


def main() -> int:
    tests = (
        ("state table", test_state_table),
        ("heading names trailing hash and fence", test_heading_names_trailing_hash_and_fence),
        ("pin preserves following keys and migrates old format", test_pin_preserves_following_keys_and_migrates_old_format),
        ("ownership matches templates", test_ownership_matches_templates),
        ("fill-only keeps hand edits", test_fill_only_keeps_hand_edits),
        ("rejects unowned and invalid sections", test_rejects_unowned_and_invalid_sections),
        ("contract placeholders are fill-only", test_contract_placeholders_fill_only),
        ("spec file rules", test_spec_file_rules),
        ("er section validation", test_er_section_validation),
        ("schema v2 supporting evidence", test_schema_v2_supporting_evidence),
        ("new spec evidence is a business flow child", test_new_spec_evidence_is_business_flow_child),
        ("check mode runs the gate without writing", test_check_mode_runs_the_gate_without_writing),
        ("pin keeps the verified fingerprint", test_pin_keeps_verified_fingerprint_when_the_doc_changes_before_commit),
        ("missing skeleton template is fatal", test_missing_skeleton_template_is_fatal),
        ("state warns about vocabulary in the contract", test_state_warns_about_vocabulary_in_the_contract),
        ("direct edit detection", test_direct_edit_detection),
        ("rollback on write failure", test_rollback_on_write_failure),
        ("cli fill flow and stale pin", test_cli_fill_flow_and_stale_pin),
        ("cli refresh requires approval", test_cli_refresh_requires_approval),
        ("refresh replaces existing spec files", test_refresh_replaces_existing_spec_files),
        ("domain-docs skill template contract", test_domain_docs_skill_template_contract),
        ("generated skill is cataloged and linked", test_generated_skill_is_cataloged_and_linked),
        ("zero state e2e ends skip fresh", test_zero_state_e2e_ends_skip_fresh),
        ("refresh invalid result does not write", test_refresh_invalid_result_does_not_write),
        ("real repo docs keep structure", test_real_repo_docs_keep_structure),
    )
    for label, test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_domain_docs_apply] FAIL: {label}: {exc}", file=sys.stderr)
            return 1
        print(f"[test_domain_docs_apply] PASS: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
