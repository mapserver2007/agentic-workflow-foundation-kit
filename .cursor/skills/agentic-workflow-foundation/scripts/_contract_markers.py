"""生成テンプレートの契約マーカー検査ヘルパー。

テンプレートの「文言そのもの」ではなく「契約の存在・順序・範囲」を検査するために、
生成物へ不可視の HTML コメント `<!-- contract: <id> -->` を埋め込む。

規約:
  - ID は ``^[a-z0-9][a-z0-9-]*$``。契約 1 つにつき ID 1 つ。
  - 検査対象は **render 後の文字列**。feature 分岐の内側のマーカーは、
    分岐が無効なら出力に現れない。分岐ごとに同じ ID を付けてよい。
  - 既定の期待個数は 1。0 個・2 個以上はどちらも契約違反として扱う。
  - 「無いこと」の検査は ``require_absent`` を使う。全 feature 有効の描画
    (``reference``) に ID が存在することを前提検査し、ID の打ち間違いによる
    空振りを防ぐ。
  - 順序・範囲はマーカー間（``span``）で表現する。見出しの文言には依存しない。
  - 値を含む契約（数値・コマンド等）はマーカー化せず、値のトークンを
    ``require_tokens_on_line`` で併用する。

テストファイル名 (test_*.py) にしないこと。run_all_foundation_tests.py が
未登録の test_*.py を失敗扱いにするため。
"""
from __future__ import annotations

import copy
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

MARKER_RE = re.compile(r"<!--[ \t]*contract:[ \t]*([^ \t>]*?)[ \t]*-->")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ContractError(AssertionError):
    """契約マーカー検査の失敗。AssertionError 系として扱う。"""


@dataclass(frozen=True)
class Marker:
    id: str
    start: int
    end: int
    line_no: int


def markers(text: str) -> List[Marker]:
    """text 内の全マーカーを出現順に返す。ID 形式が不正なものは ContractError。"""
    found: List[Marker] = []
    for match in MARKER_RE.finditer(text):
        marker_id = match.group(1)
        if not ID_RE.match(marker_id):
            raise ContractError(f"契約マーカー ID の形式が不正: {marker_id!r}")
        line_no = text.count("\n", 0, match.start()) + 1
        found.append(Marker(marker_id, match.start(), match.end(), line_no))
    return found


def ids(text: str) -> List[str]:
    return [marker.id for marker in markers(text)]


def count(text: str, marker_id: str) -> int:
    return sum(1 for marker in markers(text) if marker.id == marker_id)


def _label(label: str) -> str:
    return f"{label}: " if label else ""


def require(
    text: str,
    marker_id: str,
    *,
    expected: int = 1,
    label: str = "",
) -> Marker:
    """マーカーが ``expected`` 個ちょうど存在することを要求し、最初の 1 個を返す。"""
    if not ID_RE.match(marker_id):
        raise ContractError(f"{_label(label)}契約マーカー ID の形式が不正: {marker_id!r}")
    hits = [marker for marker in markers(text) if marker.id == marker_id]
    if len(hits) != expected:
        raise ContractError(
            f"{_label(label)}契約マーカー {marker_id!r} の個数が不正: "
            f"期待 {expected} / 実際 {len(hits)}"
        )
    if expected == 0:
        raise ContractError(
            f"{_label(label)}expected=0 は require では扱わない。require_absent を使う"
        )
    return hits[0]


def require_absent(
    text: str,
    marker_id: str,
    *,
    reference: str,
    label: str = "",
) -> None:
    """text に marker_id が無いことを要求する。

    ``reference`` は全 feature 有効の描画。ここに ID が 1 個以上存在しなければ
    ID の打ち間違いとして失敗させる（空振り防止）。
    """
    if count(reference, marker_id) < 1:
        raise ContractError(
            f"{_label(label)}契約マーカー {marker_id!r} が reference に存在しない"
            "（ID の打ち間違いの可能性）"
        )
    actual = count(text, marker_id)
    if actual != 0:
        raise ContractError(
            f"{_label(label)}契約マーカー {marker_id!r} が存在してはならない: 実際 {actual} 個"
        )


def line_of(text: str, marker_id: str, *, label: str = "") -> str:
    """マーカーを含む行全体を返す（マーカーは 1 個であること）。"""
    marker = require(text, marker_id, label=label)
    start = text.rfind("\n", 0, marker.start) + 1
    end = text.find("\n", marker.end)
    if end < 0:
        end = len(text)
    return text[start:end]


def require_tokens_on_line(
    text: str,
    marker_id: str,
    tokens: Iterable[str] = (),
    *,
    forbidden: Iterable[str] = (),
    ordered: bool = False,
    label: str = "",
) -> str:
    """マーカーと同じ行に、安定トークンが存在（または不在）することを要求する。

    ``ordered=True`` のときは tokens の出現順も要求する。
    """
    line = line_of(text, marker_id, label=label)
    missing = [token for token in tokens if token not in line]
    if missing:
        raise ContractError(
            f"{_label(label)}契約 {marker_id!r} の行に必須トークンが不足: {missing}"
        )
    present = [token for token in forbidden if token in line]
    if present:
        raise ContractError(
            f"{_label(label)}契約 {marker_id!r} の行に禁止トークンが存在: {present}"
        )
    if ordered:
        positions = [line.find(token) for token in tokens]
        if positions != sorted(positions):
            raise ContractError(
                f"{_label(label)}契約 {marker_id!r} の行でトークン順序が不正: {positions}"
            )
    return line


def require_order(
    text: str,
    marker_ids: Sequence[str],
    *,
    label: str = "",
) -> List[Marker]:
    """各 ID がちょうど 1 個あり、指定順に並ぶことを要求する。"""
    resolved = [require(text, marker_id, label=label) for marker_id in marker_ids]
    starts = [marker.start for marker in resolved]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise ContractError(f"{_label(label)}契約マーカーの順序が不正: {list(marker_ids)} -> {starts}")
    return resolved


def span(
    text: str,
    start_id: str,
    end_id: Optional[str] = None,
    *,
    label: str = "",
) -> str:
    """start マーカー直後から end マーカー直前までの本文を返す。

    ``end_id`` が None のときは文末まで。start が end より後ろにある場合は失敗。
    """
    start = require(text, start_id, label=label)
    if end_id is None:
        return text[start.end :]
    end = require(text, end_id, label=label)
    if end.start < start.end:
        raise ContractError(
            f"{_label(label)}契約マーカーの範囲が逆転: {start_id!r} -> {end_id!r}"
        )
    return text[start.end : end.start]


def require_in_span(
    text: str,
    outer: str,
    inner: str,
    *,
    end_outer: str,
    label: str = "",
) -> None:
    """inner マーカーが [outer, end_outer) の範囲内にあることを要求する。"""
    body = span(text, outer, end_outer, label=label)
    if count(body, inner) != 1:
        raise ContractError(
            f"{_label(label)}契約マーカー {inner!r} が範囲 {outer!r}..{end_outer!r} の内側に"
            f"1 個ありません（実際 {count(body, inner)} 個）"
        )


# --- render ヘルパー --------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_SKILL_DIR = _HERE.parent
_ROOT = _SKILL_DIR.parent.parent.parent
_ENGINE_SCRIPTS = _ROOT / ".cursor" / "skills" / "agentic-workflow-engine" / "scripts"


def render_template(path: Path, overrides: Optional[Dict[str, Any]] = None) -> str:
    """テンプレートを seed manifest で render する。

    ``overrides`` は ``{"code_review.enabled": False}`` のようなドット区切りキーで
    feature を切り替える。マーカーは feature 分岐を処理した後の出力に対して検査する。
    """
    if str(_ENGINE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_ENGINE_SCRIPTS))
    from genlib import load_manifest, render  # noqa: WPS433

    context = copy.deepcopy(load_manifest(str(_SKILL_DIR / "manifest.yaml")))
    for dotted, value in (overrides or {}).items():
        node = context
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    return render(Path(path).read_text(encoding="utf-8"), context)
