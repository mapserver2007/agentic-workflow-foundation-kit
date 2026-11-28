#!/usr/bin/env python3
"""gen.skills で skill を無効にした状態の解決（outputs / required_sections / 残骸 WARN）の検証。

seed manifest だけを使う hermetic なテスト（root manifest.yaml / 承認済み tech_contract は不要）。
実際の generate → check → audit は、承認済み tech_contract を持つ root manifest が要るため、
本テストの範囲外（Phase 5 の検証ゲートで実施する）。
"""
from __future__ import annotations

import copy
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
ROOT = SKILL_DIR.parents[2]
ENGINE_SCRIPTS = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
for path in (str(ENGINE_SCRIPTS), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import apply_kit_init as aki  # noqa: E402
import genlib  # noqa: E402
import run_resolved_engine as rre  # noqa: E402

# seed だけでは描画できない出力（resolved manifest が注入する値が要る）。feature とは無関係。
NOT_RENDERABLE_FROM_SEED = {"docs/CONTEXT_BUDGET.md", "bin/quality-gate"}


def _seed() -> dict:
    return genlib.load_manifest(str(SKILL_DIR / "manifest.yaml"))


def _apply_skills(manifest: dict, skills: dict) -> dict:
    """apply_kit_init と同じ対応表・導出で、gen.skills を manifest の feature フラグへ反映する。"""
    for name, enabled in skills.items():
        node = manifest
        path = aki.SKILL_FEATURE_PATHS[name]
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = enabled
    workflow_on, _ = aki._derive_agent_workflow(skills)
    manifest["agent_workflow"]["enabled"] = workflow_on
    return manifest


def _variants() -> dict:
    names = list(aki.SKILL_FEATURE_PATHS)
    workflow = set(aki.AGENT_WORKFLOW_CHILD_SKILLS)
    variants = {"all-on": {}, "all-off": {n: False for n in names}}
    for name in names:
        variants[f"only-{name}-off"] = {name: False}
    variants["workflow-all-off"] = {n: False for n in workflow}
    variants["non-workflow-all-off"] = {n: False for n in names if n not in workflow}
    variants["docs-and-gotchas-off"] = {
        "maintenance-docs-workflow": False,
        "maintenance-gotchas-workflow": False,
    }
    variants["github-all-off"] = {
        n: False
        for n in (
            "agent-code-review",
            "agent-github-pr",
            "agent-github-issue",
            "cross-repository-knowledge-link",
        )
    }
    return variants


def _skills_for(overrides: dict) -> dict:
    return {name: overrides.get(name, True) for name in aki.SKILL_FEATURE_PATHS}


def _is_valid(skills: dict) -> bool:
    """gen.skills として apply_kit_init が受理する組み合わせか。"""
    return not aki._validate_gen({"gen": {"skills": skills}})


def test_required_sections_are_satisfied_by_rendered_output() -> None:
    """どの有効・無効の組み合わせでも、展開後の required_sections が描画結果に含まれる。

    audit が feature OFF の出力に対して無条件に節を要求しないこと（条件付き required_sections）の検査。
    """
    checked = 0
    for label, overrides in _variants().items():
        skills = _skills_for(overrides)
        if not _is_valid(skills):
            continue
        manifest = rre._filter_outputs_by_features(_apply_skills(_seed(), skills))
        for out in manifest["outputs"]:
            sections = out.get("required_sections") or []
            assert all(isinstance(s, str) for s in sections), (
                f"{label}: {out['path']} の required_sections に文字列以外が残っている: {sections!r}"
            )
            if out.get("mode") not in ("render", "seed") or out["path"] in NOT_RENDERABLE_FROM_SEED:
                continue
            template = SKILL_DIR / "templates" / out["template"]
            rendered = genlib.render(template.read_text(encoding="utf-8"), manifest)
            missing = [s for s in sections if s not in rendered]
            assert not missing, f"{label}: {out['path']} に必須節が無い: {missing}"
            checked += 1
    assert checked > 0


def test_conditional_required_sections_follow_feature() -> None:
    """text + feature の項目は、feature が有効なときだけ展開される。"""
    skills_on = _skills_for({})
    skills_off = _skills_for({"maintenance-docs-workflow": False})

    def sections(skills: dict, path: str) -> list[str]:
        manifest = rre._filter_outputs_by_features(_apply_skills(_seed(), skills))
        return next(o for o in manifest["outputs"] if o["path"] == path)["required_sections"]

    assert "G-MDOCS-REASON-002" in sections(skills_on, "docs/QUALITY_GATE.md")
    assert "G-MDOCS-REASON-002" not in sections(skills_off, "docs/QUALITY_GATE.md")
    # 無条件の節は feature に関係なく残る
    assert "G-WRITE-SCOPE-DOMAIN-001" in sections(skills_off, "docs/QUALITY_GATE.md")
    # agent_workflow ごと無効なら、その出力自体が生成対象から外れる
    skills_workflow_off = _skills_for({n: False for n in aki.AGENT_WORKFLOW_CHILD_SKILLS})
    manifest = rre._filter_outputs_by_features(_apply_skills(_seed(), skills_workflow_off))
    paths = {o["path"] for o in manifest["outputs"]}
    assert "docs/agent-tasks/agent-workflow/06-completion.md" not in paths
    assert "G-REPORT-DOC-SCOPE-001" not in next(
        o for o in manifest["outputs"] if o["path"] == "docs/QUALITY_GATE.md"
    )["required_sections"]


def test_malformed_conditional_required_section_is_fatal() -> None:
    for bad in ({"text": "x"}, {"feature": "code_review"}, {"text": "", "feature": "code_review"}):
        manifest = {"code_review": {"enabled": True}, "outputs": [
            {"path": "a.md", "required_sections": [bad]},
        ]}
        try:
            rre._filter_outputs_by_features(manifest)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError(f"malformed required_sections should exit 2: {bad!r}")


def test_disabled_feature_leftovers_are_listed_not_deleted() -> None:
    manifest = {
        "code_review": {"enabled": False},
        "github_pr": {"enabled": True},
        "outputs": [
            {"path": ".cursor/skills/agent-code-review/SKILL.md", "mode": "render", "feature": "code_review"},
            {"path": ".cursor/skills/agent-code-review/config.yaml", "mode": "seed", "feature": "code_review"},
            {"path": ".cursor/skills/agent-code-review/gone.md", "mode": "render", "feature": "code_review"},
            {"path": ".cursor/skills/agent-github-pr/SKILL.md", "mode": "render", "feature": "github_pr"},
            {"path": ".gitignore", "mode": "marker", "feature": "code_review"},
            {"path": "docs/tech-stack", "mode": "split", "feature": "code_review"},
            {"path": "docs/always.md", "mode": "render"},
        ],
    }
    all_outputs = copy.deepcopy(manifest["outputs"])
    filtered = rre._filter_outputs_by_features(copy.deepcopy(manifest))
    with tempfile.TemporaryDirectory(prefix="leftover-test-") as tmp:
        work = Path(tmp)
        for rel in (
            ".cursor/skills/agent-code-review/SKILL.md",
            ".cursor/skills/agent-code-review/config.yaml",
            ".cursor/skills/agent-github-pr/SKILL.md",
            ".gitignore",
            "docs/tech-stack",
            "docs/always.md",
        ):
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if rel == "docs/tech-stack":
                target.mkdir()
            else:
                target.write_text("x", encoding="utf-8")
        leftovers = rre._disabled_feature_leftovers(all_outputs, filtered["outputs"], str(work))
        assert sorted(o["path"] for o in leftovers) == [
            ".cursor/skills/agent-code-review/SKILL.md",
            ".cursor/skills/agent-code-review/config.yaml",
        ], leftovers

        # WARN は列挙するだけで、ファイルは削除しない。ファイルの無い出力は列挙しない。
        seed = work / "seed.yaml"
        seed.write_text(
            "version: 1\noutputs:\n"
            "  - path: a/skill.md\n    template: x\n    mode: render\n    feature: code_review\n"
            "  - path: a/absent.md\n    template: x\n    mode: render\n    feature: code_review\n",
            encoding="utf-8",
        )
        (work / "a").mkdir()
        (work / "a" / "skill.md").write_text("keep", encoding="utf-8")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rre._warn_disabled_feature_leftovers(
                str(seed), {"outputs": [], "code_review": {"enabled": False}}, str(work)
            )
        message = buffer.getvalue()
        assert "WARN" in message and "a/skill.md" in message and "feature: code_review" in message
        assert "a/absent.md" not in message
        assert (work / "a" / "skill.md").read_text(encoding="utf-8") == "keep"

        # 残骸が無ければ何も出さない
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rre._warn_disabled_feature_leftovers(
                str(seed), {"outputs": list(genlib.load_manifest(str(seed))["outputs"])}, str(work)
            )
        assert buffer.getvalue() == ""


def test_all_on_has_no_leftovers_in_clean_work_root() -> None:
    with tempfile.TemporaryDirectory(prefix="leftover-clean-") as tmp:
        seed = _seed()
        filtered = rre._filter_outputs_by_features(_apply_skills(copy.deepcopy(seed), _skills_for({})))
        assert rre._disabled_feature_leftovers(seed["outputs"], filtered["outputs"], tmp) == []


def main() -> int:
    tests = [
        test_required_sections_are_satisfied_by_rendered_output,
        test_conditional_required_sections_follow_feature,
        test_malformed_conditional_required_section_is_fatal,
        test_disabled_feature_leftovers_are_listed_not_deleted,
        test_all_on_has_no_leftovers_in_clean_work_root,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[test_gen_skills_resolution] FAIL: {test.__name__}: {exc}", file=sys.stderr)
    if failures:
        return 1
    print("[test_gen_skills_resolution] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
