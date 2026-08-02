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
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
context_budget:
  min_context_window_tokens: 200000
"""

INIT_NULL_NAME = """version: 1
project:
  name: null
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
context_budget:
  min_context_window_tokens: 300000
"""

INIT_MINIMAL = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
"""

INIT_BAD_VERSION = """version: 2
project:
  name: test
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
"""

INIT_FORBIDDEN_KEY = """version: 1
project:
  name: test
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
features:
  code_review: true
"""

INIT_EMPTY_NAME = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
project:
  name: ""
"""

INIT_SMALL_WINDOW = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
context_budget:
  min_context_window_tokens: 10000
"""

INIT_UNKNOWN_KEY = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
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
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
tech_contract:
  auto_approve: true
"""

INIT_AUTO_APPROVE_FALSE = """version: 1
project:
  name: manual-approve-project
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
tech_contract:
  auto_approve: false
"""

INIT_AUTO_APPROVE_BAD_TYPE = """version: 1
project:
  name: bad-auto
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
tech_contract:
  auto_approve: "yes"
"""

INIT_AUTO_APPROVE_UNKNOWN_KEY = """version: 1
project:
  name: bad-auto
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
tech_contract:
  auto_approve: true
  extra: bad
"""

INIT_PROVISIONING_AUTO_APPROVE_TRUE = """version: 1
project:
  name: provisioning-auto-project
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
provisioning:
  auto_approve: true
"""

INIT_PROVISIONING_AUTO_APPROVE_FALSE = """version: 1
project:
  name: provisioning-manual-project
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
provisioning:
  auto_approve: false
"""

INIT_PROVISIONING_AUTO_APPROVE_BAD_TYPE = """version: 1
project:
  name: provisioning-bad-auto
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
provisioning:
  auto_approve: "yes"
"""

INIT_PROVISIONING_AUTO_APPROVE_NULL = """version: 1
project:
  name: provisioning-null-auto
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
provisioning:
  auto_approve: null
"""

INIT_PROVISIONING_AUTO_APPROVE_UNKNOWN_KEY = """version: 1
project:
  name: provisioning-bad-auto
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
provisioning:
  auto_approve: true
  extra: bad
"""

INIT_GITHUB_APP = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
github_access:
  api_credential_provider: github_app
"""

INIT_GITHUB_KEYCHAIN = """version: 1
project:
  name: github-keychain-project
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
github_access:
  api_credential_provider: keychain
  keychain:
    service: custom-github-service
    account: bot@example.com
"""

INIT_GITHUB_BAD_PROVIDER = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
github_access:
  api_credential_provider: gh
"""

INIT_GITHUB_EMPTY_ACCOUNT = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
github_access:
  api_credential_provider: keychain
  keychain:
    account: ""
"""

INIT_GITHUB_BAD_SERVICE = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
github_access:
  keychain:
    service: ""
"""

INIT_GITHUB_UNKNOWN_KEY = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
github_access:
  extra: bad
"""

INIT_GITHUB_BAD_TYPE = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
github_access: github_app
"""

INIT_GITHUB_CONTROL_CHAR = """version: 1
tech_stack_design:
  filename: TECHNOLOGY_STACK_UNIFIED_DESIGN.md
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


def main() -> int:
    errors = []

    # 1. Valid init → name / slug / workflow_pattern / tech_stack_design_filename が書き換わる
    rc, out, log = _run(MANIFEST_FIXTURE, INIT_VALID)
    if rc != 0:
        errors.append(f"valid init: expected exit 0, got {rc}\n{log}")
    for needle in ['name: "my-test-project"', 'slug: "my-test-project"',
                    'workflow_pattern: "開発型"',
                    'tech_stack_design_filename: "TECHNOLOGY_STACK_UNIFIED_DESIGN.md"']:
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

    # 33. github_app は空 account を許容
    rc, _, log = _run(MANIFEST_FIXTURE, INIT_GITHUB_APP)
    if rc != 0:
        errors.append(f"github_access github_app: expected exit 0, got {rc}\n{log}")

    if errors:
        for e in errors:
            print(f"[test_apply_kit_init] FAIL: {e}", file=sys.stderr)
        return 1
    print("[test_apply_kit_init] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
