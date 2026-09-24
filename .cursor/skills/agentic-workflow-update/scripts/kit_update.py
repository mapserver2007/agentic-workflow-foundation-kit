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
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
DEFAULT_CLONE_ROOT = Path("/tmp/agentic-workflow-foundation-kit")
DEFAULT_WORK_ROOT = Path("/tmp/work")
KIT_SOURCE_DIRS = (
    Path(".cursor/skills/agentic-workflow-foundation"),
    Path(".cursor/skills/agentic-workflow-engine"),
)
KIT_SOURCE_FILES = (
    Path(".cursor/docs/AI_AGENT_UNIFIED_DESIGN.md"),
    Path(".cursor/docs/AI_BUSINESS_AGENT_SUITE.md"),
)
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


class UpdateError(RuntimeError):
    """ユーザーが修正可能な updater エラー。"""


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


def _iter_files(root: Path, relative: Path) -> Iterable[Path]:
    base = root / relative
    if base.is_symlink():
        raise UpdateError(f"KU-SCOPE-001: symlink を kit ソースに含められません: {relative}")
    if not base.exists():
        return ()
    if base.is_file():
        return (relative,)
    files: list[Path] = []
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(root)
        if path.is_symlink():
            raise UpdateError(f"KU-SCOPE-001: symlink を kit ソースに含められません: {rel}")
        if path.is_file() and "__pycache__" not in rel.parts and not path.name.endswith(".pyc"):
            files.append(rel)
    return tuple(files)


def _kit_files(root: Path) -> tuple[Path, ...]:
    files: set[Path] = set(KIT_SOURCE_FILES)
    for relative in KIT_SOURCE_FILES:
        if (root / relative).is_symlink():
            raise UpdateError(f"KU-SCOPE-001: symlink を kit ソースに含められません: {relative}")
    for directory in KIT_SOURCE_DIRS:
        files.update(_iter_files(root, directory))
    return tuple(sorted(path for path in files if (root / path).is_file()))


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


def _feature_enabled(manifest: dict[str, Any], feature: str) -> bool:
    node: Any = manifest
    parts = feature.split(".")
    for index, part in enumerate(parts):
        if not isinstance(node, dict) or part not in node:
            return False
        if index > 0 and "enabled" in node and not bool(node["enabled"]):
            return False
        node = node[part]
    if isinstance(node, dict) and "enabled" in node:
        return bool(node["enabled"])
    return bool(node)


def _filtered_outputs(manifest: dict[str, Any]) -> dict[Path, dict[str, Any]]:
    result: dict[Path, dict[str, Any]] = {}
    requirement_enabled = _feature_enabled(manifest, "requirement_analysis")
    for output in manifest.get("outputs") or []:
        if not isinstance(output, dict) or not isinstance(output.get("path"), str):
            raise UpdateError("KU-SCOPE-001: outputs[] の path が不正です")
        if (
            output["path"] == ".cursor/skills/deep-thinking/references/workflow-triage.md"
            and requirement_enabled
        ):
            continue
        feature = output.get("feature")
        features = feature if isinstance(feature, list) else [feature]
        if feature is not None and not any(
            isinstance(item, str) and _feature_enabled(manifest, item)
            for item in features
        ):
            continue
        rel = _safe_rel(output["path"])
        result[rel] = output
    return result


def _copy_app(app_root: Path, work_root: Path) -> None:
    if work_root.exists() or work_root.is_symlink():
        raise UpdateError(f"KU-SCOPE-001: work root が既に存在します: {work_root}")

    def ignore(path: str, names: list[str]) -> set[str]:
        ignored = {".git", "__pycache__"}
        return {name for name in names if name in ignored or name.endswith(".pyc")}

    shutil.copytree(app_root, work_root, symlinks=True, ignore=ignore)


def _replace_tree(source: Path, target: Path) -> None:
    if target.is_symlink():
        raise UpdateError(f"KU-SCOPE-001: 一時作業ツリーの symlink を拒否しました: {target}")
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=True)


def _prepare_work_tree(app_root: Path, kit_root: Path, work_root: Path) -> None:
    _copy_app(app_root, work_root)
    for relative in KIT_SOURCE_DIRS:
        source = kit_root / relative
        if not source.is_dir():
            raise UpdateError(f"KU-SCOPE-001: kit source がありません: {source}")
        _replace_tree(source, work_root / relative)
    for relative in KIT_SOURCE_FILES:
        source = kit_root / relative
        if not source.is_file():
            raise UpdateError(f"KU-SCOPE-001: upstream design がありません: {source}")
        target = work_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _run(command: list[str], cwd: Path, *, allow_failure: bool = False) -> None:
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0 and not allow_failure:
        detail = (result.stderr or result.stdout).strip().splitlines()
        summary = detail[-1] if detail else "出力なし"
        raise UpdateError(f"生成または検証に失敗しました: {summary}")


def _run_candidate_validation(kit_root: Path, work_root: Path) -> None:
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
    _run([*common[:1], common[1], "generate", *common[2:], "--skip-host-update"], work_root)
    _run([*common[:1], common[1], "check", *common[2:]], work_root)
    _run([*common[:1], common[1], "audit", *common[2:]], work_root)

    manifest = _load_manifest(root_manifest, kit_root)
    profile = (
        manifest.get("project", {})
        .get("quality_gate", {})
        .get("profile", "foundation")
    )
    if profile == "application":
        gate = work_root / "bin/quality-gate"
    else:
        gate = work_root / "bin/foundation-gate"
    if gate.is_file():
        command = [str(gate), "verify" if profile == "application" else "self"]
        _run(command, work_root)
    else:
        raise UpdateError(f"KU-OVERLAY-001: quality gate がありません: {gate}")


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


def _source_change_records(
    app_root: Path, clone_root: Path
) -> tuple[list[dict[str, Any]], list[Path]]:
    old_files = set(_kit_files(app_root))
    new_files = set(_kit_files(clone_root))
    changes: list[dict[str, Any]] = []
    for relative in sorted(new_files):
        source = clone_root / relative
        target = _safe_target(app_root, relative)
        candidate = {"sha256": _sha256(source), "mode": _mode(source)}
        current = _current_file_state(app_root, relative)
        if current == candidate:
            continue
        changes.append({
            "path": str(relative),
            "kind": "kit-source",
            "mode": "source",
            "candidate_path": str(source),
            "candidate_sha256": candidate["sha256"],
            "candidate_mode": candidate["mode"],
            "preimage_sha256": current["sha256"],
            "preimage_mode": current["mode"],
            "action": "add" if not target.exists() else "update",
        })
    removed = sorted(old_files - new_files)
    return changes, removed


def _output_change_records(
    app_root: Path,
    work_root: Path,
    old_outputs: dict[Path, dict[str, Any]],
    new_outputs: dict[Path, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[Path], list[tuple[Path, Path]]]:
    changes: list[dict[str, Any]] = []
    for relative, output in sorted(new_outputs.items()):
        candidate = _safe_target(work_root, relative)
        if not candidate.is_file():
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


def _build_plan(app_root: Path, clone_root: Path, work_root: Path,
                *, validate: bool = True, kit_revision: str = "") -> dict[str, Any]:
    app_root = app_root.resolve()
    clone_root = clone_root.resolve()
    work_root = work_root.resolve()
    if not (app_root / "manifest.yaml").is_file():
        raise UpdateError("KU-OVERLAY-001: root manifest がありません。初回セットアップへ渡してください")
    if validate:
        _prepare_work_tree(app_root, clone_root, work_root)
        _run_candidate_validation(clone_root, work_root)

    old_seed = app_root / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"
    new_seed = clone_root / ".cursor/skills/agentic-workflow-foundation/manifest.yaml"
    if not old_seed.is_file() or not new_seed.is_file():
        raise UpdateError("KU-SCOPE-001: foundation manifest がありません")
    old_manifest = _load_manifest(old_seed, clone_root)
    new_manifest = _load_manifest(new_seed, clone_root)
    old_outputs = _filtered_outputs(old_manifest)
    new_outputs = _filtered_outputs(new_manifest)

    source_changes, source_orphans = _source_change_records(app_root, clone_root)
    output_changes, output_orphans, rename_candidates = _output_change_records(
        app_root, work_root, old_outputs, new_outputs
    )
    protected = _protected_paths(old_outputs, new_outputs)
    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "app_root": str(app_root),
        "clone_root": str(clone_root),
        "work_root": str(work_root),
        "kit_revision": kit_revision,
        "changes": sorted(source_changes + output_changes, key=lambda item: item["path"]),
        "orphan": [str(path) for path in sorted(set(source_orphans + output_orphans))],
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
        change["mode"] == "seed"
        for change in output_changes
    ):
        plan["blocking_issues"].append("KU-SEED-001")
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
    if plan.get("blocking_issues"):
        raise UpdateError(
            "KU-ORPHAN-001: 停止要因があります: "
            + ", ".join(plan["blocking_issues"])
        )


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


def _fetch_kit(app_root: Path, kit_root: Path, clone_root: Path) -> dict[str, Any]:
    wrapper = Path(__file__).resolve().parents[1] / "bin/kit-source-fetch-safe"
    if not wrapper.is_file():
        raise UpdateError("KU-SCOPE-001: kit fetch wrapper がありません")
    result = subprocess.run(
        [
            "bash",
            str(wrapper),
            "--kit-root",
            str(kit_root),
            "--app-root",
            str(app_root),
            "--clone-root",
            str(clone_root),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise UpdateError(f"kit の取得に失敗しました (exit {result.returncode})")
    try:
        value = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise UpdateError("KU-SCOPE-001: fetch wrapper の結果が不正です") from exc
    if not isinstance(value, dict) or not value.get("clone_root") or not value.get("sha"):
        raise UpdateError("KU-SCOPE-001: fetch wrapper の revision がありません")
    return value


def _run_application_validation(app_root: Path) -> None:
    manifest_path = app_root / "manifest.yaml"
    foundation_root = app_root / ".cursor/skills/agentic-workflow-foundation"
    if not manifest_path.is_file() or not foundation_root.is_dir():
        raise UpdateError("KU-OVERLAY-001: 適用後の quality gate 入力がありません")
    manifest = _load_manifest(manifest_path, app_root)
    profile = (
        manifest.get("project", {})
        .get("quality_gate", {})
        .get("profile", "foundation")
    )
    if profile == "application":
        gate = app_root / "bin/quality-gate"
        command = [str(gate), "verify"]
    else:
        gate = app_root / "bin/foundation-gate"
        command = [str(gate), "self"]
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


def _default_kit_root(app_root: Path) -> Path:
    return app_root.parent / "agentic-workflow-foundation-kit"


def _default_work_root() -> Path:
    return DEFAULT_WORK_ROOT


def command_plan(args: argparse.Namespace) -> int:
    app_root = Path(args.app_root).resolve()
    kit_root = Path(args.kit_root).resolve() if args.kit_root else _default_kit_root(app_root)
    clone_root = Path(args.clone_root).resolve()
    work_root = Path(args.work_root).resolve()
    if not (app_root / ".git").exists():
        raise UpdateError("KU-SCOPE-001: 対象アプリは Git repository ではありません")
    fetched = _fetch_kit(app_root, kit_root, clone_root)
    plan = _build_plan(
        app_root,
        Path(fetched["clone_root"]),
        work_root,
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
        foundation = app_root / ".cursor/skills/agentic-workflow-foundation/scripts/run_resolved_engine.py"
        if foundation.is_file():
            _run([sys.executable, str(foundation), "check"], app_root)
            _run([sys.executable, str(foundation), "audit"], app_root)
        _run_application_validation(app_root)
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
    plan.add_argument("--kit-root")
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
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FATAL: updater 実行失敗: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

