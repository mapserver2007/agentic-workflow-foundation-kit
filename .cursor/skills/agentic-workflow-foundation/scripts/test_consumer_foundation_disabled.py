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
            syntax = subprocess.run(
                ["bash", "-n", str(gate)],
                capture_output=True,
                text=True,
                check=False,
            )
            if syntax.returncode != 0:
                failures.append(
                    "bin/quality-gate: 展開後スクリプトの bash -n に失敗 "
                    f"{syntax.stderr or syntax.stdout}"
                )
    except (OSError, genlib.RenderError) as exc:
        failures.append(f"bin/quality-gate: consumer 実生成検証不能: {exc}")

    def _render_quality_gate(argv: list[str]) -> str:
        return genlib.render(
            quality_gate,
            {
                "foundation": {"enabled": False},
                "project": {"tech_stack_design_filename": "TECH.md"},
                "tech_contract": {
                    "quality_gate": {
                        "gen": {"argv": argv},
                        "build": {"argv": argv},
                        "lint": {"argv": argv},
                        "test": {"argv": argv},
                    },
                },
            },
        )

    try:
        with tempfile.TemporaryDirectory(prefix="consumer-quality-gate-cwd-") as temp_dir:
            root = Path(temp_dir)
            outside = root / "outside"
            outside.mkdir()
            log = root / "backend.log"
            backend = root / "bin" / "backend-stub"
            backend.parent.mkdir()
            backend.write_text(
                "#!/usr/bin/env bash\n"
                f"pwd >> {str(log)!r}\n",
                encoding="utf-8",
            )
            backend.chmod(0o755)
            gate = root / "bin" / "quality-gate"
            gate.write_text(
                _render_quality_gate(["bin/backend-stub"]),
                encoding="utf-8",
            )
            gate.chmod(0o755)
            result = subprocess.run(
                [str(gate), "verify"],
                cwd=outside,
                capture_output=True,
                text=True,
                check=False,
            )
            observed = [
                str(Path(line).resolve())
                for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else [])
            ]
            if result.returncode != 0 or observed != [str(root.resolve())] * 3:
                failures.append(
                    "bin/quality-gate: 非 root cwd から root 相対 backend を実行できない "
                    f"(exit {result.returncode}, pwd={observed}): "
                    f"{result.stderr or result.stdout}"
                )

            missing = root / "bin" / "quality-gate-missing"
            missing.write_text(
                _render_quality_gate(["bin/missing-backend"]),
                encoding="utf-8",
            )
            missing.chmod(0o755)
            missing_result = subprocess.run(
                [str(missing), "verify"],
                cwd=outside,
                capture_output=True,
                text=True,
                check=False,
            )
            if missing_result.returncode != 2 or "backend command not found" not in missing_result.stderr:
                failures.append(
                    "bin/quality-gate: backend 不在が exit 2 になっていない "
                    f"(exit {missing_result.returncode}): "
                    f"{missing_result.stderr or missing_result.stdout}"
                )
    except (OSError, genlib.RenderError) as exc:
        failures.append(f"bin/quality-gate: cwd 回帰検証不能: {exc}")

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

    def _render_verify_steps(
        build: list[str],
        lint: list[str],
        test: list[str],
        gen: list[str] | None = None,
    ) -> str:
        return genlib.render(
            quality_gate,
            {
                "foundation": {"enabled": False},
                "project": {"tech_stack_design_filename": "TECH.md"},
                "tech_contract": {
                    "quality_gate": {
                        "gen": {"argv": gen if gen is not None else ["true"]},
                        "build": {"argv": build},
                        "lint": {"argv": lint},
                        "test": {"argv": test},
                    },
                },
            },
        )

    try:
        with tempfile.TemporaryDirectory(prefix="consumer-quality-gate-make-") as temp_dir:
            root = Path(temp_dir)
            log = root / "steps.log"
            makefile = root / "Makefile"
            gate = root / "bin" / "quality-gate"
            gate.parent.mkdir()

            makefile.write_text(
                "lint:\n"
                f"\tprintf 'lint\\n' >> {log}\n"
                "test:\n"
                f"\tprintf 'test\\n' >> {log}\n",
                encoding="utf-8",
            )
            gate.write_text(
                _render_verify_steps(["make", "build"], ["make", "lint"], ["make", "test"]),
                encoding="utf-8",
            )
            gate.chmod(0o755)
            skipped = subprocess.run(
                [str(gate), "verify"], cwd=root, capture_output=True, text=True, check=False
            )
            skipped_log = log.read_text(encoding="utf-8") if log.exists() else ""
            if (
                skipped.returncode != 0
                or "SKIP: make target 'build'" not in skipped.stdout
                or skipped_log != "lint\ntest\n"
            ):
                failures.append(
                    "bin/quality-gate: 無い make ターゲットを省略できていない "
                    f"(exit {skipped.returncode}, log={skipped_log!r}): "
                    f"{skipped.stdout}{skipped.stderr}"
                )

            log.unlink(missing_ok=True)
            makefile.unlink()
            no_makefile = subprocess.run(
                [str(gate), "verify"], cwd=root, capture_output=True, text=True, check=False
            )
            if no_makefile.returncode != 0 or no_makefile.stdout.count("SKIP:") != 3:
                failures.append(
                    "bin/quality-gate: Makefile 自体が無い場合をターゲット不在として省略できていない "
                    f"(exit {no_makefile.returncode}): "
                    f"{no_makefile.stdout}{no_makefile.stderr}"
                )

            log.unlink(missing_ok=True)
            makefile.write_text(
                "build:\n"
                f"\tprintf 'build\\n' >> {log}\n"
                "\texit 1\n"
                "lint:\n"
                f"\tprintf 'lint\\n' >> {log}\n",
                encoding="utf-8",
            )
            failed = subprocess.run(
                [str(gate), "verify"], cwd=root, capture_output=True, text=True, check=False
            )
            failed_log = log.read_text(encoding="utf-8") if log.exists() else ""
            if failed.returncode == 0 or failed_log != "build\n" or "SKIP:" in failed.stdout:
                failures.append(
                    "bin/quality-gate: 実在ターゲットの失敗で停止できていない "
                    f"(exit {failed.returncode}, log={failed_log!r}): "
                    f"{failed.stdout}{failed.stderr}"
                )

            log.unlink(missing_ok=True)
            makefile.write_text(
                "build: missing-dep\n"
                f"\tprintf 'build\\n' >> {log}\n",
                encoding="utf-8",
            )
            dependency = subprocess.run(
                [str(gate), "verify"], cwd=root, capture_output=True, text=True, check=False
            )
            if dependency.returncode == 0 or "SKIP:" in dependency.stdout:
                failures.append(
                    "bin/quality-gate: 依存欠落をターゲット不在として省略した "
                    f"(exit {dependency.returncode}): {dependency.stdout}{dependency.stderr}"
                )

            # 単体サブコマンド（gen / build / lint / test）も、対象 make ターゲットが
            # 無ければエラーにせず SKIP して exit 0 とする。実在して失敗した段は失敗のまま。
            gate.write_text(
                _render_verify_steps(
                    ["make", "build"],
                    ["make", "lint"],
                    ["make", "test"],
                    gen=["make", "gen"],
                ),
                encoding="utf-8",
            )
            gate.chmod(0o755)
            log.unlink(missing_ok=True)
            makefile.write_text(
                "lint:\n"
                "\texit 1\n",
                encoding="utf-8",
            )
            for sub in ("gen", "build", "test"):
                single = subprocess.run(
                    [str(gate), sub], cwd=root, capture_output=True, text=True, check=False
                )
                if single.returncode != 0 or f"SKIP: make target '{sub}'" not in single.stdout:
                    failures.append(
                        f"bin/quality-gate {sub}: 無い make ターゲットを SKIP して exit 0 にできていない "
                        f"(exit {single.returncode}): {single.stdout}{single.stderr}"
                    )
            single_failed = subprocess.run(
                [str(gate), "lint"], cwd=root, capture_output=True, text=True, check=False
            )
            if single_failed.returncode == 0 or "SKIP:" in single_failed.stdout:
                failures.append(
                    "bin/quality-gate lint: 実在ターゲットの失敗を省略した "
                    f"(exit {single_failed.returncode}): {single_failed.stdout}{single_failed.stderr}"
                )

            makefile.unlink()
            for sub in ("gen", "build", "lint", "test"):
                single_no_makefile = subprocess.run(
                    [str(gate), sub], cwd=root, capture_output=True, text=True, check=False
                )
                if (
                    single_no_makefile.returncode != 0
                    or f"SKIP: make target '{sub}'" not in single_no_makefile.stdout
                ):
                    failures.append(
                        f"bin/quality-gate {sub}: Makefile 自体が無い場合を SKIP して exit 0 にできていない "
                        f"(exit {single_no_makefile.returncode}): "
                        f"{single_no_makefile.stdout}{single_no_makefile.stderr}"
                    )
    except (OSError, genlib.RenderError) as exc:
        failures.append(f"bin/quality-gate: make ターゲット省略の検証不能: {exc}")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1
    print("[test_consumer_foundation_disabled] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
