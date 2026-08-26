#!/usr/bin/env python3
"""Step② Domain docs 書込み契約の回帰テスト。"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parent.parent.parent
sys.path.insert(0, str(ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"))
from genlib import load_manifest, render  # noqa: E402


def _load():
    manifest = load_manifest(str(SKILL / "manifest.yaml"))
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        for name in ("domain_doc_scope.py", "gate_report.py"):
            source = SKILL / "templates/skills/session-handover/scripts" / (
                "domain_doc_scope.py.template" if name == "domain_doc_scope.py" else "gate-report.py.template"
            )
            (target / name).write_text(render(source.read_text(encoding="utf-8"), manifest), encoding="utf-8")
        sys.path.insert(0, str(target))
        spec = importlib.util.spec_from_file_location("gate_report_doc_scope", target / "gate_report.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


BASE = """\
## 1. タスクの概要
## 2. 問題・要件の詳細
### 受入条件
- AC-001: source を変更する
## 3. 原因・背景
## 4. 影響範囲
## 5. 実装方針
- **参照ドキュメント**: `docs/spec.md`
## 6. コード変更の詳細
| 変更対象ファイル | 変更箇所 | 変更内容 |
| --- | --- | --- |
| src/main.py | main | 変更 |
## 7. テスト計画
## 8. 関連する既存コード
- docs/spec.md
## 9. 追加調査が必要な項目
## 10. 完了チェック
"""


def _ids(text: str) -> set[str]:
    module = _load()
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "T.md"
        step1 = Path(td) / "T--step1.md"
        step1.write_text("---\ncampaign_slug: T\nrequirements_digest: " + "a" * 64 + "\n---\n", encoding="utf-8")
        report.write_text(text, encoding="utf-8")
        result = module.check_report(str(report), str(step1))
    return {item["id"] for item in result["checks"] if item["status"] == "FAIL"}


def test_section6_and_ambiguous_fail():
    assert "G-REPORT-DOC-SCOPE-001" in _ids(BASE.replace("src/main.py", "docs/spec.md"))
    assert "G-REPORT-DOC-SCOPE-001" in _ids(BASE.replace("src/main.py", "docs/spec.md, docs/api.md"))


def test_plan_write_and_ac_fail_but_reference_passes():
    assert "G-REPORT-DOC-SCOPE-001" in _ids(BASE.replace("## 6.", "- docs/spec.md を更新する\n## 6."))
    assert "G-REPORT-DOC-SCOPE-001" in _ids(BASE.replace("## 6.", "- docs/spec.md を replace する\n## 6."))
    assert "G-REPORT-DOC-SCOPE-001" in _ids(BASE.replace("source を変更する", "docs/spec.md を更新する"))
    assert "G-REPORT-DOC-SCOPE-001" in _ids(BASE.replace("source を変更する", "docs/spec.md は maintenance-docs/ に起票しない"))
    assert "G-REPORT-DOC-SCOPE-001" in _ids(BASE.replace("source を変更する", "docs/spec.md の反映は後続 maintenance-docs-workflow が実施しない"))
    assert "G-REPORT-DOC-SCOPE-001" in _ids(BASE.replace("source を変更する", "docs/spec.md は maintenance-docs/ を参照する"))
    assert "G-REPORT-DOC-SCOPE-001" not in _ids(BASE)
    allowed = BASE.replace(
        "source を変更する",
        "docs/spec.md の反映は後続 maintenance-docs-workflow が実施する",
    )
    assert "G-REPORT-DOC-SCOPE-001" not in _ids(allowed)


def main() -> int:
    tests = [test_section6_and_ambiguous_fail, test_plan_write_and_ac_fail_but_reference_passes]
    for test in tests:
        test()
    print(f"[test_gate_report_doc_scope] {len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
