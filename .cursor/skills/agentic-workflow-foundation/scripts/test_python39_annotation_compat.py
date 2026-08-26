#!/usr/bin/env python3
"""Python 3.9 における生成 gate の型注釈互換性を検査する。"""
from __future__ import annotations

import importlib.util
import py_compile
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent.parent
TEMPLATES_DIR = HERE.parent / "templates"
GATES_DIR = ROOT / ".cursor" / "skills" / "session-handover" / "scripts"
GATE_NAMES = (
    "gate-artifact.py",
    "gate-report.py",
    "gate-redispatch.py",
    "gate-adr.py",
    "gate-maintenance-docs.py",
    "gate-domain-write-scope.py",
)
IMPORT_ONLY_MODULES = ("domain_doc_scope.py",)
FUTURE_IMPORT = "from __future__ import annotations"


def check_template_future_imports() -> None:
    """全 Python template が shebang 直後に future import を置くことを確認する。"""
    templates = sorted(TEMPLATES_DIR.rglob("*.py.template"))
    assert templates, "Python template が見つかりません"
    for template in templates:
        lines = template.read_text(encoding="utf-8").splitlines()
        if not lines or not lines[0].startswith("#!"):
            continue  # import-only library templates (domain_doc_scope.py.template 等)
        head = lines[1:6]
        assert FUTURE_IMPORT in head, (
            f"shebang 直後 5 行以内に future import がありません: {template}"
        )


def import_generated_gates() -> None:
    """生成済み gate を importlib で実行時ロードする（ERR-003 の主検査）。"""
    scripts_dir = str(GATES_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    for module_name in IMPORT_ONLY_MODULES:
        module_path = GATES_DIR / module_name
        assert module_path.is_file(), f"生成済み module がありません: {module_path}"
        spec = importlib.util.spec_from_file_location(
            "python39_annotation_compat_" + module_name.replace("-", "_").replace(".", "_"),
            str(module_path),
        )
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
    for gate_name in GATE_NAMES:
        gate_path = GATES_DIR / gate_name
        assert gate_path.is_file(), f"生成済み gate がありません: {gate_path}"
        module_name = "python39_annotation_compat_" + gate_name.replace("-", "_").replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name, str(gate_path))
        assert spec is not None and spec.loader is not None, (
            f"import spec を作成できません: {gate_path}"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


def compile_generated_gates() -> None:
    """生成済み gate を py_compile する補助検査。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        for gate_name in (*IMPORT_ONLY_MODULES, *GATE_NAMES):
            gate_path = GATES_DIR / gate_name
            py_compile.compile(
                str(gate_path),
                cfile=str(output_dir / (gate_name + "c")),
                doraise=True,
            )


def main() -> int:
    checks = (
        ("template future import", check_template_future_imports),
        ("generated gate import smoke", import_generated_gates),
        ("generated gate py_compile (supplemental)", compile_generated_gates),
    )
    for label, check in checks:
        try:
            check()
        except Exception:
            print(f"[FAIL] {label}", file=sys.stderr)
            traceback.print_exc()
            return 1
        print(f"[PASS] {label}")
    print("[PASS] Python 3.9 annotation compatibility")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
