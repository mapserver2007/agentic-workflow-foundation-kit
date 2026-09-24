#!/usr/bin/env python3
"""適用済みアプリへ agentic-workflow-foundation-kit を安全に更新する。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
LOCK_SCHEMA_VERSION = 1
LOCK_PATH = Path("agentic-workflow-kit.lock.yaml")
DEFAULT_CLONE_ROOT = Path("/tmp/agentic-workflow-foundation-kit")
DEFAULT_WORK_ROOT = Path("/tmp/work")
DENY_EXACT = {
    Path("init.yaml"),
    Path("manifest.yaml"),
    Path(".cursor/docs/TECHNOLOGY_STACK_UNIFIED_DESIGN.md"),
    Path("docs/DECISIONS.md"),
    Path("docs/GOTCHAS.md"),
}
DENY_PREFIXES = (
    Path("docs/spec"),
    Path("docs/agent-tasks/reports"),
    Path("docs/agent-tasks/reviews"),
)
NON_APPLY_PREFIXES = (
    Path(".cursor/skills/agentic-workflow-foundation"),
    Path(".cursor/skills/agentic-workflow-engine"),
    Path(".cursor/docs/AI_AGENT_UNIFIED_DESIGN.md"),
    Path(".cursor/docs/AI_BUSINESS_AGENT_SUITE.md"),
)


class UpdateError(RuntimeError):
    """ユーザーが修正可能な updater エラー。"""

    exit_code = 1


class FatalUpdateError(UpdateError):
    """入力不備または契約違反による致命的な updater エラー。"""

    exit_code = 2


class CommandUpdateError(UpdateError):
    """子プロセスの終了コードと診断情報を保持する updater エラー。"""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = 2 if exit_code == 2 else 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _safe_rel(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path) in ("", "."):
        raise UpdateError(f"KU-SCOPE-001: 不正な相対パスです: {value}")
    return path


def _safe_target(root: Path, rel: str | Path) -> Path:
    relative = _safe_rel(rel)
    target = (root / relative).resolve(strict=False)
    root_real = root.resolve()
    if os.path.commonpath((str(root_real), str(target))) != str(root_real):
        raise UpdateError(f"KU-SCOPE-001: root 外のパスです: {relative}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UpdateError(f"KU-SCOPE-001: symlink 経由の同期を拒否しました: {relative}")
    return root / relative


def _resolve_overlay_path(app_root: Path, explicit: str | None) -> Path:
    raw = Path(explicit).expanduser() if explicit else app_root / "manifest.yaml"
    if raw.is_symlink():
        raise FatalUpdateError("KU-OVERLAY-001: root manifest が symlink です")
    path = raw.resolve(strict=False)
    if not path.is_file():
        raise FatalUpdateError(f"KU-OVERLAY-001: root manifest がありません: {path}")
    return path


def _preflight_overlay(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FatalUpdateError(f"KU-OVERLAY-001: root manifest を読めません: {path}") from exc
    if not text.strip():
        raise FatalUpdateError(f"KU-OVERLAY-001: root manifest が空です: {path}")
    top_level = []
    for raw in text.splitlines():
        if "\t" in raw:
            raise FatalUpdateError(f"KU-OVERLAY-001: tab indentation は使用できません: {path}")
        line = raw.strip()
        if not line or line.startswith("#") or line == "---":
            continue
        if len(raw) == len(raw.lstrip(" ")) and re.match(r"^[^:#]+:", line):
            top_level.append(line)
    if not top_level:
        raise FatalUpdateError(f"KU-OVERLAY-001: root manifest が mapping ではありません: {path}")


def _load_manifest(path: Path, kit_root: Path) -> dict[str, Any]:
    engine_path = kit_root / ".cursor/skills/agentic-workflow-engine/scripts/genlib.py"
    if not engine_path.is_file():
        raise UpdateError(f"KU-SCOPE-001: engine genlib.py がありません: {engine_path}")
    module_name = f"kit_update_genlib_{hash(engine_path)}"
    spec = importlib.util.spec_from_file_location(module_name, engine_path)
    if spec is None or spec.loader is None:
        raise UpdateError("KU-SCOPE-001: manifest loader を読み込めません")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        value = module.load_manifest(str(path))
    except Exception as exc:  # noqa: BLE001
        raise UpdateError(f"KU-OVERLAY-001: manifest を読み込めません: {path}") from exc
    if not isinstance(value, dict):
        raise UpdateError(f"KU-OVERLAY-001: manifest が mapping ではありません: {path}")
    return value


def _catalog_from_manifest(manifest: dict[str, Any]) -> dict[Path, dict[str, Any]]:
    result: dict[Path, dict[str, Any]] = {}
    for output in manifest.get("outputs") or []:
        if not isinstance(output, dict) or not isinstance(output.get("path"), str):
            raise UpdateError("KU-SCOPE-001: outputs[] の path が不正です")
        mode = output.get("mode", "render")
        if mode not in {"render", "marker"}:
            continue
        rel = _safe_rel(output["path"])
        if any(rel == prefix or prefix in rel.parents for prefix in NON_APPLY_PREFIXES):
            raise UpdateError(f"KU-SCOPE-001: kit source を output catalog に含められません: {rel}")
        if rel == LOCK_PATH:
            raise UpdateError(f"KU-SCOPE-001: lock path を output catalog に含められません: {rel}")
        result[rel] = {"path": str(rel), "mode": mode}
    return result


def _copy_app(app_root: Path, work_root: Path) -> None:
    if work_root.exists() or work_root.is_symlink():
        raise UpdateError(f"KU-SCOPE-001: work root が既に存在します: {work_root}")

    def ignore(path: str, names: list[str]) -> set[str]:
        ignored = {".git", "__pycache__"}
        return {name for name in names if name in ignored or name.endswith(".pyc")}

    shutil.copytree(app_root, work_root, symlinks=True, ignore=ignore)


def _prepare_work_tree(
    app_root: Path,
    overlay_path: Path,
    work_root: Path,
) -> None:
    _copy_app(app_root, work_root)
    target = work_root / "manifest.yaml"
    if target.is_symlink():
        raise UpdateError("KU-SCOPE-001: 一時作業ツリーの manifest.yaml が symlink です")
    target.parent.mkdir(parents=True, exist_ok=True)
    if overlay_path.resolve() != (app_root / "manifest.yaml").resolve():
        shutil.copy2(overlay_path, target)


def _run(command: list[str], cwd: Path, *, allow_failure: bool = False) -> None:
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0 and not allow_failure:
        detail = (result.stderr or result.stdout).strip().splitlines()
        summary = detail[-1] if detail else "出力なし"
        raise CommandUpdateError(
            f"生成または検証に失敗しました (exit {result.returncode}): {summary}",
            result.returncode,
        )


def _load_resolved_manifest(
    seed_manifest: Path,
    root_manifest: Path,
    kit_root: Path,
) -> dict[str, Any]:
    runner_path = kit_root / ".cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py"
    engine_dir = kit_root / ".cursor/skills/agentic-workflow-engine/scripts"
    foundation_dir = kit_root / ".cursor/skills/agentic-workflow-foundation/scripts"
    if not runner_path.is_file() or not engine_dir.is_dir() or not foundation_dir.is_dir():
        raise FatalUpdateError("KU-OVERLAY-001: resolved manifest の実行基盤がありません")
    old_sys_path = list(sys.path)
    sys.path[:0] = [str(foundation_dir), str(engine_dir)]
    try:
        module_name = f"kit_update_resolver_{abs(hash(runner_path))}"
        spec = importlib.util.spec_from_file_location(module_name, runner_path)
        if spec is None or spec.loader is None:
            raise FatalUpdateError("KU-OVERLAY-001: resolved manifest loader を読み込めません")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        value = module.resolved_manifest(str(seed_manifest), str(root_manifest))
    except SystemExit as exc:
        raise FatalUpdateError(
            f"KU-OVERLAY-001: resolved manifest の検証に失敗しました (exit {exc.code})"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise FatalUpdateError("KU-OVERLAY-001: resolved manifest を解決できません") from exc
    finally:
        sys.path[:] = old_sys_path
    if not isinstance(value, dict):
        raise FatalUpdateError("KU-OVERLAY-001: resolved manifest が mapping ではありません")
    return value


def _run_candidate_validation(kit_root: Path, work_root: Path) -> dict[str, Any]:
    runner = kit_root / ".cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py"
    seed = kit_root / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"
    root_manifest = work_root / "manifest.yaml"
    if not runner.is_file() or not seed.is_file() or not root_manifest.is_file():
        raise UpdateError("KU-OVERLAY-001: overlay 生成に必要な入力が不足しています")
    common = [
        sys.executable,
        str(runner),
        "--seed-manifest",
        str(seed),
        "--root-manifest",
        str(root_manifest),
        "--work-root",
        str(work_root),
    ]
    # work_root が kit clone の ROOT ではないため、runner は host updater を配置しない。
    _run([*common[:1], common[1], "generate", *common[2:]], work_root)
    _run([*common[:1], common[1], "check", *common[2:]], work_root)
    _run([*common[:1], common[1], "audit", *common[2:]], work_root)

    manifest = _load_resolved_manifest(seed, root_manifest, kit_root)
    profile = (
        manifest.get("project", {})
        .get("quality_gate", {})
        .get("profile", "foundation")
    )
    if profile != "application":
        raise FatalUpdateError("KU-OVERLAY-001: consumer updater は application profile が必要です")
    gate = work_root / "bin/quality-gate"
    if gate.is_file():
        _run([str(gate), "verify"], work_root)
    else:
        raise FatalUpdateError(f"KU-OVERLAY-001: quality gate がありません: {gate}")
    return manifest


def _digest_or_none(path: Path) -> str | None:
    return _sha256(path) if path.is_file() else None


def _snapshot_protected(app_root: Path, paths: Iterable[Path]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    expanded: set[Path] = set()
    for relative in paths:
        target = _safe_target(app_root, relative)
        if target.is_symlink():
            raise UpdateError(f"KU-DENY-001: 保護対象が symlink です: {relative}")
        if target.is_dir():
            expanded.update(
                path.relative_to(app_root)
                for path in target.rglob("*")
                if path.is_file()
            )
        else:
            expanded.add(relative)
    for relative in sorted(expanded):
        target = _safe_target(app_root, relative)
        if target.exists():
            if not target.is_file() or target.is_symlink():
                raise UpdateError(f"KU-DENY-001: 保護対象が通常ファイルではありません: {relative}")
            snapshot[str(relative)] = _sha256(target)
    return snapshot


def _is_protected_path(relative: Path, protected: Iterable[Path]) -> bool:
    return any(relative == prefix or prefix in relative.parents for prefix in protected)


def _protected_paths(old_outputs: dict[Path, dict[str, Any]],
                     new_outputs: dict[Path, dict[str, Any]]) -> set[Path]:
    paths = set(DENY_EXACT)
    paths.update(NON_APPLY_PREFIXES)
    paths.update(path for path in (*old_outputs, *new_outputs)
                 if (old_outputs.get(path) or new_outputs.get(path)).get("mode") == "seed")
    for prefix in DENY_PREFIXES:
        paths.add(prefix)
    return paths


def _current_file_state(root: Path, relative: Path) -> dict[str, Any]:
    target = _safe_target(root, relative)
    return {
        "sha256": _digest_or_none(target),
        "mode": _mode(target) if target.is_file() else None,
    }


def _load_lock(app_root: Path, kit_root: Path) -> dict[str, Any] | None:
    path = app_root / LOCK_PATH
    if not path.is_file():
        return None
    if path.is_symlink():
        raise FatalUpdateError(f"KU-LOCK-001: lock が symlink です: {path}")
    try:
        value = _load_manifest(path, kit_root)
    except UpdateError as exc:
        raise FatalUpdateError(f"KU-LOCK-001: lock を読み込めません: {path}") from exc
    if value.get("version") != LOCK_SCHEMA_VERSION:
        raise FatalUpdateError(f"KU-LOCK-001: lock version が不正です: {path}")
    raw_catalog = value.get("catalog")
    if not isinstance(raw_catalog, list):
        raise FatalUpdateError(f"KU-LOCK-001: lock catalog が不正です: {path}")
    catalog: dict[Path, dict[str, Any]] = {}
    for item in raw_catalog:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise FatalUpdateError(f"KU-LOCK-001: lock catalog item が不正です: {path}")
        rel = _safe_rel(item["path"])
        mode = item.get("mode", "render")
        digest = item.get("sha256")
        if mode not in {"render", "marker"} or not isinstance(digest, str):
            raise FatalUpdateError(f"KU-LOCK-001: lock catalog item が不正です: {rel}")
        if any(rel == prefix or prefix in rel.parents for prefix in NON_APPLY_PREFIXES):
            raise FatalUpdateError(f"KU-LOCK-001: kit source を lock に記録できません: {rel}")
        if rel in catalog:
            raise FatalUpdateError(f"KU-LOCK-001: lock catalog に重複があります: {rel}")
        catalog[rel] = {"path": str(rel), "mode": mode, "sha256": digest}
    revision = value.get("kit_revision")
    if not isinstance(revision, str) or not revision:
        raise FatalUpdateError(f"KU-LOCK-001: kit_revision がありません: {path}")
    return {"kit_revision": revision, "catalog": catalog}


def _lock_catalog_as_list(catalog: dict[Path, dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "path": str(relative),
            "mode": str(catalog[relative]["mode"]),
            "sha256": str(catalog[relative]["sha256"]),
        }
        for relative in sorted(catalog)
    ]


def _write_lock_candidate(
    work_root: Path,
    kit_revision: str,
    catalog: dict[Path, dict[str, Any]],
) -> None:
    entries: list[dict[str, str]] = []
    for relative in sorted(catalog):
        candidate = _safe_target(work_root, relative)
        if not candidate.is_file() or candidate.is_symlink():
            raise FatalUpdateError(f"KU-OVERLAY-001: 生成候補がありません: {relative}")
        entries.append({
            "path": str(relative),
            "mode": str(catalog[relative]["mode"]),
            "sha256": _sha256(candidate),
        })
    lines = [
        f"version: {LOCK_SCHEMA_VERSION}",
        f'kit_revision: "{kit_revision}"',
        "catalog:",
    ]
    for item in entries:
        lines.extend([
            f'  - path: "{item["path"]}"',
            f'    mode: "{item["mode"]}"',
            f'    sha256: "{item["sha256"]}"',
        ])
    target = _safe_target(work_root, LOCK_PATH)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _lock_change_record(app_root: Path, work_root: Path) -> dict[str, Any] | None:
    relative = LOCK_PATH
    candidate = _safe_target(work_root, relative)
    target = _safe_target(app_root, relative)
    if not candidate.is_file() or candidate.is_symlink():
        raise FatalUpdateError(f"KU-OVERLAY-001: lock 候補がありません: {candidate}")
    candidate_state = {"sha256": _sha256(candidate), "mode": _mode(candidate)}
    current = _current_file_state(app_root, relative)
    if current == candidate_state:
        return None
    return {
        "path": str(relative),
        "kind": "lock",
        "mode": "lock",
        "candidate_path": str(candidate),
        "candidate_sha256": candidate_state["sha256"],
        "candidate_mode": candidate_state["mode"],
        "preimage_sha256": current["sha256"],
        "preimage_mode": current["mode"],
        "action": "add" if not target.exists() else "update",
    }


def _output_change_records(
    app_root: Path,
    work_root: Path,
    old_outputs: dict[Path, dict[str, Any]],
    new_outputs: dict[Path, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[Path], list[tuple[Path, Path]]]:
    changes: list[dict[str, Any]] = []
    for relative, output in sorted(new_outputs.items()):
        candidate = _safe_target(work_root, relative)
        if not candidate.is_file() or candidate.is_symlink():
            raise UpdateError(f"KU-OVERLAY-001: 生成候補がありません: {relative}")
        target = _safe_target(app_root, relative)
        current = _current_file_state(app_root, relative)
        candidate_state = {"sha256": _sha256(candidate), "mode": _mode(candidate)}
        if current == candidate_state:
            continue
        mode = output.get("mode", "render")
        changes.append({
            "path": str(relative),
            "kind": "generated",
            "mode": mode,
            "candidate_path": str(candidate),
            "candidate_sha256": candidate_state["sha256"],
            "candidate_mode": candidate_state["mode"],
            "preimage_sha256": current["sha256"],
            "preimage_mode": current["mode"],
            "action": "add" if not target.exists() else "update",
        })

    removed = sorted(set(old_outputs) - set(new_outputs))
    new_by_digest = {
        record["candidate_sha256"]: Path(record["path"])
        for record in changes
        if record["kind"] == "generated"
    }
    rename_candidates = [
        (relative, new_by_digest[_sha256(_safe_target(app_root, relative))])
        for relative in removed
        if _safe_target(app_root, relative).is_file()
        and _sha256(_safe_target(app_root, relative)) in new_by_digest
    ]
    return changes, removed, rename_candidates


def _plan_digest(plan: dict[str, Any]) -> str:
    payload = dict(plan)
    payload.pop("plan_digest", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_plan(path: Path, plan: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _build_plan(
    app_root: Path,
    clone_root: Path,
    work_root: Path,
    overlay_path: Path,
    *,
    validate: bool = True,
    kit_revision: str = "",
) -> dict[str, Any]:
    app_root = app_root.resolve()
    clone_root = clone_root.resolve()
    work_root = work_root.resolve()
    overlay_path = overlay_path.resolve()
    _preflight_overlay(overlay_path)
    if overlay_path == (clone_root / "manifest.yaml").resolve():
        raise FatalUpdateError("KU-OVERLAY-001: kit clone の manifest.yaml は overlay に使えません")
    if not kit_revision:
        raise FatalUpdateError("KU-SCOPE-001: kit revision がありません")
    if validate:
        _prepare_work_tree(app_root, overlay_path, work_root)
        resolved_manifest = _run_candidate_validation(clone_root, work_root)
    else:
        if not work_root.is_dir():
            raise FatalUpdateError(f"KU-OVERLAY-001: work root がありません: {work_root}")
        resolved_manifest = _load_resolved_manifest(
            clone_root / ".cursor/skills/agentic-workflow-foundation/manifest.yaml",
            work_root / "manifest.yaml",
            clone_root,
        )

    new_catalog = _catalog_from_manifest(resolved_manifest)
    lock = _load_lock(app_root, clone_root)
    old_catalog = lock["catalog"] if lock is not None else {}
    _write_lock_candidate(work_root, kit_revision, new_catalog)
    output_changes, output_orphans, rename_candidates = _output_change_records(
        app_root, work_root, old_catalog, new_catalog
    )
    lock_change = _lock_change_record(app_root, work_root)
    changes = list(output_changes)
    if lock_change is not None:
        changes.append(lock_change)
    protected = _protected_paths(old_catalog, new_catalog)
    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "app_root": str(app_root),
        "clone_root": str(clone_root),
        "work_root": str(work_root),
        "overlay_manifest_path": str(overlay_path),
        "overlay_manifest_sha256": _sha256(overlay_path),
        "kit_revision": kit_revision,
        "catalog": _lock_catalog_as_list({
            relative: {
                **new_catalog[relative],
                "sha256": _sha256(_safe_target(work_root, relative)),
            }
            for relative in new_catalog
        }),
        "baseline": "lock" if lock is not None else "adopt",
        "previous_kit_revision": lock["kit_revision"] if lock is not None else None,
        "changes": sorted(changes, key=lambda item: item["path"]),
        "orphan": [str(path) for path in sorted(set(output_orphans))],
        "rename_candidates": [
            {"old": str(old), "new": str(new)}
            for old, new in rename_candidates
        ],
        "protected": _snapshot_protected(app_root, protected),
        "blocking_issues": [],
    }
    if plan["orphan"] or plan["rename_candidates"]:
        plan["blocking_issues"].append("KU-ORPHAN-001")
    if any(
        _is_protected_path(_safe_rel(change["path"]), protected)
        for change in plan["changes"]
    ):
        plan["blocking_issues"].append("KU-DENY-001")
    plan["blocking_issues"] = sorted(set(plan["blocking_issues"]))
    plan["plan_digest"] = _plan_digest(plan)
    return plan


def _write_atomic(target: Path, content: bytes, mode: int) -> None:
    if target.is_symlink() or target.exists() and target.is_dir():
        raise UpdateError(f"KU-SCOPE-001: 同期先が通常ファイルではありません: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validate_plan(plan: dict[str, Any], app_root: Path, approved: str) -> None:
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise UpdateError("KU-PREIMAGE-001: plan schema が不一致です")
    expected = plan.get("plan_digest")
    if not isinstance(expected, str) or expected != approved or _plan_digest(plan) != expected:
        raise UpdateError("KU-PREIMAGE-001: plan digest が不一致です")
    if Path(plan.get("app_root", "")).resolve() != app_root.resolve():
        raise UpdateError("KU-PREIMAGE-001: 対象アプリ root が不一致です")
    overlay_path = Path(plan.get("overlay_manifest_path", "")).resolve()
    if not overlay_path.is_file() or _sha256(overlay_path) != plan.get("overlay_manifest_sha256"):
        raise UpdateError("KU-PREIMAGE-001: overlay manifest が変更されています")
    kit_revision = plan.get("kit_revision")
    clone_root = Path(plan.get("clone_root", "")).resolve()
    if not isinstance(kit_revision, str) or not kit_revision:
        raise UpdateError("KU-PREIMAGE-001: kit revision がありません")
    try:
        result = subprocess.run(
            ["git", "-C", str(clone_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        actual_revision = result.stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise UpdateError("KU-PREIMAGE-001: kit clone の revision を検証できません") from exc
    if actual_revision != kit_revision:
        raise UpdateError("KU-PREIMAGE-001: kit clone の revision が計画と不一致です")
    for change in plan.get("changes", []):
        _validate_change_scope(change)
    if plan.get("blocking_issues"):
        raise UpdateError(
            "KU-ORPHAN-001: 停止要因があります: "
            + ", ".join(plan["blocking_issues"])
        )


def _validate_change_scope(change: dict[str, Any]) -> None:
    relative = _safe_rel(change.get("path", ""))
    kind = change.get("kind")
    if kind == "lock":
        if relative != LOCK_PATH:
            raise UpdateError(f"KU-SCOPE-001: 不正な lock 適用先です: {relative}")
    elif kind == "generated":
        if any(
            relative == prefix or prefix in relative.parents
            for prefix in NON_APPLY_PREFIXES
        ):
            raise UpdateError(f"KU-SCOPE-001: kit source は適用できません: {relative}")
    else:
        raise UpdateError(f"KU-SCOPE-001: 不正な変更種別です: {kind}")


def _rollback_applied(applied: list[tuple[Path, bytes | None, int | None]]) -> None:
    for target, content, mode in reversed(applied):
        try:
            if content is None:
                if target.is_file() or target.is_symlink():
                    target.unlink()
            else:
                _write_atomic(target, content, int(mode or 0o644))
        except OSError:
            pass


def _apply_plan(plan: dict[str, Any]) -> list[tuple[Path, bytes | None, int | None]]:
    app_root = Path(plan["app_root"]).resolve()
    applied: list[tuple[Path, bytes | None, int | None]] = []
    for relative, digest in plan.get("protected", {}).items():
        current = _safe_target(app_root, relative)
        if not current.is_file() or _sha256(current) != digest:
            raise UpdateError(f"KU-DENY-001: 保護対象が変更されています: {relative}")

    try:
        for change in plan.get("changes", []):
            _validate_change_scope(change)
            relative = _safe_rel(change["path"])
            target = _safe_target(app_root, relative)
            current = _current_file_state(app_root, relative)
            if current["sha256"] != change.get("preimage_sha256") or (
                current["mode"] != change.get("preimage_mode")
            ):
                raise UpdateError(f"KU-PREIMAGE-001: 適用前の内容が変わっています: {relative}")
            candidate = Path(change["candidate_path"])
            candidate_roots = (
                Path(plan["work_root"]).resolve(),
                Path(plan["clone_root"]).resolve(),
            )
            candidate_root = None
            candidate_relative = None
            for root in candidate_roots:
                try:
                    candidate_relative = candidate.resolve(strict=False).relative_to(root)
                    _safe_target(root, candidate_relative)
                    candidate_root = root
                    break
                except (OSError, ValueError):
                    continue
            if candidate_root is None:
                raise UpdateError(
                    f"KU-SCOPE-001: 候補が plan の work/clone root 外です: {candidate}"
                )
            if (
                not candidate.is_file()
                or candidate.is_symlink()
                or _sha256(candidate) != change["candidate_sha256"]
            ):
                raise UpdateError(f"KU-PREIMAGE-001: 候補内容が変わっています: {relative}")
            old_content = target.read_bytes() if target.is_file() else None
            old_mode = _mode(target) if target.is_file() else None
            applied.append((target, old_content, old_mode))
            _write_atomic(target, candidate.read_bytes(), int(change["candidate_mode"]))
    except Exception:
        _rollback_applied(applied)
        raise
    return applied


def _fetch_kit(clone_root: Path) -> dict[str, Any]:
    wrapper = Path(__file__).resolve().parents[1] / "bin/kit-source-fetch-safe"
    if not wrapper.is_file():
        raise UpdateError("KU-SCOPE-001: kit fetch wrapper がありません")
    result = subprocess.run(
        [
            "bash",
            str(wrapper),
            "--clone-root",
            str(clone_root),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        summary = detail[-1] if detail else "出力なし"
        raise CommandUpdateError(
            f"kit の取得に失敗しました (exit {result.returncode}): {summary}",
            result.returncode,
        )
    try:
        value = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise UpdateError("KU-SCOPE-001: fetch wrapper の結果が不正です") from exc
    if not isinstance(value, dict) or not value.get("clone_root") or not value.get("sha"):
        raise UpdateError("KU-SCOPE-001: fetch wrapper の revision がありません")
    return value


def _run_application_validation(
    app_root: Path,
    kit_root: Path,
    overlay_path: Path,
) -> None:
    manifest_path = app_root / "manifest.yaml"
    if not manifest_path.is_file():
        manifest_path = overlay_path
    if not manifest_path.is_file():
        raise FatalUpdateError("KU-OVERLAY-001: 適用後の quality gate 入力がありません")
    manifest = _load_manifest(manifest_path, kit_root)
    profile = (
        manifest.get("project", {})
        .get("quality_gate", {})
        .get("profile", "foundation")
    )
    if profile != "application":
        raise FatalUpdateError("KU-OVERLAY-001: consumer updater は application profile が必要です")
    gate = app_root / "bin/quality-gate"
    command = [str(gate), "verify"]
    if not gate.is_file():
        raise UpdateError(f"KU-OVERLAY-001: 適用後の quality gate がありません: {gate}")
    _run(command, app_root)


def _remove_host_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _install_host_updater(clone_root: Path) -> int:
    """適用成功後に clone の最新版 updater をホスト個人スキルへ配置する。"""
    source = clone_root / ".cursor/skills/agentic-workflow-update"
    if not source.is_dir() or source.is_symlink():
        print("[KU-HOST-001] SKIP: clone に updater 正本がありません")
        return 0
    if any(path.is_symlink() for path in source.rglob("*")):
        raise UpdateError("KU-SCOPE-001: updater 正本に symlink が含まれています")

    base = Path(
        os.path.expanduser(
            os.environ.get("AGENTIC_WORKFLOW_UPDATE_HOME", "~/.cursor/skills")
        )
    ).resolve()
    destination = base / "agentic-workflow-update"
    try:
        base.mkdir(parents=True, exist_ok=True)
        staging_parent = Path(tempfile.mkdtemp(prefix=".agentic-workflow-update.", dir=base))
    except OSError as exc:
        raise UpdateError(f"KU-HOST-001: 個人スキル配置先を準備できません: {exc}") from exc
    staged = staging_parent / "agentic-workflow-update"
    backup = base / f".agentic-workflow-update.previous.{os.getpid()}"
    try:
        shutil.copytree(
            source,
            staged,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        if not (staged / "SKILL.md").is_file():
            raise UpdateError("KU-HOST-001: updater SKILL.md がありません")
        if backup.exists() or backup.is_symlink():
            raise UpdateError("KU-HOST-001: updater 退避先が既に存在します")
        if destination.exists() or destination.is_symlink():
            os.replace(destination, backup)
        try:
            os.replace(staged, destination)
        except OSError:
            if backup.exists() or backup.is_symlink():
                os.replace(backup, destination)
            raise
        if backup.exists() or backup.is_symlink():
            _remove_host_path(backup)
        print(f"[KU-HOST-001] PASS: 個人 updater を更新しました: {destination}")
        return 0
    except OSError as exc:
        raise UpdateError(f"KU-HOST-001: 個人 updater 更新に失敗しました: {exc}") from exc
    finally:
        _remove_host_path(staging_parent)


def _default_work_root() -> Path:
    return DEFAULT_WORK_ROOT


def command_plan(args: argparse.Namespace) -> int:
    app_root = Path(args.app_root).resolve()
    clone_root = Path(args.clone_root).resolve()
    work_root = Path(args.work_root).resolve()
    overlay_path = _resolve_overlay_path(app_root, args.root_manifest)
    _preflight_overlay(overlay_path)
    if not (app_root / ".git").exists():
        raise UpdateError("KU-SCOPE-001: 対象アプリは Git repository ではありません")
    fetched = _fetch_kit(clone_root)
    plan = _build_plan(
        app_root,
        Path(fetched["clone_root"]),
        work_root,
        overlay_path,
        kit_revision=str(fetched["sha"]),
    )
    if args.plan_file:
        _write_plan(Path(args.plan_file).resolve(), plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if plan["blocking_issues"]:
        return 1
    return 0


def command_apply(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan_file).resolve()
    if not plan_path.is_file():
        raise UpdateError("KU-PREIMAGE-001: plan file がありません")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    app_root = Path(args.app_root).resolve()
    _validate_plan(plan, app_root, args.approve_plan)
    applied = _apply_plan(plan)
    try:
        _run_application_validation(
            app_root,
            Path(plan["clone_root"]).resolve(),
            Path(plan["overlay_manifest_path"]).resolve(),
        )
        _install_host_updater(Path(plan["clone_root"]).resolve())
    except Exception:
        _rollback_applied(applied)
        raise
    print(json.dumps({
        "status": "applied",
        "plan_digest": plan["plan_digest"],
        "changed_paths": [item["path"] for item in plan.get("changes", [])],
    }, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="agentic-workflow-update")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--app-root", default=".")
    plan.add_argument("--root-manifest")
    plan.add_argument("--clone-root", default=str(DEFAULT_CLONE_ROOT))
    plan.add_argument("--work-root", default=str(DEFAULT_WORK_ROOT))
    plan.add_argument("--plan-file")
    plan.set_defaults(handler=command_plan)
    apply = subparsers.add_parser("apply")
    apply.add_argument("--app-root", default=".")
    apply.add_argument("--plan-file", required=True)
    apply.add_argument("--approve-plan", required=True)
    apply.set_defaults(handler=command_apply)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except UpdateError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FATAL: updater 実行失敗: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

