#!/usr/bin/env python3
"""foundation.enabled: false の consumer 構成で実行可能生成物が foundation scripts に依存しないことを検査。

consumer（foundation/engine を vendor しない構成）では
.cursor/skills/agentic-workflow-foundation/scripts/ が存在しない。
executable な生成物がこのパスを無条件に参照すると、生成直後に gate が exit 2 で落ちる。
"""
from __future__ import annotations

import sys
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
TEMPLATES = SKILL_DIR / "templates"
ROOT = SKILL_DIR.parents[2]
GENLIB_DIR = ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"
if str(GENLIB_DIR) not in sys.path:
    sys.path.insert(0, str(GENLIB_DIR))

import genlib  # noqa: E402

VENDOR_ONLY_PATHS = (
    ".cursor/skills/agentic-workflow-foundation/scripts",
    ".cursor/skills/agentic-workflow-engine/scripts",
)
FOUNDATION_ONLY_OUTPUTS = ("bin/foundation-gate", "bin/project-setup")


class _AllTruthy(dict):
    """未設定キーを truthy として解決する root。foundation 以外の feature を有効扱いにする。"""

    def __contains__(self, key: object) -> bool:
        return True

    def __getitem__(self, key):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return _AllTruthy()


def _conditionals_for(text: str, *, foundation_enabled: bool) -> str:
    root = _AllTruthy(foundation={"enabled": foundation_enabled})
    return genlib._process_ifs(text, root)


def main() -> int:
    failures: list[str] = []
    manifest = genlib.load_manifest(str(SKILL_DIR / "manifest.yaml"))
    outputs = manifest.get("outputs") or []
    by_path = {out.get("path"): out for out in outputs}

    for path in FOUNDATION_ONLY_OUTPUTS:
        entry = by_path.get(path)
        if entry is None:
            failures.append(f"outputs に {path} がありません")
        elif entry.get("feature") != "foundation":
            failures.append(f"{path} に feature: foundation がありません")

    for out in outputs:
        if not out.get("executable"):
            continue
        template = out.get("template")
        if not template:
            continue
        template_path = TEMPLATES / template
        if not template_path.is_file():
            failures.append(f"テンプレート不在: {template}")
            continue
        if out.get("feature") == "foundation":
            continue
        rendered = _conditionals_for(
            template_path.read_text(encoding="utf-8"),
            foundation_enabled=False,
        )
        for vendor_path in VENDOR_ONLY_PATHS:
            if vendor_path in rendered:
                failures.append(
                    f"{out.get('path')}: foundation.enabled=false でも {vendor_path} を参照している"
                )

    quality_gate = (TEMPLATES / "bin" / "quality-gate.template").read_text(encoding="utf-8")
    enabled = _conditionals_for(quality_gate, foundation_enabled=True)
    if VENDOR_ONLY_PATHS[0] not in enabled:
        failures.append("bin/quality-gate: foundation.enabled=true で contract status 検査が消えている")
    if "bin/project-setup" not in enabled:
        failures.append("bin/quality-gate: foundation.enabled=true で preflight が消えている")
    disabled = _conditionals_for(quality_gate, foundation_enabled=False)
    if "bin/project-setup" in disabled:
        failures.append("bin/quality-gate: foundation.enabled=false で未生成の project-setup を呼んでいる")

    try:
        executable_context = {
            "foundation": {"enabled": False},
            "project": {"tech_stack_design_filename": "TECH.md"},
            "tech_contract": {
                "quality_gate": {
                    "gen": {"argv": ["true"]},
                    "build": {"argv": ["true"]},
                    "lint": {"argv": ["true"]},
                    "test": {"argv": ["true"]},
                },
            },
        }
        rendered_gate = genlib.render(quality_gate, executable_context)
        with tempfile.TemporaryDirectory(prefix="consumer-quality-gate-") as temp_dir:
            root = Path(temp_dir)
            gate = root / "bin/quality-gate"
            gate.parent.mkdir()
            gate.write_text(rendered_gate, encoding="utf-8")
            gate.chmod(0o755)
            result = subprocess.run(
                [str(gate), "verify"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                failures.append(
                    "bin/quality-gate: foundation.enabled=false の実行検証に失敗 "
                    f"(exit {result.returncode}): {result.stderr or result.stdout}"
                )
    except (OSError, genlib.RenderError) as exc:
        failures.append(f"bin/quality-gate: consumer 実生成検証不能: {exc}")

    doc_templates = (
        TEMPLATES / "hooks" / "README.md.template",
        TEMPLATES / "docs" / "references" / "context-budget-internals.md.template",
        TEMPLATES / "docs" / "QUALITY_GATE.md.template",
    )
    for path in doc_templates:
        rendered = _conditionals_for(
            path.read_text(encoding="utf-8"),
            foundation_enabled=False,
        )
        if "run_resolved_engine.py" in rendered:
            failures.append(
                f"{path.relative_to(TEMPLATES)}: foundation.enabled=false でも run_resolved_engine.py を案内している"
            )
        if VENDOR_ONLY_PATHS[0] in rendered:
            failures.append(
                f"{path.relative_to(TEMPLATES)}: foundation.enabled=false でも foundation scripts パスを案内している"
            )

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1
    print("[test_consumer_foundation_disabled] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
