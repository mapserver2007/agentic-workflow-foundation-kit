#!/usr/bin/env python3
"""_contract_markers.py の自動変異テスト。

マーカー検査が「保証すべき違反」を実際に検出できることを確かめる。
検査が空振りすると、テンプレート側の契約が壊れても気づけないため。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import _contract_markers as cm  # noqa: E402

BASE = """\
# 見出し

<!-- contract: section-a -->
## A

- 項目 `workflow-gate.sh step5` を実行する <!-- contract: rerun-after-change -->
- 本文 <!-- contract: approval-step -->

<!-- contract: section-b -->
## B
"""


def _raises(func, *args, **kwargs) -> bool:
    try:
        func(*args, **kwargs)
    except cm.ContractError:
        return True
    return False


def test_baseline_passes() -> None:
    cm.require(BASE, "section-a")
    cm.require_order(BASE, ("section-a", "rerun-after-change", "section-b"))
    cm.require_tokens_on_line(BASE, "rerun-after-change", ("step5",))
    cm.require_in_span(BASE, "section-a", "rerun-after-change", end_outer="section-b")
    assert "approval-step" in cm.ids(cm.span(BASE, "section-a", "section-b"))


def test_marker_deleted_fails() -> None:
    mutated = BASE.replace("<!-- contract: rerun-after-change -->", "")
    assert _raises(cm.require, mutated, "rerun-after-change")
    assert _raises(cm.require_order, mutated, ("section-a", "rerun-after-change", "section-b"))


def test_marker_duplicated_fails() -> None:
    mutated = BASE + "- 重複 <!-- contract: rerun-after-change -->\n"
    assert _raises(cm.require, mutated, "rerun-after-change")
    assert cm.count(mutated, "rerun-after-change") == 2


def test_marker_moved_to_other_section_fails() -> None:
    marker = "<!-- contract: rerun-after-change -->"
    mutated = BASE.replace(marker, "") + f"- 移動先 {marker}\n"
    assert _raises(
        cm.require_in_span, mutated, "section-a", "rerun-after-change", end_outer="section-b"
    )


def test_body_deleted_marker_left_fails() -> None:
    mutated = BASE.replace("`workflow-gate.sh step5` を実行する", "")
    assert _raises(cm.require_tokens_on_line, mutated, "rerun-after-change", ("step5",))


def test_forbidden_token_on_line_fails() -> None:
    mutated = BASE.replace("本文", "PO承認 本文")
    assert _raises(cm.require_tokens_on_line, mutated, "approval-step", forbidden=("PO承認",))


def test_order_inversion_fails() -> None:
    assert _raises(cm.require_order, BASE, ("section-b", "section-a"))
    assert _raises(cm.span, BASE, "section-b", "section-a")


def test_absent_check_with_typo_id_fails() -> None:
    disabled = BASE.replace("<!-- contract: approval-step -->", "")
    # 正しい ID: reference に存在し、disabled には無い -> PASS
    cm.require_absent(disabled, "approval-step", reference=BASE)
    # 打ち間違い ID: reference に存在しないので空振りせず失敗する
    assert _raises(cm.require_absent, disabled, "aproval-step", reference=BASE)
    # 無いはずのマーカーが残っていれば失敗する
    assert _raises(cm.require_absent, BASE, "approval-step", reference=BASE)


def test_invalid_id_format_fails() -> None:
    assert _raises(cm.markers, "<!-- contract: Bad_ID -->")
    assert _raises(cm.require, BASE, "Bad_ID")
    assert _raises(cm.markers, "<!-- contract:  -->")


def test_whitespace_variants_are_equivalent() -> None:
    assert cm.ids("<!--contract:abc-->\n<!--   contract:   def   -->") == ["abc", "def"]


def main() -> int:
    tests = [
        test_baseline_passes,
        test_marker_deleted_fails,
        test_marker_duplicated_fails,
        test_marker_moved_to_other_section_fails,
        test_body_deleted_marker_left_fails,
        test_forbidden_token_on_line_fails,
        test_order_inversion_fails,
        test_absent_check_with_typo_id_fails,
        test_invalid_id_format_fails,
        test_whitespace_variants_are_equivalent,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL: {test.__name__}: {exc}", file=sys.stderr)
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {test.__name__}: {exc}", file=sys.stderr)
            failed += 1
    print(f"[test_contract_markers] {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
