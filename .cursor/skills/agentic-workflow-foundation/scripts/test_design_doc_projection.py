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


def _draft(manifest: Path, doc: Path, body: str = "Explicit purpose.") -> dict:
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
    }


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


def test_no_projection_templates_are_byte_identical() -> None:
    manifest = resolver.resolved_manifest(
        str(ROOT / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"),
        str(ROOT / "manifest.yaml"),
    )
    _assert("design_doc" not in manifest, "kit unpinned Design Doc must not be overlaid")
    for filename in ("spec.md", "architecture.md", "api.md", "data-models.md", "workflows.md"):
        template = (
            ROOT
            / ".cursor/skills/agentic-workflow-foundation/templates/docs"
            / f"{filename}.template"
        )
        rendered = genlib.render(template.read_text(encoding="utf-8"), manifest)
        actual = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        _assert(rendered == actual, f"no-projection output drift: {filename}")


def main() -> int:
    tests = (
        ("state table", test_state_table),
        ("schema and auto approval", test_schema_and_auto_approval),
        ("pristine seed replacement", test_pristine_seed_replacement),
        ("no-projection byte identity", test_no_projection_templates_are_byte_identical),
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
