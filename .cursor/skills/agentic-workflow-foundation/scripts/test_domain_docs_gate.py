#!/usr/bin/env python3
"""domain_docs_gate.py（G-DOCFILL-*）と、別アプリの fixture で apply とゲートを通す一般性を検査する。

fixture は `fixtures/domain-docs/library/`（図書館の貸出管理。設計書、手書きの参照結果、期待 findings）。
subagent の起案そのものは CI の対象外で、決定論の部分（apply の検証とゲート）だけを検査する。
"""
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
import domain_docs_apply as da  # noqa: E402
import domain_docs_gate as gate  # noqa: E402
import genlib  # noqa: E402

FIXTURE = HERE.parent / "fixtures" / "domain-docs" / "library"
# domain_docs_apply は Design Doc を自動検知しない。テストでは PO が選んだ体で、このパスを明示する。
DOC_PATH = Path("designs/docs/designdoc.md")

# 設計書の標準構造を持つ、最小の Design Doc。
DESIGN = """\
# 概要

説明。

# 業務フロー

## 1. 登録

### 1-1. 受付

## 2. 提出

```md
## fenced is not a heading
```

# 設計

## API設計

| API | メソッドとパス | 呼び元 |
| --- | --- | --- |
| 登録 | `POST /things` | 端末 |
| 取得 | `GET /things/{thing_id}` | 端末 |
| 更新 | `PUT /things/{thing_id}/state` | 端末 |

## データベース設計

### things（もの）

| 列 | 型 | NULL | キー | 内容 |
| --- | --- | --- | --- | --- |
| thing_id | BIGINT | NO | PK | もの |
| label | VARCHAR(10) | NO | | 表示名 |

### parts（部品）

| 列 | 型 | NULL | キー | 内容 |
| --- | --- | --- | --- | --- |
| part_id | BIGINT | NO | PK | 部品 |

### 画面との対応

| 画面の項目 | 参照 |
| --- | --- |
| 表示名 | `things.label` |

## UML

```mermaid
sequenceDiagram
    A->>B: x
```

```mermaid
sequenceDiagram
    B->>A: y
```

```mermaid
stateDiagram-v2
    [*] --> S1
```

失敗は `already_taken` を返す。`thing_id` は列名。`GET /things` は文中の例。
"""


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect(exc_type: type, label: str, fn) -> Exception:
    try:
        fn()
    except exc_type as exc:
        return exc
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"{label}: expected {exc_type.__name__}, got {type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"{label}: {exc_type.__name__} was not raised")


def _ids(report: gate.Report, level: str | None = None) -> list[str]:
    return [item["id"] for item in report.findings if level is None or item["level"] == level]


# --------------------------------------------------------------------------
def test_design_doc_extraction() -> None:
    _assert(gate.business_flow_children(DESIGN) == ["1. 登録", "2. 提出"],
            f"business flow children wrong: {gate.business_flow_children(DESIGN)}")
    _assert(gate.business_flow_children("# 概要\n\n## 業務\n") == [], "missing 業務フロー must be empty")
    tables = gate.design_tables(DESIGN)
    _assert(tables == [("things", ["thing_id", "label"]), ("parts", ["part_id"])], f"tables wrong: {tables}")
    _assert(gate.design_tables("# 概要\n") == [], "no database heading must be empty")
    endpoints = gate.design_endpoints(DESIGN)
    _assert(endpoints == [("POST", "/things"), ("GET", "/things/{thing_id}"), ("PUT", "/things/{thing_id}/state")],
            f"endpoints wrong: {endpoints}")
    _assert(gate.design_endpoints("# 概要\n") == [], "no API heading must be empty")
    _assert(gate.diagram_counts(DESIGN) == {"sequenceDiagram": 2, "stateDiagram": 1},
            f"diagram counts wrong: {gate.diagram_counts(DESIGN)}")
    # コードフェンス内の見出しは見出しとして数えない。表も同様。
    headings = [item.text for item in gate.parse_headings(DESIGN)]
    _assert("fenced is not a heading" not in headings, "fenced heading registered")
    fenced = "```text\n| a | b |\n| --- | --- |\n| x | y |\n```\n"
    lines = fenced.splitlines()
    _assert(gate.parse_tables(lines, gate.fence_mask(lines), 0, len(lines)) == [], "fenced table registered")
    identifiers = gate.design_identifiers(DESIGN)
    _assert(identifiers == {"already_taken", "thing_id"}, f"identifiers wrong: {identifiers}")
    hits = gate.contract_vocabulary_hits(DESIGN, ["規約だけを述べる。", "失敗は already_taken とする。"])
    _assert(hits == ["already_taken"], f"vocabulary hits wrong: {hits}")
    _assert(gate.contract_vocabulary_hits(DESIGN, ["not_already_taken_x"]) == [], "partial identifier matched")


def test_residue_is_a_fail() -> None:
    clean = gate.evaluate(DESIGN, replaced={"docs/a.md#x": "本文。\n\n```text\n[TODO] フェンス内は見本\n```"},
                          final_texts={}, spec_documents={})
    _assert("G-DOCFILL-001" not in _ids(clean), f"fenced TODO must not fail: {clean.findings}")
    for label, body in (
        ("todo", "本文\n\n[TODO] 後で書く"),
        ("er sample", "```mermaid\nerDiagram\n    ENTITY_A ||--o{ ENTITY_B : has\n```"),
        ("sequence sample", "```mermaid\nsequenceDiagram\n    Client->>API: リクエスト\n```"),
        ("state sample", "```mermaid\nstateDiagram-v2\n    Created --> Processing\n```"),
        ("component sample", "```mermaid\ngraph TB\n    A[コンポーネント A]\n```"),
    ):
        report = gate.evaluate(DESIGN, replaced={"docs/a.md#x": body}, final_texts={}, spec_documents={})
        _assert(report.fails and _ids(report, "FAIL") == ["G-DOCFILL-001"], f"{label}: FAIL expected: {report.findings}")
        _assert(report.to_dict()["status"] == "FAIL", f"{label}: status")
        if label == "todo":
            continue
        # Design Doc に同じパターンがある遷移は、設計書の語として持ち込む。
        transcribed = gate.evaluate(
            DESIGN + "\n" + body, replaced={"docs/a.md#x": body}, final_texts={}, spec_documents={}
        )
        _assert(not transcribed.fails, f"{label}: design doc pattern must not fail: {transcribed.findings}")
    # 別の雛形が Design Doc にあっても、本文側の別パターンは FAIL のまま。
    other = gate.evaluate(
        DESIGN + "\nCreated --> Processing\n",
        replaced={"docs/a.md#x": "ENTITY_A"},
        final_texts={},
        spec_documents={},
    )
    _assert(other.fails and "ER 図の雛形名" in other.findings[0]["message"], f"other sample: {other.findings}")
    # `[TODO]` は Design Doc にあっても FAIL のまま。
    todo = gate.evaluate(
        DESIGN + "\n[TODO] 設計書側\n",
        replaced={"docs/a.md#x": "本文\n\n[TODO] 後で書く"},
        final_texts={},
        spec_documents={},
    )
    _assert(todo.fails and "TODO" in todo.findings[0]["message"], f"TODO must still fail: {todo.findings}")


def test_structural_warnings_and_skips() -> None:
    api = "| POST | `/things` |\n| GET | `/things/{thing_id}` |\n| PUT | `/things/{thing_id}/state` |"
    data_models = "things と parts。列: thing_id, label, part_id。"
    workflows = (
        "```mermaid\nsequenceDiagram\n    A->>B: x\n```\n\n"
        "```mermaid\nsequenceDiagram\n    B->>A: y\n```\n\n"
        "```mermaid\nstateDiagram-v2\n    [*] --> S1\n```\n"
    )
    full = {gate.API_FILE: api, gate.DATA_MODELS_FILE: data_models, gate.WORKFLOWS_FILE: workflows}
    ok = gate.evaluate(DESIGN, replaced={}, final_texts=full,
                       spec_documents={"docs/spec/a.md": "## 概要\n\n本文\n\n## エラーハンドリング\n\n本文"})
    _assert(not ok.findings and not ok.skipped, f"complete docs must pass: {ok.findings} {ok.skipped}")
    _assert(ok.metrics["diagrams"]["sequenceDiagram"] == {"design": 2, "docs": 2}, f"metrics: {ok.metrics}")
    _assert(ok.metrics["tables"] == {"design": 2, "missing": 0}, f"table metrics: {ok.metrics}")
    _assert(ok.metrics["endpoints"] == {"design": 3, "missing": 0}, f"endpoint metrics: {ok.metrics}")

    def variant(**changes):
        texts = dict(full)
        texts.update(changes)
        return gate.evaluate(DESIGN, replaced={}, final_texts=texts, spec_documents={})

    # 図が足りない（本数は設計書以上が必要）。
    report = variant(**{gate.WORKFLOWS_FILE: workflows.split("```mermaid\nstateDiagram")[0]})
    _assert(_ids(report) == ["G-DOCFILL-002"] and "stateDiagram" in report.findings[0]["message"],
            f"missing state diagram: {report.findings}")
    _assert(report.findings[0]["level"] == "WARN", "diagram finding must be WARN")
    # テーブルと列。
    report = variant(**{gate.DATA_MODELS_FILE: "things のみ。列は thing_id。"})
    messages = " ".join(item["message"] for item in report.findings)
    _assert(_ids(report) == ["G-DOCFILL-003"] * 2 and "parts" in messages and "label" in messages,
            f"missing table/columns: {report.findings}")
    # エンドポイントは、メソッドとパスが同じ行にあることを求める。長いパスの前置は別物。
    report = variant(**{gate.API_FILE: "| POST | `/things` |\n| GET | `/things/{thing_id}/state` |\n| PUT | `/things/{thing_id}/state` |"})
    _assert(_ids(report) == ["G-DOCFILL-004"] and "GET /things/{thing_id}" in report.findings[0]["message"],
            f"endpoint must need its own line: {report.findings}")
    report = variant(**{gate.API_FILE: "POST `/things/{thing_id}`\nGET `/things/{thing_id}`\nPUT `/things/{thing_id}/state`"})
    _assert("POST /things" in report.findings[0]["message"], f"prefix path must not satisfy POST /things: {report.findings}")
    _assert(gate._endpoint_present("GET", "/books", "GET /books"), "exact path")
    _assert(gate._endpoint_present("GET", "/books", "GET `/books`"), "code span path")
    _assert(not gate._endpoint_present("GET", "/books", "GET /v2/books"), "suffix path must not satisfy")
    _assert(not gate._endpoint_present("GET", "/books", "GET `/v2/books`"), "suffix path in a span must not satisfy")
    # 機能仕様の必須見出し。コードフェンス内は数えない。
    report = gate.evaluate(DESIGN, replaced={}, final_texts=full, spec_documents={
        "docs/spec/a.md": "## 概要\n\n本文",
        "docs/spec/b.md": "## 概要\n\n```md\n## エラーハンドリング\n```\n",
        "docs/spec/c.md": "## 概要\n\n## エラーハンドリング\n\n本文",
    })
    _assert([item["file"] for item in report.findings] == ["docs/spec/a.md", "docs/spec/b.md"],
            f"error handling findings wrong: {report.findings}")

    # 標準の見出し構造を持たない設計書では、抽出できない検査は skipped になる。
    plain = gate.evaluate("# 概要\n\n本文\n", replaced={}, final_texts=full, spec_documents={})
    _assert(not plain.findings, f"plain design doc must not warn: {plain.findings}")
    _assert({item["id"] for item in plain.skipped} == {
        "G-DOCFILL-002", "G-DOCFILL-003", "G-DOCFILL-004", "G-DOCFILL-005"}, f"skips wrong: {plain.skipped}")
    _assert(all(item["reason"] for item in plain.skipped), "skip reason missing")
    # 書込み先の docs が無いときも skipped。
    missing = gate.evaluate(DESIGN, replaced={}, final_texts={}, spec_documents={})
    _assert(not missing.findings and {item["id"] for item in missing.skipped} >= {
        "G-DOCFILL-002", "G-DOCFILL-003", "G-DOCFILL-004"}, f"missing docs skips wrong: {missing.skipped}")


# --------------------------------------------------------------------------
# 別アプリ（図書館の貸出管理・別スタック）の fixture
# --------------------------------------------------------------------------
LIBRARY_MANIFEST = {
    # architecture.md.template の束縛節が、ブループリントのファイル名を参照する。
    "project": {"tech_stack_design_filename": "LIBRARY_BLUEPRINT.md"},
    "domain_docs": {
        "primary_language": "TypeScript",
        "framework": "NestJS",
        "architecture": "Layered",
        "api_style": "REST/JSON",
        "database": "PostgreSQL",
        "api_sections": [{"title": "REST 規約", "guidance": "技術規約の引用。"}],
        "data_model_sections": [
            {"title": "型と識別子", "guidance": "技術規約の引用。"},
            {"title": "トランザクションの方式", "guidance": "技術規約の引用。"},
        ],
        "workflow_sections": [{"title": "ローカル開発", "guidance": "技術規約の引用。"}],
    }
}
LIBRARY_TITLES = {
    "docs/api.md": frozenset({"REST 規約"}),
    "docs/data-models.md": frozenset({"型と識別子", "トランザクションの方式"}),
    "docs/workflows.md": frozenset({"ローカル開発"}),
}


def _library_skeletons() -> dict[str, str]:
    skeletons = {}
    for rel in da.OWNERSHIP:
        template = (da.TEMPLATES_DIR / f"{rel}.template").read_text(encoding="utf-8")
        skeletons[rel] = genlib.render(template, LIBRARY_MANIFEST)
    return skeletons


def _library_repo(base: Path, skeletons: dict[str, str], name: str) -> Path:
    root = base / name
    (root / "designs/docs").mkdir(parents=True)
    (root / DOC_PATH).write_text((FIXTURE / "designdoc.md").read_text(encoding="utf-8"), encoding="utf-8")
    (root / "manifest.yaml").write_text("project:\n  name: library\n", encoding="utf-8")
    for rel, text in skeletons.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _library_plan(root: Path, skeletons: dict[str, str], result: dict):
    targets = da.build_targets(
        root, root / "manifest.yaml", skeletons, root / DOC_PATH, refresh=False, titles=LIBRARY_TITLES)
    return targets, da.build_plan(
        root, root / "manifest.yaml", skeletons, targets, result, refresh=False, titles=LIBRARY_TITLES)


def _body(result: dict, file: str, heading: str) -> dict:
    return next(s for s in result["sections"] if (s["file"], s["heading"]) == (file, heading))


def _drop_column(result):
    item = _body(result, "docs/data-models.md", "主要テーブル/コレクション構成")
    item["body"] = "\n".join(line for line in item["body"].splitlines() if "due_date" not in line)


def _drop_endpoint(result):
    for item in result["sections"]:
        if item["file"] == "docs/api.md":
            item["body"] = item["body"].replace("/loans/{loan_id}/return", "/loans/{loan_id}/give-back")


def _drop_diagram(result):
    item = _body(result, "docs/workflows.md", "状態管理・状態遷移")
    item["body"] = item["body"].split("```mermaid")[0] + "状態は表の 2 つである。"


def _spec_without_error_handling(result):
    spec = next(s for s in result["spec_files"] if s["slug"] == "return-book")
    spec["body"] = spec["body"].replace("## エラーハンドリング\n\n", "")


def _sample_residue(result):
    item = _body(result, "docs/workflows.md", "状態管理・状態遷移")
    item["body"] = item["body"].replace("返却済み --> [*]", "返却済み --> [*]\n    Created --> Processing")


def _drop_table(result):
    for item in result["sections"]:
        if item["file"] == "docs/data-models.md":
            item["body"] = item["body"].replace("loans", "rentals")
    er = _body(result, "docs/data-models.md", "ER図・関係性")
    result["sections"].remove(er)
    result["omissions"] = [{"file": "docs/data-models.md", "heading": "ER図・関係性", "reason": "根拠が無い"}]


MUTATIONS = {
    "drop-column": _drop_column,
    "drop-endpoint": _drop_endpoint,
    "drop-diagram": _drop_diagram,
    "spec-without-error-handling": _spec_without_error_handling,
    "sample-residue": _sample_residue,
    "drop-table": _drop_table,
}


def test_second_app_reference_passes_the_gate() -> None:
    skeletons = _library_skeletons()
    result = genlib.load_manifest(str(FIXTURE / "result.reference.yaml"))
    with tempfile.TemporaryDirectory(prefix="domain-docs-library-") as temp_dir:
        root = _library_repo(Path(temp_dir), skeletons, "reference")
        targets, plan = _library_plan(root, skeletons, copy.deepcopy(result))
        expected = genlib.load_manifest(str(FIXTURE / "expectations.yaml"))
        _assert(plan.report.findings == [] and plan.report.skipped == [],
                f"reference must pass without findings: {plan.report.findings} {plan.report.skipped}")
        _assert(plan.report.metrics == expected["reference"]["metrics"],
                f"reference metrics drifted: {plan.report.metrics}")
        # 契約節（3 ファイル）、ER 図、機能仕様 3 件がすべて書かれる。
        placeholders = {item["file"]: item.get("placeholders", []) for item in targets["files"]}
        _assert(placeholders["docs/api.md"] == ["REST 規約"]
                and placeholders["docs/data-models.md"] == ["型と識別子", "トランザクションの方式"]
                and placeholders["docs/workflows.md"] == ["ローカル開発"], f"placeholders wrong: {placeholders}")
        da.commit(root, plan.writes)
        data_models = (root / "docs/data-models.md").read_text(encoding="utf-8")
        _assert("erDiagram" in data_models and "ENTITY_A" not in data_models, "ER diagram missing")
        _assert("[TODO]" not in data_models, "data-models still has TODO")
        workflows = (root / "docs/workflows.md").read_text(encoding="utf-8")
        _assert(workflows.count("sequenceDiagram") == 2 and workflows.count("stateDiagram-v2") == 1,
                "workflow diagrams not carried over")
        _assert("[TODO]" not in workflows, "workflows still has TODO")
        for slug in ("register-member", "lend-book", "return-book"):
            _assert((root / "docs/spec" / f"{slug}.md").is_file(), f"spec file missing: {slug}")
        again = da.build_targets(
            root, root / "manifest.yaml", skeletons, root / DOC_PATH, refresh=False, titles=LIBRARY_TITLES)
        _assert(again["action"] == "skip", f"filled library repo must skip: {again['action']}")


def test_second_app_mutations_are_detected() -> None:
    skeletons = _library_skeletons()
    reference = genlib.load_manifest(str(FIXTURE / "result.reference.yaml"))
    expected = genlib.load_manifest(str(FIXTURE / "expectations.yaml"))["mutations"]
    _assert(set(expected) == set(MUTATIONS), f"expectations and mutations differ: {sorted(set(expected) ^ set(MUTATIONS))}")
    with tempfile.TemporaryDirectory(prefix="domain-docs-library-mut-") as temp_dir:
        base = Path(temp_dir)
        for name, mutate in MUTATIONS.items():
            root = _library_repo(base, skeletons, name)
            result = copy.deepcopy(reference)
            mutate(result)
            want = expected[name]
            if want["level"] == "FAIL":
                exc = _expect(da.GateError, name, lambda: _library_plan(root, skeletons, result))
                findings = exc.report.findings
            else:
                findings = _library_plan(root, skeletons, result)[1].report.findings
            levels = {item["level"] for item in findings}
            _assert(levels == {want["level"]}, f"{name}: levels {levels} != {want['level']}: {findings}")
            _assert({item["id"] for item in findings} == {want["id"]}, f"{name}: ids wrong: {findings}")
            joined = " ".join(f"{item['file']} {item['message']}" for item in findings)
            for needle in want["contains"]:
                _assert(needle in joined, f"{name}: {needle!r} not reported: {findings}")


def test_gate_skips_for_a_design_doc_without_the_standard_structure() -> None:
    skeletons = _library_skeletons()
    reference = genlib.load_manifest(str(FIXTURE / "result.reference.yaml"))
    with tempfile.TemporaryDirectory(prefix="domain-docs-library-plain-") as temp_dir:
        root = _library_repo(Path(temp_dir), skeletons, "plain")
        doc = root / DOC_PATH
        # 標準の見出し（業務フロー / データベース設計 / API設計）を別の名前にする。
        text = (FIXTURE / "designdoc.md").read_text(encoding="utf-8")
        for old, new in (("# 業務フロー", "# 流れ"), ("## データベース設計", "## 保存"), ("## API設計", "## 呼び出し")):
            text = text.replace(old, new)
        doc.write_text(text, encoding="utf-8")
        result = copy.deepcopy(reference)
        for item in result["sections"]:
            if item["evidence"] in ("業務フロー", "API設計", "データベース設計"):
                item["evidence"] = "概要"
        for spec in result["spec_files"]:
            spec["evidence"] = {"1. 会員の登録": "機能要件", "2. 貸出": "管理画面", "3. 返却": "概要"}[spec["evidence"]]
        for item in result["sections"]:
            if item["heading"] == "収録仕様":
                item["body"] = (
                    "- [会員の登録](register-member.md) — 司書が会員を登録する（根拠: `機能要件`）\n"
                    "- [貸出](lend-book.md) — 司書が蔵書の貸出を記録する（根拠: `管理画面`）\n"
                    "- [返却](return-book.md) — 司書が貸出の返却を記録する（根拠: `概要`）"
                )
        _, plan = _library_plan(root, skeletons, result)
        skipped = {item["id"] for item in plan.report.skipped}
        _assert({"G-DOCFILL-003", "G-DOCFILL-004"} <= skipped, f"expected skips for missing structure: {plan.report.skipped}")
        _assert(not plan.report.fails, f"plain design doc must not fail: {plan.report.findings}")


# --------------------------------------------------------------------------
# 一般性: kit の起案手順・テンプレート・スクリプトに、設計書由来の語彙を入れない
# --------------------------------------------------------------------------
# 既定の設計書（現行の Design Doc 例）の業務語彙。kit 側のファイルには現れてはならない。
FORBIDDEN_VOCABULARY = (
    "卓", "伝票", "受取番号", "call_number", "table_key", "hacocafe", "voucher",
    "conflict_dining", "invalid_table_key", "save_failed", "タブレット", "カフェ",
)


def test_kit_sources_carry_no_design_vocabulary() -> None:
    skill_dir = HERE.parent
    sources = sorted((skill_dir / "templates").rglob("*.template"))
    sources += [
        skill_dir / "manifest.yaml",
        skill_dir / "SKILL.md",
        skill_dir / "scripts" / "domain_docs_apply.py",
        skill_dir / "scripts" / "domain_docs_gate.py",
        skill_dir / "references" / "design-conformance.md",
        skill_dir / "references" / "source-mapping.md",
    ]
    _assert(len(sources) > 20, f"source scan too small: {len(sources)}")
    offenders = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for word in FORBIDDEN_VOCABULARY:
            if word in text:
                offenders.append(f"{path.relative_to(skill_dir).as_posix()}: {word}")
    _assert(not offenders, "design vocabulary leaked into kit sources: " + "; ".join(offenders))


def test_binding_gate() -> None:
    """G-DOCFILL-006: 束縛節の整合。apply が渡す名前の一覧だけで検査し、語彙は持たない。"""
    good = {
        "file": "docs/arch.md", "section": "束縛", "text": "本文",
        "placeholder_rows": {"app": "`sample-app`", "module": "`github.com/acme/sample-app`"},
        "names_text": (
            "| 種別 | 実名 | パス | 根拠 |\n| --- | --- | --- | --- |\n"
            "| Entity | `item_entity` | `internal/item_entity/` | `x` |\n"
            "| proto | `item` | `proto/sample/item.proto` | `x` |\n"
            "| UseCase | `web / order` | `x` | `x` |"
        ),
        "tree_text": "sample-app/\n├── item_entity/\n└── web/order_usecase/",
        "required_names": ["item", "order", "web"],
        "feature_names": ["item"],
        "app": "sample-app",
    }
    clean = gate.evaluate(DESIGN, replaced={}, final_texts={}, spec_documents={}, binding=good)
    _assert(not [f for f in clean.findings if f["id"] == "G-DOCFILL-006"], f"good binding must pass: {clean.findings}")
    _assert(clean.metrics.get("binding") == {"placeholders": 2, "names": 3}, f"metrics wrong: {clean.metrics}")
    # 束縛節を書かないときは、何も検査せず、skipped にも出さない。
    none = gate.evaluate(DESIGN, replaced={}, final_texts={}, spec_documents={}, binding=None)
    _assert("binding" not in none.metrics and not [s for s in none.skipped if s["id"] == "G-DOCFILL-006"],
            f"no binding must be silent: {none.metrics} {none.skipped}")
    cases = {
        "unfilled row": ({"placeholder_rows": {"app": "[TODO]", "module": "`m`"}}, "プレースホルダの具体値が未記入: app"),
        "empty row": ({"placeholder_rows": {"app": "  "}}, "プレースホルダの具体値が未記入: app"),
        "name missing in names": (
            {"names_text": "| Entity | `item_entity` | `p` |\n| proto | `item` | `proto/sample/item.proto` |"},
            "名前決定表に現れない名前: order, web",
        ),
        # 集約の Entity の行だけでは足りない。集約ごとに、パスが `.proto` の行が要る。
        "no proto row": (
            {"names_text": "| Entity | `item_entity` | `p` | `x` |\n| UseCase | `web / order` | `x` | `x` |"},
            "名前決定表に proto の行が無い集約: item",
        ),
        "proto row for another name": (
            {"feature_names": ["item", "order"]},
            "名前決定表に proto の行が無い集約: order",
        ),
        # 実名の列が集約名でも、パスが `.proto` でなければ proto の行に数えない。
        "controller row is not a proto row": (
            {"names_text": (
                "| Entity | `item_entity` | `p` | `x` |\n"
                "| Controller | `item` | `internal/controller/item_controller.go` | `x` |\n"
                "| UseCase | `web / order` | `x` | `x` |")},
            "名前決定表に proto の行が無い集約: item",
        ),
        "name missing in tree": ({"tree_text": "sample-app/\n└── item_entity/"}, "ディレクトリツリーに現れない名前: order, web"),
        "app missing in tree": ({"tree_text": "item order web"}, "ディレクトリツリーに現れない名前: sample-app"),
    }
    for label, (change, message) in cases.items():
        report = gate.evaluate(
            DESIGN, replaced={}, final_texts={}, spec_documents={}, binding={**good, **change})
        found = [f for f in report.fails if f["id"] == "G-DOCFILL-006"]
        _assert(len(found) == 1 and message in found[0]["message"], f"{label}: wrong findings: {report.findings}")
        _assert(found[0]["file"] == "docs/arch.md#束縛", f"{label}: wrong label: {found[0]['file']}")
    # 従属集約を親の proto に含めるときも、従属集約の行は残り、パスが親の `.proto` を指せば満たす。
    merged = {
        **good,
        "feature_names": ["item", "order"],
        "names_text": good["names_text"] + "\n| proto | `order` | `proto/sample/item.proto` | `x` |",
    }
    report = gate.evaluate(DESIGN, replaced={}, final_texts={}, spec_documents={}, binding=merged)
    _assert(not [f for f in report.findings if f["id"] == "G-DOCFILL-006"],
            f"a subordinate aggregate pointing at the parent proto must pass: {report.findings}")


def test_binding_gate_proto_rows_follow_the_contract() -> None:
    """proto の行は、ブループリントが proto を使う契約のときだけ要る（`require_proto`。既定は要求する）。"""
    binding = {
        "file": "docs/arch.md", "section": "束縛", "text": "本文",
        "placeholder_rows": {"app": "`sample-app`"},
        "names_text": (
            "| 種別 | 実名 | パス | 根拠 |\n| --- | --- | --- | --- |\n"
            "| Entity | `item_entity` | `internal/item_entity/` | `x` |\n"
            "| Controller | `item` | `internal/controller/item_controller.go` | `x` |"
        ),
        "tree_text": "sample-app/\n├── item_entity/\n└── item/",
        "required_names": ["item"],
        "feature_names": ["item"],
        "app": "sample-app",
    }

    def findings(**changes):
        report = gate.evaluate(DESIGN, replaced={}, final_texts={}, spec_documents={}, binding={**binding, **changes})
        return [f for f in report.findings if f["id"] == "G-DOCFILL-006"]

    default = findings()
    _assert(
        len(default) == 1 and default[0]["level"] == "FAIL" and "proto の行が無い集約: item" in default[0]["message"],
        f"既定は proto の行を要求する: {default}",
    )
    _assert(len(findings(require_proto=True)) == 1, "require_proto=True は要求する")
    _assert(findings(require_proto=False) == [], f"require_proto=False は proto の行を要求しない: {findings(require_proto=False)}")
    # proto の行を要求しなくても、ほかの検査（名前の欠落）は効く。
    missing = findings(require_proto=False, required_names=["item", "order"])
    _assert(any("名前決定表に現れない名前: order" in f["message"] for f in missing), f"名前の検査は残る: {missing}")


def main() -> int:
    tests = (
        ("design doc extraction", test_design_doc_extraction),
        ("residue is a FAIL", test_residue_is_a_fail),
        ("structural warnings and skips", test_structural_warnings_and_skips),
        ("second app reference passes the gate", test_second_app_reference_passes_the_gate),
        ("second app mutations are detected", test_second_app_mutations_are_detected),
        ("gate skips for a design doc without the standard structure",
         test_gate_skips_for_a_design_doc_without_the_standard_structure),
        ("binding gate", test_binding_gate),
        ("kit sources carry no design vocabulary", test_kit_sources_carry_no_design_vocabulary),
        ("binding gate proto rows follow the contract", test_binding_gate_proto_rows_follow_the_contract),
    )
    for label, test in tests:
        try:
            test()
        except Exception as exc:
            print(f"[test_domain_docs_gate] FAIL: {label}: {exc}", file=sys.stderr)
            return 1
        print(f"[test_domain_docs_gate] PASS: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
