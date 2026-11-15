#!/usr/bin/env python3
"""Design Doc 投影の状態表・schema・seed 初回置換を回帰検査する。"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ENGINE_DIR = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ENGINE_DIR))
import design_doc_projection as dp  # noqa: E402
import generate  # noqa: E402
import genlib  # noqa: E402
import resolve_design_doc as rd  # noqa: E402
import run_resolved_engine as resolver  # noqa: E402
from yaml_emitter import dump_yaml_text  # noqa: E402


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_manifest(path: Path, design_doc: dict | None = None) -> None:
    value: dict = {"project": {"name": "test"}}
    if design_doc is not None:
        value["design_doc"] = design_doc
    path.write_text(dump_yaml_text(value), encoding="utf-8")


def _write_doc(root: Path, filename: str = "designdoc.md") -> Path:
    path = root / "designs" / "docs" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Design\n\n## Purpose\n\nExplicit purpose.\n", encoding="utf-8")
    return path


_OTHER_DOCS = ("api", "architecture", "data_models", "workflows")


def _draft(manifest: Path, doc: Path, body: str = "Explicit purpose.") -> dict:
    """spec だけを投影し、他の 4 doc は omissions で省略理由を示す draft。"""
    return {
        "schema_version": 1,
        "source_path": doc.relative_to(manifest.parent).as_posix(),
        "source_fingerprint": dp.tc.source_fingerprint(doc),
        "projection": {
            "spec": {
                "purpose": {
                    "body": body,
                    "evidence": "Purpose",
                },
            },
        },
        "omissions": {name: f"Design Doc に {name} の根拠節が無い" for name in _OTHER_DOCS},
    }


def _full_draft(manifest: Path, doc: Path) -> dict:
    """5 つの doc すべてを投影し、omissions を持たない draft。"""
    draft = _draft(manifest, doc)
    del draft["omissions"]
    for name in _OTHER_DOCS:
        first_field = sorted(dp.PROJECTION_FIELDS[name])[0]
        draft["projection"][name] = {
            first_field: {"body": f"{name} projected", "evidence": "Purpose"},
        }
    return draft


def _expect(exc_type: type, label: str, fn) -> None:
    try:
        fn()
    except exc_type:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"{label}: expected {exc_type.__name__}, got {type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"{label}: {exc_type.__name__} was not raised")


def _pin(manifest: Path, doc: Path) -> dict:
    return dp.pin_projection(
        manifest,
        _draft(manifest, doc),
        dp.tc.file_digest(manifest),
        doc,
    )


def _exit_for_phase(manifest: Path) -> int:
    try:
        rd.resolve_projection(manifest, allow_unpinned=False)
        return 0
    except dp.ProjectionError:
        return 1
    except dp.SchemaError:
        return 2


def _exit_for_engine(manifest: Path) -> int:
    try:
        resolver._inject_design_doc_projection({}, str(manifest))
        return 0
    except dp.ProjectionError:
        return 1
    except dp.SchemaError:
        return 2


def test_state_table() -> None:
    with tempfile.TemporaryDirectory(prefix="design-doc-states-") as temp_dir:
        base = Path(temp_dir)

        none_root = base / "none"
        none_root.mkdir()
        none_manifest = none_root / "manifest.yaml"
        _write_manifest(none_manifest)
        _assert((_exit_for_phase(none_manifest), _exit_for_engine(none_manifest)) == (0, 0), "none/none")

        missing_root = base / "missing"
        missing_root.mkdir()
        missing_manifest = missing_root / "manifest.yaml"
        _write_manifest(missing_manifest, {"schema_version": 1})
        _assert((_exit_for_phase(missing_manifest), _exit_for_engine(missing_manifest)) == (2, 2), "none/pin")

        both_root = base / "both"
        both_root.mkdir()
        both_manifest = both_root / "manifest.yaml"
        _write_manifest(both_manifest)
        _write_doc(both_root, "designdoc.md")
        _write_doc(both_root, "design-doc.md")
        _assert((_exit_for_phase(both_manifest), _exit_for_engine(both_manifest)) == (2, 2), "both")

        unpinned_root = base / "unpinned"
        unpinned_root.mkdir()
        unpinned_manifest = unpinned_root / "manifest.yaml"
        _write_manifest(unpinned_manifest)
        _write_doc(unpinned_root)
        _assert(
            (_exit_for_phase(unpinned_manifest), _exit_for_engine(unpinned_manifest)) == (1, 0),
            "doc/unpinned",
        )

        stale_root = base / "stale"
        stale_root.mkdir()
        stale_manifest = stale_root / "manifest.yaml"
        _write_manifest(stale_manifest)
        stale_doc = _write_doc(stale_root)
        _pin(stale_manifest, stale_doc)
        stale_doc.write_text(stale_doc.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        _assert((_exit_for_phase(stale_manifest), _exit_for_engine(stale_manifest)) == (1, 1), "stale")

        invalid_root = base / "invalid"
        invalid_root.mkdir()
        invalid_manifest = invalid_root / "manifest.yaml"
        _write_manifest(invalid_manifest)
        invalid_doc = _write_doc(invalid_root)
        pinned = _pin(invalid_manifest, invalid_doc)
        pinned["approval"]["digest"] = "0" * 64
        _write_manifest(invalid_manifest, pinned)
        _assert((_exit_for_phase(invalid_manifest), _exit_for_engine(invalid_manifest)) == (2, 2), "bad approval")

        ready_root = base / "ready"
        ready_root.mkdir()
        ready_manifest = ready_root / "manifest.yaml"
        _write_manifest(ready_manifest)
        ready_doc = _write_doc(ready_root)
        _pin(ready_manifest, ready_doc)
        _assert((_exit_for_phase(ready_manifest), _exit_for_engine(ready_manifest)) == (0, 0), "ready")


def test_schema_and_auto_approval() -> None:
    with tempfile.TemporaryDirectory(prefix="design-doc-schema-") as temp_dir:
        root = Path(temp_dir)
        manifest = root / "manifest.yaml"
        _write_manifest(manifest)
        doc = _write_doc(root)
        draft = _draft(manifest, doc)

        unknown = copy.deepcopy(draft)
        unknown["projection"]["spec"]["unknown"] = {
            "body": "x",
            "evidence": "Purpose",
        }
        try:
            dp.validate(unknown, manifest, doc, require_approval=False)
        except dp.SchemaError:
            pass
        else:
            raise AssertionError("unknown field accepted")

        missing_evidence = copy.deepcopy(draft)
        missing_evidence["projection"]["spec"]["purpose"]["evidence"] = "Missing"
        try:
            dp.validate(missing_evidence, manifest, doc, require_approval=False)
        except dp.SchemaError:
            pass
        else:
            raise AssertionError("missing evidence heading accepted")

        mustache = _draft(manifest, doc, "bad {{value}}")
        try:
            dp.validate(mustache, manifest, doc, require_approval=False)
        except dp.SchemaError:
            pass
        else:
            raise AssertionError("Mustache body accepted")

        sealed = _pin(manifest, doc)
        _assert(sealed["approval"]["status"] == "approved", "approval status missing")
        _assert(sealed["approval"]["digest"] == sealed["digest"], "approval digest mismatch")
        dp.validate(sealed, manifest, doc, require_approval=True)


def test_pristine_seed_replacement() -> None:
    with tempfile.TemporaryDirectory(prefix="design-doc-seed-") as temp_dir:
        root = Path(temp_dir) / "repo"
        skill = root / ".cursor" / "skills" / "test"
        templates = skill / "templates"
        templates.mkdir(parents=True)
        manifest = {
            "design_doc": {"projection": {"spec": {"purpose": {"body": "projected"}}}},
            "outputs": [{
                "path": "docs/spec.md",
                "template": "spec.template",
                "mode": "seed",
                "pristine_drop_keys": ["design_doc"],
            }],
        }
        (skill / "manifest.yaml").write_text(dump_yaml_text(manifest), encoding="utf-8")
        (templates / "spec.template").write_text(
            "{{#if design_doc.projection.spec.purpose.body}}"
            "{{design_doc.projection.spec.purpose.body}}\n"
            "{{else}}skeleton\n{{/if}}",
            encoding="utf-8",
        )
        target = root / "docs" / "spec.md"
        target.parent.mkdir(parents=True)
        target.write_text("skeleton\n", encoding="utf-8")
        _assert(generate.run(str(skill), check=False) == 0, "pristine generation failed")
        _assert(target.read_text(encoding="utf-8") == "projected\n", "pristine seed not replaced")

        target.write_text("edited\n", encoding="utf-8")
        _assert(generate.run(str(skill), check=False) == 0, "edited generation failed")
        _assert(target.read_text(encoding="utf-8") == "edited\n", "edited seed overwritten")


def test_doc_coverage_and_omissions() -> None:
    with tempfile.TemporaryDirectory(prefix="design-doc-coverage-") as temp_dir:
        root = Path(temp_dir)
        manifest = root / "manifest.yaml"
        _write_manifest(manifest)
        doc = _write_doc(root)

        def validate(draft: dict) -> None:
            dp.validate(draft, manifest, doc, require_approval=False)

        validate(_draft(manifest, doc))
        validate(_full_draft(manifest, doc))

        # 投影も omissions も無い doc は、再起案で直せる ProjectionError（exit 1）。
        gap = _draft(manifest, doc)
        del gap["omissions"]["architecture"]
        _expect(dp.ProjectionError, "doc gap", lambda: validate(gap))
        no_omissions = _draft(manifest, doc)
        del no_omissions["omissions"]
        _expect(dp.ProjectionError, "no omissions", lambda: validate(no_omissions))
        empty_doc = _draft(manifest, doc)
        empty_doc["projection"]["architecture"] = {}
        del empty_doc["omissions"]["architecture"]
        _expect(dp.ProjectionError, "empty doc mapping", lambda: validate(empty_doc))

        # omissions の形式不正・重複・投影 0 件は SchemaError（exit 2）。
        unknown = _draft(manifest, doc)
        unknown["omissions"]["unknown_doc"] = "reason"
        _expect(dp.SchemaError, "unknown doc", lambda: validate(unknown))
        blank = _draft(manifest, doc)
        blank["omissions"]["api"] = "  "
        _expect(dp.SchemaError, "blank reason", lambda: validate(blank))
        not_mapping = _draft(manifest, doc)
        not_mapping["omissions"] = ["api"]
        _expect(dp.SchemaError, "omissions list", lambda: validate(not_mapping))
        overlap = _draft(manifest, doc)
        overlap["omissions"]["spec"] = "投影と両立しない"
        _expect(dp.SchemaError, "overlap", lambda: validate(overlap))
        only_omissions = _draft(manifest, doc)
        only_omissions["projection"] = {}
        only_omissions["omissions"]["spec"] = "Design Doc に spec の根拠節が無い"
        _expect(dp.SchemaError, "omissions only", lambda: validate(only_omissions))

        # 空の projection の doc を omissions で埋める場合は重複扱いにならない。
        empty_with_reason = _draft(manifest, doc)
        empty_with_reason["projection"]["api"] = {}
        validate(empty_with_reason)


def test_digest_compat_and_legacy_pin() -> None:
    with tempfile.TemporaryDirectory(prefix="design-doc-digest-") as temp_dir:
        root = Path(temp_dir)
        manifest = root / "manifest.yaml"
        _write_manifest(manifest)
        doc = _write_doc(root)

        # omissions を持たない pin の digest は、omissions キー追加前の規則と同一である。
        full = _full_draft(manifest, doc)
        sealed = dp.pin_projection(manifest, full, dp.tc.file_digest(manifest), doc)
        _assert("omissions" not in sealed, "full pin must not gain an omissions key")
        _assert(sealed["digest"] == dp.projection_digest(full), "digest changed for omissions-free pin")
        with_omissions = copy.deepcopy(full)
        with_omissions["omissions"] = {}
        _assert(
            dp.projection_digest(with_omissions) != sealed["digest"],
            "omissions must participate in the digest",
        )

        # 旧規則で pin 済み（spec だけ投影、omissions 無し）: 再起案で直せる exit 1。
        legacy_root = root / "legacy"
        legacy_root.mkdir()
        legacy_manifest = legacy_root / "manifest.yaml"
        _write_manifest(legacy_manifest)
        legacy_doc = _write_doc(legacy_root)
        legacy = _draft(legacy_manifest, legacy_doc)
        del legacy["omissions"]
        _write_manifest(legacy_manifest, dp._finalize(legacy))
        _assert(
            (_exit_for_phase(legacy_manifest), _exit_for_engine(legacy_manifest)) == (1, 1),
            "legacy pin without doc coverage must be exit 1",
        )


def test_docs_structural_headings_and_projection_match() -> None:
    """kit 自身の Domain docs について、節マージの前提と pin 済み状態の一致を検査する。"""
    manifest = resolver.resolved_manifest(
        str(ROOT / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"),
        str(ROOT / "manifest.yaml"),
    )
    checked = 0
    for output in manifest["outputs"]:
        drop_keys = output.get("pristine_drop_keys")
        if not drop_keys:
            continue
        template = (
            ROOT / ".cursor/skills/agentic-workflow-foundation/templates" / output["template"]
        ).read_text(encoding="utf-8")
        pristine = genlib.render(
            template, {key: value for key, value in manifest.items() if key not in drop_keys}
        )
        expected = genlib.render(template, manifest)
        actual = (ROOT / output["path"]).read_text(encoding="utf-8")
        headings = generate.structural_headings(pristine)
        for where, text in (("投影なし", pristine), ("投影あり", expected), ("実ファイル", actual)):
            try:
                generate.split_structural_sections(text, headings, where)
            except generate.SectionMismatch as exc:
                raise AssertionError(f"{output['path']}: {exc}") from exc
        # 固定済み投影があれば docs/* は投影あり描画と一致する。未 pin ならスケルトンと一致する。
        _assert(actual == expected, f"docs drift from projected render: {output['path']}")
        checked += 1
    _assert(checked == 5, f"expected 5 projected seed docs, got {checked}")


def test_heading_names_trailing_hash_and_fence() -> None:
    """閉じ記号は直前に空白がある `#` だけ除去し、コードフェンス内の見出しは登録しない。"""
    with tempfile.TemporaryDirectory(prefix="design-doc-headings-") as temp_dir:
        doc = Path(temp_dir) / "designdoc.md"
        doc.write_text(
            "# Design\n\n## C#\n\n## Foo ##\n\n## Foo #bar\n\n"
            "```md\n## OnlyInCode\n```\n",
            encoding="utf-8",
        )
        names = dp._heading_names(doc)
        _assert("C#" in names, f"trailing # without space was stripped: {sorted(names)}")
        _assert("Foo" in names, f"closing ## with space not stripped: {sorted(names)}")
        _assert("Foo #bar" in names, f"non-closing # was stripped: {sorted(names)}")
        _assert("OnlyInCode" not in names, f"fenced heading registered: {sorted(names)}")


def test_pin_preserves_following_top_level_keys() -> None:
    """design_doc の直後にある値ありのトップレベルキーとコメント行は置換範囲に含めない。"""
    with tempfile.TemporaryDirectory(prefix="design-doc-boundary-") as temp_dir:
        root = Path(temp_dir)
        manifest = root / "manifest.yaml"
        _write_manifest(manifest)
        doc = _write_doc(root)
        _pin(manifest, doc)
        following = "custom_flag: true\n# note: keep\nother:\n  a: 1\n"
        manifest.write_text(manifest.read_text(encoding="utf-8") + following, encoding="utf-8")
        _pin(manifest, doc)
        raw = manifest.read_text(encoding="utf-8")
        _assert(raw.endswith(following), f"following top-level keys were removed: {raw!r}")


def main() -> int:
    tests = (
        ("state table", test_state_table),
        ("heading names trailing hash and fence", test_heading_names_trailing_hash_and_fence),
        ("pin preserves following top-level keys", test_pin_preserves_following_top_level_keys),
        ("schema and auto approval", test_schema_and_auto_approval),
        ("pristine seed replacement", test_pristine_seed_replacement),
        ("doc coverage and omissions", test_doc_coverage_and_omissions),
        ("digest compat and legacy pin", test_digest_compat_and_legacy_pin),
        ("docs structural headings and projection match", test_docs_structural_headings_and_projection_match),
    )
    for label, test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_design_doc_projection] FAIL: {label}: {exc}", file=sys.stderr)
            return 1
        print(f"[test_design_doc_projection] PASS: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
