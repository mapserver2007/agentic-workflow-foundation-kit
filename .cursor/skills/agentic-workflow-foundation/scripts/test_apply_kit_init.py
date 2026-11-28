#!/usr/bin/env python3
"""apply_kit_init.py の fixture テスト。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPLY = HERE / "apply_kit_init.py"

MANIFEST_FIXTURE = """version: 1
project:
  name: "[要確認]"
  slug: "[要確認]"
  workflow_pattern: "[要確認]"
  one_liner: "test"
  context_budget:
    min_context_window_tokens: 200000
session:
  verification:
    gate_command: "[要確認]"
"""

INIT_VALID = """version: 1
project:
  name: my-test-project
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
context_budget:
  min_context_window_tokens: 200000
"""

INIT_NULL_NAME = """version: 1
project:
  name: null
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
context_budget:
  min_context_window_tokens: 300000
"""

INIT_MINIMAL = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
"""

INIT_BAD_VERSION = """version: 2
project:
  name: test
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
"""

INIT_FORBIDDEN_KEY = """version: 1
project:
  name: test
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
features:
  code_review: true
"""

INIT_EMPTY_NAME = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
project:
  name: ""
"""

INIT_SMALL_WINDOW = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
context_budget:
  min_context_window_tokens: 10000
"""

INIT_UNKNOWN_KEY = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
project:
  name: test
  slug: forced
"""

INIT_MISSING_TSD = """version: 1
project:
  name: test
"""

INIT_TSD_EMPTY_FILENAME = """version: 1
tech_stack_design:
  filename: ""
"""

INIT_TSD_PATH_TRAVERSAL = """version: 1
tech_stack_design:
  filename: "../etc/EVIL.md"
"""

INIT_TSD_NO_MD_SUFFIX = """version: 1
tech_stack_design:
  filename: TECH_STACK.yaml
"""

INIT_TSD_UNKNOWN_KEY = """version: 1
tech_stack_design:
  filename: MY_STACK.md
  extra: bad
"""

INIT_CUSTOM_FILENAME = """version: 1
project:
  name: custom-stack-project
tech_stack_design:
  filename: MY_CUSTOM_TECH_STACK.md
context_budget:
  min_context_window_tokens: 200000
"""

INIT_AUTO_APPROVE_TRUE = """version: 1
project:
  name: auto-approve-project
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
tech_contract:
  auto_approve: true
"""

INIT_AUTO_APPROVE_FALSE = """version: 1
project:
  name: manual-approve-project
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
tech_contract:
  auto_approve: false
"""

INIT_AUTO_APPROVE_BAD_TYPE = """version: 1
project:
  name: bad-auto
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
tech_contract:
  auto_approve: "yes"
"""

INIT_AUTO_APPROVE_UNKNOWN_KEY = """version: 1
project:
  name: bad-auto
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
tech_contract:
  auto_approve: true
  extra: bad
"""

INIT_PROVISIONING_AUTO_APPROVE_TRUE = """version: 1
project:
  name: provisioning-auto-project
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
provisioning:
  auto_approve: true
"""

INIT_PROVISIONING_AUTO_APPROVE_FALSE = """version: 1
project:
  name: provisioning-manual-project
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
provisioning:
  auto_approve: false
"""

INIT_PROVISIONING_AUTO_APPROVE_BAD_TYPE = """version: 1
project:
  name: provisioning-bad-auto
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
provisioning:
  auto_approve: "yes"
"""

INIT_PROVISIONING_AUTO_APPROVE_NULL = """version: 1
project:
  name: provisioning-null-auto
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
provisioning:
  auto_approve: null
"""

INIT_PROVISIONING_AUTO_APPROVE_UNKNOWN_KEY = """version: 1
project:
  name: provisioning-bad-auto
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
provisioning:
  auto_approve: true
  extra: bad
"""

INIT_GITHUB_APP = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access:
  api_credential_provider: github_app
"""

INIT_GITHUB_KEYCHAIN = """version: 1
project:
  name: github-keychain-project
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access:
  api_credential_provider: keychain
  keychain:
    service: custom-github-service
    account: bot@example.com
"""

INIT_GITHUB_BAD_PROVIDER = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access:
  api_credential_provider: gh
"""

INIT_GITHUB_EMPTY_ACCOUNT = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access:
  api_credential_provider: keychain
  keychain:
    account: ""
"""

INIT_GITHUB_KEYCHAIN_OMITTED = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access:
  api_credential_provider: keychain
"""

INIT_GITHUB_BAD_SERVICE = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access:
  keychain:
    service: ""
"""

INIT_GITHUB_UNKNOWN_KEY = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access:
  extra: bad
"""

INIT_GITHUB_BAD_TYPE = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access: github_app
"""

INIT_GITHUB_CONTROL_CHAR = """version: 1
tech_stack_design:
  filename: APP_DESIGN_BESTPRACTICE.md
github_access:
  api_credential_provider: keychain
  keychain:
    account: "bad\x7faccount"
"""

MANIFEST_WITH_GITHUB_ACCESS = MANIFEST_FIXTURE + """github_access:
  api_credential_provider: github_app
  keychain:
    service: old-service
    account: old-account
"""

# gen.skills の投影テスト用。feature ブロックを持つ root manifest。
# code_review.report.enabled は孫キー。code_review.enabled の書き換えに巻き込まれてはならない。
MANIFEST_WITH_FEATURES = MANIFEST_FIXTURE + """code_review:
  enabled: true  # keep-me
  report:
    enabled: true
    output_dir: "docs/agent-tasks/reviews"
github_pr:
  enabled: true
github_issue:
  enabled: true
agent_workflow:
  enabled: true
  report_slug_format: "{ticket}-{slug}"
  maintenance_docs:
    enabled: true
    judgment_enum:
      - "pending"
  maintenance_gotchas:
    enabled: true
  # 子の設定（コメントは保持される）
  gate_scripts: true
  orchestrator_skill: true
requirement_analysis:
  enabled: true
  models:
    normalize: "composer-2.5-fast"
deep_thinking:
  enabled: true
agent_kaizen:
  enabled: true
cross_repo_knowledge:
  enabled: true
  clone_base_path: "/tmp/cross-repo-knowledge"
"""

# 一部の feature が root で既に false（直接編集で無効化済み）の manifest。
MANIFEST_WITH_FEATURES_PARTLY_OFF = MANIFEST_WITH_FEATURES.replace(
    "deep_thinking:\n  enabled: true", "deep_thinking:\n  enabled: false"
).replace(
    "agent_kaizen:\n  enabled: true", "agent_kaizen:\n  enabled: false"
)

# 投影先（skill 名 → manifest のパス）。apply_kit_init の対応表とは独立に、リテラルで持つ。
EXPECTED_SKILL_PATHS = {
    "agent-code-review": ("code_review", "enabled"),
    "agent-github-pr": ("github_pr", "enabled"),
    "agent-github-issue": ("github_issue", "enabled"),
    "workflow-orchestrator": ("agent_workflow", "orchestrator_skill"),
    "maintenance-docs-workflow": ("agent_workflow", "maintenance_docs", "enabled"),
    "maintenance-gotchas-workflow": ("agent_workflow", "maintenance_gotchas", "enabled"),
    "requirement-analysis": ("requirement_analysis", "enabled"),
    "deep-thinking": ("deep_thinking", "enabled"),
    "agent-kaizen": ("agent_kaizen", "enabled"),
    "cross-repository-knowledge-link": ("cross_repo_knowledge", "enabled"),
}
WORKFLOW_BASE_PATH = ("agent_workflow", "enabled")
CODE_REVIEW_REPORT_PATH = ("code_review", "report", "enabled")
WORKFLOW_CHILD_SKILLS = (
    "workflow-orchestrator",
    "maintenance-docs-workflow",
    "maintenance-gotchas-workflow",
    "requirement-analysis",
)


def _init_with_skills(skills: dict | None) -> str:
    """gen.skills を持つ init.yaml を組み立てる。skills が None なら gen を書かない。"""
    # name を固定する（省略するとテンポラリディレクトリ名から導出され、再 apply で値が変わる）
    text = (
        "version: 1\n"
        "project:\n"
        "  name: gen-skills-test\n"
        "tech_stack_design:\n"
        "  filename: APP_DESIGN_BESTPRACTICE.md\n"
    )
    if skills is None:
        return text
    text += "gen:\n  skills:\n"
    for name, value in skills.items():
        rendered = value if isinstance(value, str) else ("true" if value else "false")
        text += f"    {name}: {rendered}\n"
    return text


def _run(manifest_text: str, init_text: str, extra_args: list[str] | None = None) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory(prefix="test-apply-") as tmp:
        manifest = Path(tmp) / "manifest.yaml"
        init = Path(tmp) / "init.yaml"
        manifest.write_text(manifest_text, encoding="utf-8")
        init.write_text(init_text, encoding="utf-8")
        cmd = [sys.executable, str(APPLY), "--manifest", str(manifest), "--init", str(init)]
        if extra_args:
            cmd.extend(extra_args)
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True, env=dict(os.environ),
        )
        out = manifest.read_text(encoding="utf-8") if manifest.exists() else ""
        return result.returncode, out, result.stdout + result.stderr


def _flags(manifest_text: str) -> dict:
    """manifest の feature フラグ（10 項目 + 土台 + code_review.report）を path 文字列 → 値で返す。"""
    engine_scripts = str(HERE.parents[1] / "agentic-workflow-engine" / "scripts")
    if engine_scripts not in sys.path:
        sys.path.insert(0, engine_scripts)
    import genlib  # noqa: WPS433

    with tempfile.TemporaryDirectory(prefix="test-flags-") as tmp:
        path = Path(tmp) / "manifest.yaml"
        path.write_text(manifest_text, encoding="utf-8")
        manifest = genlib.load_manifest(str(path))
    result = {}
    paths = list(EXPECTED_SKILL_PATHS.values()) + [WORKFLOW_BASE_PATH, CODE_REVIEW_REPORT_PATH]
    for flag_path in paths:
        node = manifest
        for key in flag_path:
            node = node.get(key) if isinstance(node, dict) else None
        result[".".join(flag_path)] = node
    return result


def _expected_flags(skills: dict, workflow_base: bool) -> dict:
    """skills（skill 名 → bool、全 10 項目）と土台の期待値から、_flags と同形式の期待値を作る。"""
    expected = {".".join(EXPECTED_SKILL_PATHS[name]): value for name, value in skills.items()}
    expected[".".join(WORKFLOW_BASE_PATH)] = workflow_base
    expected[".".join(CODE_REVIEW_REPORT_PATH)] = True
    return expected


def _all_skills(value: bool = True, **overrides: bool) -> dict:
    skills = {name: value for name in EXPECTED_SKILL_PATHS}
    for key, flag in overrides.items():
        skills[key.replace("_", "-")] = flag
    return skills


def _test_gen_skills() -> list[str]:
    """gen.skills（生成 skill の選択）の検証・投影・導出。"""
    errors: list[str] = []

    def check_flags(label: str, out: str, skills: dict, workflow_base: bool) -> None:
        actual = _flags(out)
        expected = _expected_flags(skills, workflow_base)
        if actual != expected:
            diff = {k: (actual.get(k), v) for k, v in expected.items() if actual.get(k) != v}
            errors.append(f"gen.skills {label}: flags mismatch (actual, expected)={diff}")

    # G1. 全項目 true を明示 → 全 true（土台も true）。code_review.report.enabled は不変
    rc, out, log = _run(MANIFEST_WITH_FEATURES, _init_with_skills(_all_skills()))
    if rc != 0:
        errors.append(f"gen.skills all true: expected exit 0, got {rc}\n{log}")
    else:
        check_flags("all true", out, _all_skills(), True)

    # G2. 各 skill の単独 OFF → その skill のフラグだけ false。
    #     workflow 系 1 つを OFF にしても、他の子が true なので土台は true のまま。
    #     例外: requirement-analysis は workflow 系が true の間は OFF にできない（G15 で検査）
    for name in EXPECTED_SKILL_PATHS:
        if name == "requirement-analysis":
            continue
        skills = _all_skills(**{name.replace("-", "_"): False})
        rc, out, log = _run(MANIFEST_WITH_FEATURES, _init_with_skills(skills))
        if rc != 0:
            errors.append(f"gen.skills only {name} off: expected exit 0, got {rc}\n{log}")
            continue
        check_flags(f"only {name} off", out, skills, True)

    # G3. インラインコメントとコメント行が保持される。code_review.report.enabled は true のまま
    rc, out, log = _run(
        MANIFEST_WITH_FEATURES, _init_with_skills(_all_skills(**{"agent_code_review": False}))
    )
    if rc != 0:
        errors.append(f"gen.skills comment keep: expected exit 0, got {rc}\n{log}")
    for needle in ("enabled: false  # keep-me", "  # 子の設定（コメントは保持される）"):
        if needle not in out:
            errors.append(f"gen.skills comment keep: missing {needle!r}")

    # G4. 土台の導出: workflow 系 4 つがすべて false → agent_workflow.enabled は false
    skills = _all_skills(
        workflow_orchestrator=False,
        maintenance_docs_workflow=False,
        maintenance_gotchas_workflow=False,
        requirement_analysis=False,
    )
    rc, out, log = _run(MANIFEST_WITH_FEATURES, _init_with_skills(skills))
    if rc != 0:
        errors.append(f"gen.skills workflow all off: expected exit 0, got {rc}\n{log}")
    else:
        check_flags("workflow all off", out, skills, False)
        if "agent_workflow.enabled=false を導出" not in log:
            errors.append("gen.skills workflow all off: INFO about derived base missing")

    # G5. 土台の導出: 子が 1 つでも true なら土台は true（子ごとに単独で true）。
    #     requirement-analysis は workflow 系が true の間は true が必須なので、常に併せて true にする
    for child in WORKFLOW_CHILD_SKILLS:
        skills = _all_skills(
            False, **{child.replace("-", "_"): True, "requirement_analysis": True}
        )
        rc, out, log = _run(MANIFEST_WITH_FEATURES, _init_with_skills(skills))
        if rc != 0:
            errors.append(f"gen.skills only {child} on: expected exit 0, got {rc}\n{log}")
            continue
        check_flags(f"only {child} on", out, skills, True)
        if "agent_workflow.enabled=true を導出" not in log:
            errors.append(f"gen.skills only {child} on: INFO about derived base missing")

    # G6. workflow 系以外だけ true → 土台は false（workflow docs と gate は生成対象外）
    skills = _all_skills(False, agent_github_pr=True, deep_thinking=True)
    rc, out, log = _run(MANIFEST_WITH_FEATURES, _init_with_skills(skills))
    if rc != 0:
        errors.append(f"gen.skills non-workflow only: expected exit 0, got {rc}\n{log}")
    else:
        check_flags("non-workflow only", out, skills, False)

    # G7. 書いたキーだけが対象で、省略したキーは true（root で false でも true に戻る）
    rc, out, log = _run(
        MANIFEST_WITH_FEATURES_PARTLY_OFF,
        _init_with_skills({"agent-github-pr": False}),
    )
    if rc != 0:
        errors.append(f"gen.skills omitted keys: expected exit 0, got {rc}\n{log}")
    else:
        check_flags("omitted keys", out, _all_skills(agent_github_pr=False), True)

    # G8. gen / gen.skills を書かない → root の feature フラグに触れない（false のまま）
    rc, out, log = _run(MANIFEST_WITH_FEATURES_PARTLY_OFF, _init_with_skills(None))
    if rc != 0:
        errors.append(f"gen omitted: expected exit 0, got {rc}\n{log}")
    else:
        check_flags(
            "gen omitted", out, _all_skills(deep_thinking=False, agent_kaizen=False), True
        )
        if "gen.skills 未指定" not in log:
            errors.append("gen omitted: INFO about untouched flags missing")
    rc, out, log = _run(MANIFEST_FIXTURE, _init_with_skills(None))
    if rc != 0:
        errors.append(f"gen omitted without feature blocks: expected exit 0, got {rc}\n{log}")

    # G9. 冪等性: 同じ init.yaml を再 apply しても manifest は変わらない
    skills = _all_skills(deep_thinking=False, agent_code_review=False)
    init_text = _init_with_skills(skills)
    rc, out1, log = _run(MANIFEST_WITH_FEATURES, init_text)
    if rc != 0:
        errors.append(f"gen.skills idempotency: 1st apply exit {rc}\n{log}")
    rc, out2, log = _run(out1, init_text)
    if rc != 0 or out1 != out2:
        errors.append("gen.skills idempotency: second apply changed manifest or failed")

    # G10. スキーマ違反 → exit 2、manifest は無変更
    bad_cases = {
        "unknown skill": _init_with_skills({"agent-unknown": True}),
        "non-bool string": _init_with_skills({"deep-thinking": '"yes"'}),
        "null value": _init_with_skills({"deep-thinking": "null"}),
        "top-level skills": (
            "version: 1\ntech_stack_design:\n  filename: APP_DESIGN_BESTPRACTICE.md\n"
            "skills:\n  deep-thinking: false\n"
        ),
        "gen unknown key": (
            "version: 1\ntech_stack_design:\n  filename: APP_DESIGN_BESTPRACTICE.md\n"
            "gen:\n  hooks: true\n"
        ),
        "gen not mapping": (
            "version: 1\ntech_stack_design:\n  filename: APP_DESIGN_BESTPRACTICE.md\n"
            "gen: true\n"
        ),
        "gen empty": (
            "version: 1\ntech_stack_design:\n  filename: APP_DESIGN_BESTPRACTICE.md\ngen:\n"
        ),
        "gen.skills empty": (
            "version: 1\ntech_stack_design:\n  filename: APP_DESIGN_BESTPRACTICE.md\n"
            "gen:\n  skills:\n"
        ),
    }
    for always_on in ("session-planning", "session-handover", "campaign-cleanup", "domain-docs"):
        bad_cases[f"always-on {always_on}"] = _init_with_skills({always_on: False})
    for label, init_text in bad_cases.items():
        rc, out, log = _run(MANIFEST_WITH_FEATURES, init_text)
        if rc != 2:
            errors.append(f"gen.skills {label}: expected exit 2, got {rc}\n{log}")
        if out != MANIFEST_WITH_FEATURES:
            errors.append(f"gen.skills {label}: manifest changed although validation failed")

    # G11. 旧キー features は引き続き exit 2、トップレベル skills のメッセージは gen.skills を案内する
    rc, _, log = _run(MANIFEST_WITH_FEATURES, bad_cases["top-level skills"])
    if "gen.skills" not in log:
        errors.append("gen.skills top-level skills: message does not point to gen.skills")

    # G12. 投影先ブロックが root に無い → 無音でスキップせず exit 2、manifest は無変更
    rc, out, log = _run(MANIFEST_FIXTURE, _init_with_skills(_all_skills()))
    if rc != 2:
        errors.append(f"gen.skills missing blocks: expected exit 2, got {rc}\n{log}")
    if out != MANIFEST_FIXTURE:
        errors.append("gen.skills missing blocks: manifest changed on projection failure")
    if "投影先" not in log:
        errors.append("gen.skills missing blocks: error message does not name the projection failure")

    # G13. 投影先が bool リテラルでない（例: 文字列）→ exit 2
    quoted = MANIFEST_WITH_FEATURES.replace(
        "deep_thinking:\n  enabled: true", 'deep_thinking:\n  enabled: "true"'
    )
    rc, out, log = _run(quoted, _init_with_skills(_all_skills()))
    if rc != 2:
        errors.append(f"gen.skills non-bool target: expected exit 2, got {rc}\n{log}")
    if out != quoted:
        errors.append("gen.skills non-bool target: manifest changed on projection failure")

    # G15. requirement-analysis: false は、workflow 系 skill が true の間は exit 2（audit が失敗する組み合わせ）。
    #      workflow 系がすべて false なら許容される（G4）
    for other in ("workflow-orchestrator", "maintenance-docs-workflow", "maintenance-gotchas-workflow"):
        skills = _all_skills(False, **{other.replace("-", "_"): True})
        rc, out, log = _run(MANIFEST_WITH_FEATURES, _init_with_skills(skills))
        if rc != 2 or "requirement-analysis" not in log:
            errors.append(f"gen.skills RA off with {other} on: expected exit 2 naming requirement-analysis, got {rc}\n{log}")
        if out != MANIFEST_WITH_FEATURES:
            errors.append(f"gen.skills RA off with {other} on: manifest changed although validation failed")
    rc, out, log = _run(
        MANIFEST_WITH_FEATURES,
        _init_with_skills(_all_skills(**{"requirement_analysis": False})),
    )
    if rc != 2:
        errors.append(f"gen.skills only RA off: expected exit 2, got {rc}\n{log}")

    # G14. --check は書き込まない
    rc, out, log = _run(
        MANIFEST_WITH_FEATURES, _init_with_skills(_all_skills(deep_thinking=False)), ["--check"]
    )
    if rc != 0 or out != MANIFEST_WITH_FEATURES:
        errors.append("gen.skills --check: expected exit 0 and unchanged manifest")

    return errors


def main() -> int:
    errors = []

    # 1. Valid init → name / slug / workflow_pattern / tech_stack_design_filename が書き換わる
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_VALID)
    if rc != 0:
        errors.append(f"valid init: expected exit 0, got {rc}\n{log}")
    for needle in ['name: "my-test-project"', 'slug: "my-test-project"',
                    'workflow_pattern: "開発型"',
                    'tech_stack_design_filename: "APP_DESIGN_BESTPRACTICE.md"']:
        if needle not in out:
            errors.append(f"valid init: missing {needle!r} in manifest")

    # 2. null name → ディレクトリ名から導出
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_NULL_NAME)
    if rc != 0:
        errors.append(f"null name: expected exit 0, got {rc}\n{log}")
    if 'workflow_pattern: "開発型"' not in out:
        errors.append("null name: missing workflow_pattern")
    if "min_context_window_tokens: 300000" not in out:
        errors.append("null name: missing min_context_window_tokens 300000")

    # 3. Minimal init (name/context_budget 省略) → デフォルトで通過
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_MINIMAL)
    if rc != 0:
        errors.append(f"minimal init: expected exit 0, got {rc}\n{log}")
    if 'workflow_pattern: "開発型"' not in out:
        errors.append("minimal: missing workflow_pattern")

    # 4. Bad version → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_BAD_VERSION)
    if rc != 2:
        errors.append(f"bad version: expected exit 2, got {rc}\n{log}")

    # 5. Forbidden key (features) → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_FORBIDDEN_KEY)
    if rc != 2:
        errors.append(f"forbidden key: expected exit 2, got {rc}\n{log}")

    # 6. Empty name → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_EMPTY_NAME)
    if rc != 2:
        errors.append(f"empty name: expected exit 2, got {rc}\n{log}")

    # 7. Small window (< 50000) → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_SMALL_WINDOW)
    if rc != 2:
        errors.append(f"small window: expected exit 2, got {rc}\n{log}")

    # 8. Unknown project key → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_UNKNOWN_KEY)
    if rc != 2:
        errors.append(f"unknown key: expected exit 2, got {rc}\n{log}")

    # 9. --check → exit 0, manifest unchanged
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_VALID, ["--check"])
    if rc != 0:
        errors.append(f"--check: expected exit 0, got {rc}\n{log}")
    if 'name: "[要確認]"' not in out:
        errors.append("--check: manifest was modified (should be dry-run)")

    # 10. Idempotency: apply twice → same result
    rc1, out1, _ = _run(MANIFEST_FIXTURE, INIT_VALID)
    if rc1 != 0:
        errors.append(f"idempotency: 1st apply expected exit 0, got {rc1}")
    with tempfile.TemporaryDirectory(prefix="test-idempotent-") as tmp:
        m = Path(tmp) / "manifest.yaml"
        i = Path(tmp) / "init.yaml"
        m.write_text(out1, encoding="utf-8")
        i.write_text(INIT_VALID, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(APPLY), "--manifest", str(m), "--init", str(i)],
            check=False, capture_output=True, text=True, env=dict(os.environ),
        )
        out2 = m.read_text(encoding="utf-8")
    if out1 != out2:
        errors.append("idempotency: second apply changed manifest")
    if r.returncode != 0:
        errors.append(f"idempotency: second apply exit {r.returncode}")

    # 11. Missing tech_stack_design → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_MISSING_TSD)
    if rc != 2:
        errors.append(f"missing tsd: expected exit 2, got {rc}\n{log}")

    # 12. tech_stack_design.filename empty → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_TSD_EMPTY_FILENAME)
    if rc != 2:
        errors.append(f"tsd empty filename: expected exit 2, got {rc}\n{log}")

    # 13. tech_stack_design.filename with path traversal → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_TSD_PATH_TRAVERSAL)
    if rc != 2:
        errors.append(f"tsd path traversal: expected exit 2, got {rc}\n{log}")

    # 14. tech_stack_design.filename without .md suffix → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_TSD_NO_MD_SUFFIX)
    if rc != 2:
        errors.append(f"tsd no .md suffix: expected exit 2, got {rc}\n{log}")

    # 15. tech_stack_design unknown key → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_TSD_UNKNOWN_KEY)
    if rc != 2:
        errors.append(f"tsd unknown key: expected exit 2, got {rc}\n{log}")

    # 16. Custom filename → inserted into manifest
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_CUSTOM_FILENAME)
    if rc != 0:
        errors.append(f"custom filename: expected exit 0, got {rc}\n{log}")
    if 'tech_stack_design_filename: "MY_CUSTOM_TECH_STACK.md"' not in out:
        errors.append(f"custom filename: missing tech_stack_design_filename in manifest\n{out}")

    # 17. Insertion idempotency: apply custom filename twice → same result
    rc1, out1, _ = _run(MANIFEST_FIXTURE, INIT_CUSTOM_FILENAME)
    if rc1 != 0:
        errors.append(f"tsd idempotency: 1st apply expected exit 0, got {rc1}")
    with tempfile.TemporaryDirectory(prefix="test-tsd-idempotent-") as tmp:
        m = Path(tmp) / "manifest.yaml"
        i = Path(tmp) / "init.yaml"
        m.write_text(out1, encoding="utf-8")
        i.write_text(INIT_CUSTOM_FILENAME, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(APPLY), "--manifest", str(m), "--init", str(i)],
            check=False, capture_output=True, text=True, env=dict(os.environ),
        )
        out2 = m.read_text(encoding="utf-8")
    if out1 != out2:
        errors.append("tsd idempotency: second apply changed manifest")
    if r.returncode != 0:
        errors.append(f"tsd idempotency: second apply exit {r.returncode}")

    # 18. tech_contract.auto_approve: true → project.tech_contract_auto_approve: true
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_AUTO_APPROVE_TRUE)
    if rc != 0:
        errors.append(f"auto_approve true: expected exit 0, got {rc}\n{log}")
    if "tech_contract_auto_approve: true" not in out:
        errors.append(f"auto_approve true: missing projection\n{out}")

    # 19. tech_contract.auto_approve: false → explicit false
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_AUTO_APPROVE_FALSE)
    if rc != 0:
        errors.append(f"auto_approve false: expected exit 0, got {rc}\n{log}")
    if "tech_contract_auto_approve: false" not in out:
        errors.append(f"auto_approve false: missing projection\n{out}")

    # 20. 省略時 → false（既定）
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_VALID)
    if rc != 0:
        errors.append(f"auto_approve omit: expected exit 0, got {rc}\n{log}")
    if "tech_contract_auto_approve: false" not in out:
        errors.append(f"auto_approve omit: expected default false\n{out}")

    # 21. auto_approve が非 bool → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_AUTO_APPROVE_BAD_TYPE)
    if rc != 2:
        errors.append(f"auto_approve bad type: expected exit 2, got {rc}\n{log}")

    # 22. tech_contract 未知キー → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_AUTO_APPROVE_UNKNOWN_KEY)
    if rc != 2:
        errors.append(f"auto_approve unknown key: expected exit 2, got {rc}\n{log}")

    # 23. provisioning.auto_approve: true → project.provisioning_auto_approve: true
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_PROVISIONING_AUTO_APPROVE_TRUE)
    if rc != 0:
        errors.append(f"provisioning auto_approve true: expected exit 0, got {rc}\n{log}")
    if "provisioning_auto_approve: true" not in out:
        errors.append(f"provisioning auto_approve true: missing projection\n{out}")

    # 24. provisioning.auto_approve: false → explicit false
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_PROVISIONING_AUTO_APPROVE_FALSE)
    if rc != 0:
        errors.append(f"provisioning auto_approve false: expected exit 0, got {rc}\n{log}")
    if "provisioning_auto_approve: false" not in out:
        errors.append(f"provisioning auto_approve false: missing projection\n{out}")

    # 25. provisioning 省略時 → false（既定）
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_VALID)
    if rc != 0:
        errors.append(f"provisioning auto_approve omit: expected exit 0, got {rc}\n{log}")
    if "provisioning_auto_approve: false" not in out:
        errors.append(f"provisioning auto_approve omit: expected default false\n{out}")

    # 26. provisioning.auto_approve が非 bool → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_PROVISIONING_AUTO_APPROVE_BAD_TYPE)
    if rc != 2:
        errors.append(
            f"provisioning auto_approve bad type: expected exit 2, got {rc}\n{log}"
        )

    # 27. provisioning.auto_approve: null（明示）→ exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_PROVISIONING_AUTO_APPROVE_NULL)
    if rc != 2:
        errors.append(
            f"provisioning auto_approve null: expected exit 2, got {rc}\n{log}"
        )

    # 28. provisioning 未知キー → exit 2
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_PROVISIONING_AUTO_APPROVE_UNKNOWN_KEY)
    if rc != 2:
        errors.append(
            f"provisioning auto_approve unknown key: expected exit 2, got {rc}\n{log}"
        )

    # 29. github_access 省略時 → github_app + default service
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_MINIMAL)
    if rc != 0:
        errors.append(f"github_access default: expected exit 0, got {rc}\n{log}")
    for needle in (
        'api_credential_provider: "github_app"',
        'service: "agentic-workflow-github-api"',
        'account: ""',
    ):
        if needle not in out:
            errors.append(f"github_access default: missing {needle!r}\n{out}")

    # 30. provider=keychain → locator を root manifest へ投影
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_GITHUB_KEYCHAIN)
    if rc != 0:
        errors.append(f"github_access keychain: expected exit 0, got {rc}\n{log}")
    for needle in (
        'api_credential_provider: "keychain"',
        'service: "custom-github-service"',
        'account: "bot@example.com"',
    ):
        if needle not in out:
            errors.append(f"github_access keychain: missing {needle!r}\n{out}")

    # 31. 既存 github_access block を置換し、2回目は byte-identical
    rc, out1, log = _run(MANIFEST_WITH_GITHUB_ACCESS, INIT_GITHUB_KEYCHAIN)
    if rc != 0:
        errors.append(f"github_access update: expected exit 0, got {rc}\n{log}")
    with tempfile.TemporaryDirectory(prefix="test-github-idempotent-") as tmp:
        m = Path(tmp) / "manifest.yaml"
        i = Path(tmp) / "init.yaml"
        m.write_text(out1, encoding="utf-8")
        i.write_text(INIT_GITHUB_KEYCHAIN, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(APPLY), "--manifest", str(m), "--init", str(i)],
            check=False, capture_output=True, text=True, env=dict(os.environ),
        )
        out2 = m.read_text(encoding="utf-8")
    if r.returncode != 0 or out1 != out2:
        errors.append("github_access idempotency: second apply changed manifest or failed")

    # 32. github_access schema violations → exit 2
    for label, fixture in (
        ("bad provider", INIT_GITHUB_BAD_PROVIDER),
        ("empty keychain account", INIT_GITHUB_EMPTY_ACCOUNT),
        ("empty service", INIT_GITHUB_BAD_SERVICE),
        ("unknown key", INIT_GITHUB_UNKNOWN_KEY),
        ("bad type", INIT_GITHUB_BAD_TYPE),
        ("control character", INIT_GITHUB_CONTROL_CHAR),
    ):
        rc, _, log = _run(MANIFEST_FIXTURE, fixture)
        if rc != 2:
            errors.append(f"github_access {label}: expected exit 2, got {rc}\n{log}")

    # 33. provider=keychain で keychain block 省略 → 書き込み前に exit 2
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_GITHUB_KEYCHAIN_OMITTED)
    if rc != 2:
        errors.append(f"github_access omitted keychain: expected exit 2, got {rc}\n{log}")
    if out != MANIFEST_FIXTURE:
        errors.append("github_access omitted keychain: manifest changed before validation failed")

    # 34. github_app は空 account を許容
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_GITHUB_APP)
    if rc != 0:
        errors.append(f"github_access github_app: expected exit 0, got {rc}\n{log}")

    # 35. gen.skills（生成 skill の選択）
    errors.extend(_test_gen_skills())

    if errors:
        for e in errors:
            print(f"[test_apply_kit_init] FAIL: {e}", file=sys.stderr)
        return 1
    print("[test_apply_kit_init] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
