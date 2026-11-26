#!/usr/bin/env python3
"""tech_contract の状態分類（READY / NEEDS_DRAFT / BROKEN）、draft 骨組み、版の数値 lint の回帰。

「契約が未起案・未承認・stale」は修正可能な想定内の状態であり、致命（exit 2）ではなく exit 1 で
返ること、骨組みは空欄のまま pin できないこと（fail-closed）を固定する。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tech_contract as tc  # noqa: E402
from test_contract_fixture import base_contract, bootstrap_root  # noqa: E402

SKILL_DIR = HERE.parent
ROOT = HERE.parents[3]
TECH_SCRIPT = HERE / "tech_contract.py"
ENGINE_SCRIPT = HERE / "run_resolved_engine.py"


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TECH_SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _seed_placeholder_block() -> bytes:
    raw = (SKILL_DIR / "manifest.yaml").read_bytes()
    span = tc._find_top_level_block_span(raw, b"tech_contract")
    assert span is not None, "seed manifest に tech_contract placeholder がありません"
    return raw[span[0]:span[1]]


def _fail(message: str) -> bool:
    print(f"FAIL: {message}", file=sys.stderr)
    return False


def placeholder_is_needs_draft() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        manifest, design = bootstrap_root(Path(tmp))
        with manifest.open("ab") as handle:
            handle.write(_seed_placeholder_block())
        try:
            tc.load_approved(manifest, design)
        except tc.ContractError as exc:
            if "Phase 1.6" not in str(exc):
                return _fail(f"未承認の案内に Phase 1.6 がない: {exc}")
        except tc.SchemaError as exc:
            return _fail(f"placeholder が致命（SchemaError）になっている: {exc}")
        else:
            return _fail("placeholder が承認済みとして受理された")
        state = tc.contract_state(manifest, design)
        if (state["state"], state["exit_code"]) != (tc.STATE_NEEDS_DRAFT, 1):
            return _fail(f"placeholder の分類が不正: {state}")
        result = _cli("status", "--manifest", str(manifest), "--design-doc", str(design))
        if result.returncode != 1 or "NEEDS_DRAFT" not in result.stderr:
            return _fail(f"status の exit が 1 でない: {result.returncode} {result.stderr}")
        result = _cli("status", "--json", "--manifest", str(manifest), "--design-doc", str(design))
        payload = json.loads(result.stdout)
        if result.returncode != 1 or payload["state"] != tc.STATE_NEEDS_DRAFT or not payload["next_action"]:
            return _fail(f"status --json が不正: {result.stdout}")
    return True


def missing_contract_is_needs_draft() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        manifest, design = bootstrap_root(Path(tmp))
        state = tc.contract_state(manifest, design)
        if (state["state"], state["exit_code"]) != (tc.STATE_NEEDS_DRAFT, 1):
            return _fail(f"契約欠落の分類が不正: {state}")
        if not state["next_action"]:
            return _fail("契約欠落に次の操作がない")
    return True


def pinned_is_ready_and_stale_is_needs_draft() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        manifest, design = bootstrap_root(Path(tmp))
        contract = base_contract(tc.source_fingerprint(design), with_file_action=False)
        tc.pin_contract(manifest, contract, tc.file_digest(manifest))
        state = tc.contract_state(manifest, design)
        if (state["state"], state["exit_code"]) != (tc.STATE_READY, 0) or not state.get("digest"):
            return _fail(f"pin 済みが READY でない: {state}")
        result = _cli("status", "--manifest", str(manifest), "--design-doc", str(design))
        if result.returncode != 0 or not result.stdout.startswith("READY:"):
            return _fail(f"READY の出力が互換でない: {result.stdout!r}")
        design.write_text(design.read_text(encoding="utf-8") + "追記\n", encoding="utf-8")
        state = tc.contract_state(manifest, design)
        if (state["state"], state["exit_code"]) != (tc.STATE_NEEDS_DRAFT, 1):
            return _fail(f"stale の分類が不正: {state}")
        if "Phase 1.6" not in state["reason"]:
            return _fail(f"stale の案内に Phase 1.6 がない: {state['reason']}")
    return True


def broken_is_fatal() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        manifest, design = bootstrap_root(Path(tmp))
        with manifest.open("a", encoding="utf-8") as handle:
            handle.write('tech_contract:\n  schema_version: 2\n  approval:\n    status: "approved"\n')
        state = tc.contract_state(manifest, design)
        if (state["state"], state["exit_code"]) != (tc.STATE_BROKEN, 2):
            return _fail(f"schema 破損が致命でない: {state}")
        result = _cli("status", "--manifest", str(manifest), "--design-doc", str(design))
        if result.returncode != 2 or "FATAL" not in result.stderr:
            return _fail(f"破損時の exit が 2 でない: {result.returncode}")
        missing = _cli("status", "--manifest", str(manifest), "--design-doc", str(Path(tmp) / "nope.md"))
        if missing.returncode != 2:
            return _fail(f"設計書欠落が致命でない: {missing.returncode}")
    return True


def _shape(value: object) -> object:
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return "[]"
    return type(value).__name__


def skeleton_fails_closed_and_matches_shape() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        _, design = bootstrap_root(Path(tmp))
        draft = Path(tmp) / "tmp" / "draft.yaml"
        absent_manifest = Path(tmp) / "no-manifest.yaml"
        result = _cli(
            "draft-skeleton", "--manifest", str(absent_manifest),
            "--design-doc", str(design), "--draft", str(draft),
        )
        if result.returncode != 0 or not draft.is_file():
            return _fail(f"骨組みの生成に失敗（manifest なしでも生成できること）: {result.stderr}")
        again = _cli("draft-skeleton", "--design-doc", str(design), "--draft", str(draft))
        if again.returncode != 1:
            return _fail(f"既存 draft の上書きが拒否されない: {again.returncode}")
        forced = _cli("draft-skeleton", "--design-doc", str(design), "--draft", str(draft), "--force")
        if forced.returncode != 0:
            return _fail(f"--force で上書きできない: {forced.stderr}")
        skeleton = tc.load_yaml(draft)
        if skeleton.get("source_fingerprint") != tc.source_fingerprint(design):
            return _fail("骨組みの source_fingerprint が設計書と一致しない")
        valid = base_contract(tc.source_fingerprint(design), with_file_action=False)
        if _shape(skeleton) != _shape(valid):
            return _fail("骨組みの形が有効な契約の形と一致しない")
        try:
            tc.validate(skeleton, design, require_approval=False)
        except tc.SchemaError:
            pass
        else:
            return _fail("空欄の骨組みが validate を通過した（fail-closed でない）")
        validated = _cli("validate", "--manifest", str(absent_manifest), "--design-doc", str(design), "--draft", str(draft))
        if validated.returncode == 0:
            return _fail("空欄の骨組みを CLI の validate が受理した")
    return True


def version_lint_reports_without_rejecting() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        manifest, design = bootstrap_root(Path(tmp))
        contract = base_contract(tc.source_fingerprint(design), with_file_action=False)
        contract["domain_docs"]["resolved"]["framework"] = "Go 1.27.3 と gRPC（§3.1.1 を参照）"
        contract["quality_gate"]["gen"]["argv"] = ["tool", "v2.3.4"]
        contract["quality_gate"]["gen"]["evidence_ref"] = "§4.1 の 9.9"
        hits = tc.lint_version_numbers(contract)
        if len(hits) != 2 or not any("framework" in h for h in hits) or not any("gen.argv" in h for h in hits):
            return _fail(f"版の数値の検出が不正: {hits}")
        clean = base_contract(tc.source_fingerprint(design), with_file_action=False)
        clean["domain_docs"]["resolved"]["framework"] = "§3.1.1 と §0.5 に従う gRPC"
        if tc.lint_version_numbers(clean):
            return _fail(f"§ 参照を版として誤検出: {tc.lint_version_numbers(clean)}")
        tc.validate(contract, design, require_approval=False)
        draft = Path(tmp) / "draft.yaml"
        draft.write_text("\n".join(tc._dump_yaml(contract)) + "\n", encoding="utf-8")
        result = _cli(
            "validate", "--manifest", str(manifest), "--design-doc", str(design), "--draft", str(draft),
        )
        if result.returncode != 0 or not result.stdout.startswith("PASS:"):
            return _fail(f"版 lint が validate を拒否に変えた: {result.returncode} {result.stderr}")
        if result.stderr.count("WARN:") != 2:
            return _fail(f"WARN が2件出ない: {result.stderr!r}")
    return True


def engine_placeholder_is_exit_1_with_guidance() -> bool:
    """今回の停止の再現: 契約が placeholder のとき generate / check は致命ではなく exit 1 で案内する。"""
    real = ROOT / "manifest.yaml"
    if not real.is_file():
        print("SKIP engine_placeholder_is_exit_1_with_guidance: root manifest absent", file=sys.stderr)
        return True
    raw = real.read_bytes()
    span = tc._find_top_level_block_span(raw, b"tech_contract")
    filename = (tc.load_yaml(real).get("project") or {}).get("tech_stack_design_filename")
    source_doc = ROOT / ".cursor" / "docs" / str(filename)
    if span is None or not source_doc.is_file():
        print("SKIP engine_placeholder_is_exit_1_with_guidance: contract/design absent", file=sys.stderr)
        return True
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "manifest.yaml").write_bytes(raw[:span[0]] + _seed_placeholder_block() + raw[span[1]:])
        copied = root / ".cursor" / "docs" / str(filename)
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_bytes(source_doc.read_bytes())
        for command in ("check", "audit"):
            result = subprocess.run(
                [sys.executable, str(ENGINE_SCRIPT), command, "--root-manifest", str(root / "manifest.yaml")],
                capture_output=True,
                text=True,
            )
            if result.returncode != 1:
                return _fail(f"{command}: placeholder で exit 1 にならない: {result.returncode} {result.stderr}")
            if "Phase 1.6" not in result.stderr or "FATAL" in result.stderr:
                return _fail(f"{command}: 案内がない、または致命表示: {result.stderr!r}")
    return True


TESTS = (
    placeholder_is_needs_draft,
    missing_contract_is_needs_draft,
    pinned_is_ready_and_stale_is_needs_draft,
    broken_is_fatal,
    skeleton_fails_closed_and_matches_shape,
    version_lint_reports_without_rejecting,
    engine_placeholder_is_exit_1_with_guidance,
)


def main() -> int:
    failed = [test.__name__ for test in TESTS if not test()]
    if failed:
        print(f"[test_contract_state] FAIL: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"[test_contract_state] {len(TESTS)}/{len(TESTS)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
