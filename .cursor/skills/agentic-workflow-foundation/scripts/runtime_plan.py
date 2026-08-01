"""tech_contract runtime file/command action の plan・apply・preflight 実行。"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

FILE_KINDS = frozenset({"create-if-missing", "owned-text-render", "json-key-merge"})
COMMAND_EFFECTS = frozenset({"network", "host_write", "project_write", "lockfile_write"})
PREFLIGHT_KINDS = frozenset({
    "executable-exists",
    "path-exists",
    "json-value-pattern",
    "json-key-present",
    "installed-marker",
    "absent-marker",
    "lockfile-present",
    "lockfile-absent",
    "state-digests",
    "non-empty-workspace",
})
POSTCONDITION_KINDS = frozenset({"capture-toolchain-version", "record-state-digest"})
MARKER_VALIDATION_KINDS = frozenset({"json-field", "executable-file"})
VERSION_QUERY_ARGS = frozenset({"--version", "-version", "version", "-V", "-v"})


class PreflightError(Exception):
    """preflight 検証失敗（修正可能）。"""


class PreflightFatal(Exception):
    """preflight 設定不正（exit 2）。"""


class PathSafetyError(PreflightFatal):
    """project root 外への write / resolve を拒否。"""


class CommandNotFoundError(PreflightFatal):
    """command argv[0] が見つからない（exit 2）。"""


class UndeclaredProjectWriteError(ValueError):
    """read-only postcondition command が project を変更した。"""

    def __init__(self, paths: list[str]):
        self.paths = paths
        super().__init__(f"postcondition command changed undeclared project paths: {', '.join(paths)}")


def digest_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_digest(action: dict) -> str:
    payload = {k: v for k, v in action.items() if k != "evidence_ref"}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def preflight_payload_digest(check: dict) -> str:
    payload = {k: v for k, v in check.items() if k not in {"guidance", "evidence_ref"}}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _split_pointer(key: str) -> list[str]:
    if not key:
        raise ValueError("empty JSON pointer")
    return key.split(".")


def _get_at(doc: object, parts: list[str]) -> object:
    cur = doc
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_at(doc: dict, parts: list[str], value: object) -> None:
    cur: dict = doc
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = copy.deepcopy(value)


def _deep_merge_dict(base: dict, overlay: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def merge_json_owned(current: dict, values: dict, owned_keys: list[str]) -> dict:
    merged = copy.deepcopy(current)
    for key in owned_keys:
        if key not in values:
            raise ValueError(f"missing value for owned key {key!r}")
        parts = _split_pointer(key)
        if len(parts) == 1 and isinstance(values[key], dict):
            existing = merged.get(key)
            if isinstance(existing, dict):
                merged[key] = _deep_merge_dict(existing, values[key])
            else:
                merged[key] = copy.deepcopy(values[key])
        else:
            _set_at(merged, parts, values[key])
    return merged


def resolve_in_project(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel.strip():
        raise PathSafetyError(f"invalid relative path: {rel!r}")
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise PathSafetyError(f"path traversal forbidden: {rel!r}")
    root_real = root.resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root_real)
    except ValueError as exc:
        raise PathSafetyError(f"path escapes project root: {rel!r}") from exc
    return candidate


def render_file_bytes(action: dict, root: Path) -> bytes:
    kind = action["kind"]
    target = resolve_in_project(root, action["target"])
    if kind == "owned-text-render":
        return str(action["content"]).encode("utf-8")
    if kind == "json-key-merge":
        current: dict = {}
        if target.is_file():
            current = _read_json_object(target, action["target"])
        merged = merge_json_owned(current, action["values"], action["owned_keys"])
        return (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if kind == "create-if-missing":
        if "content" in action:
            return str(action["content"]).encode("utf-8")
        if "values" in action:
            return (json.dumps(action["values"], indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        raise ValueError("create-if-missing requires content or values")
    raise ValueError(f"unsupported file action kind: {kind}")


def check_ownership_conflict(action: dict, root: Path) -> str | None:
    target = resolve_in_project(root, action["target"])
    if not target.is_file():
        return None
    existing = target.read_bytes()
    desired = render_file_bytes(action, root)
    if existing == desired:
        return None
    policy = action["conflict_policy"]
    if policy == "merge_owned":
        return None
    if policy == "fail":
        ownership = action["ownership"]
        label = "project-owned で" if ownership == "project" else ""
        return f"{action['target']} は {label}既存内容と異なります（fail）"
    return f"{action['target']} の conflict_policy では上書きできません"


def _atomic_write_bytes(path: Path, payload: bytes, default_mode: int = 0o644) -> None:
    """既存 mode を保って置換し、失敗時は一時ファイルを除去する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    target_mode = stat.S_IMODE(path.stat().st_mode) if path.is_file() else default_mode
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            temp_name = tmp.name
            tmp.write(payload)
        os.chmod(temp_name, target_mode)
        os.replace(temp_name, path)
    except BaseException:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise


def apply_file_action(action: dict, root: Path, dry_run: bool = False) -> None:
    target = resolve_in_project(root, action["target"])
    conflict = check_ownership_conflict(action, root)
    if conflict:
        raise ValueError(conflict)
    if action["kind"] == "create-if-missing" and target.is_file():
        return
    content = render_file_bytes(action, root)
    if dry_run:
        return
    _atomic_write_bytes(target, content)


def collect_file_actions(contract: dict) -> list[dict]:
    raw = (contract.get("runtime_materialization") or {}).get("actions")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("runtime_materialization.actions must be a list")
    return list(raw)


def collect_command_actions(contract: dict) -> list[dict]:
    prov = contract.get("provisioning") or {}
    raw = prov.get("command_actions")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("provisioning.command_actions must be a list")
    return list(raw)


def collect_preflight_checks(contract: dict) -> list[dict]:
    prov = contract.get("provisioning") or {}
    raw = prov.get("preflight_checks")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("provisioning.preflight_checks must be a list")
    return list(raw)


def _read_json_object(path: Path, label: str) -> dict:
    if not path.is_file():
        raise PreflightFatal(f"{label}: JSON target が存在しません: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PreflightFatal(f"{label}: UTF-8 decode 失敗: {exc}") from exc
    except OSError as exc:
        raise PreflightFatal(f"{label}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PreflightFatal(f"{label}: JSON 解析失敗: {exc}") from exc
    if not isinstance(data, dict):
        raise PreflightFatal(f"{label}: JSON root は mapping である必要があります")
    return data


def _read_state_marker(marker_path: Path, label: str) -> dict:
    data = _read_json_object(marker_path, label)
    digests = data.get("digests")
    if not isinstance(digests, dict):
        raise PreflightFatal(f"{label}: digests mapping が必要です")
    for key, value in digests.items():
        if not isinstance(key, str) or not key.strip():
            raise PreflightFatal(f"{label}: digests key が不正です")
        if not isinstance(value, str) or not value.strip():
            raise PreflightFatal(f"{label}: digests[{key!r}] は非空文字列が必要です")
        if value == "absent":
            raise PreflightFatal(f"{label}: digests[{key!r}] に absent は記録できません")
    return data


def _run_marker_validation(validation: dict, target_path: Path, label: str) -> list[str]:
    if not isinstance(validation, dict):
        raise PreflightFatal(f"{label}.validation は mapping である必要があります")
    kind = validation.get("kind")
    if kind == "json-field":
        pointer = validation.get("pointer")
        expected = validation.get("expected")
        if not isinstance(pointer, str) or not pointer.strip():
            raise PreflightFatal(f"{label}.validation.pointer は必須です")
        if not isinstance(expected, str) or not expected.strip():
            raise PreflightFatal(f"{label}.validation.expected は必須です")
        try:
            data = _read_json_object(target_path, label)
        except PreflightFatal as exc:
            return [str(exc)]
        value = _json_pointer_get(data, pointer)
        if value is None:
            return [f"{target_path.name} に {pointer} がありません"]
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        version_pattern = validation.get("version_pattern")
        if version_pattern is not None:
            if not isinstance(version_pattern, str) or not version_pattern.strip():
                raise PreflightFatal(f"{label}.validation.version_pattern が不正です")
            try:
                compiled = re.compile(version_pattern)
            except re.error as exc:
                raise PreflightFatal(f"{label}.validation.version_pattern が不正です: {exc}") from exc
            if not compiled.fullmatch(text):
                return [f"installed-marker 不一致: {pointer}={text!r} pattern={version_pattern!r}"]
        elif text != expected:
            return [f"installed-marker 不一致: {pointer}={text!r} expected={expected!r}"]
        return []
    if kind == "executable-file":
        if not target_path.is_file():
            return [f"{target_path} がありません"]
        if target_path.stat().st_size <= 0:
            return [f"{target_path} が空です"]
        if not os.access(target_path, os.X_OK):
            return [f"{target_path} が executable ではありません"]
        return []
    raise PreflightFatal(f"{label}.validation.kind が未知です: {kind!r}")


def _pattern_fullmatch(pattern: str, text: str, label: str) -> bool:
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise PreflightFatal(f"{label}.pattern が不正です: {exc}") from exc
    return compiled.fullmatch(text) is not None


def _json_pointer_get(data: object, pointer: str) -> object:
    parts = _split_pointer(pointer)
    cur = data
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _atomic_write_json(path: Path, data: dict) -> None:
    payload = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_write_bytes(path, payload)


def _postcondition_generated_paths(action: dict) -> set[str]:
    generated: set[str] = set()
    for post in action.get("postconditions") or []:
        marker = post.get("marker")
        if isinstance(marker, str) and marker.strip():
            generated.add(marker)
    return generated


def validate_capture_argv(argv: object, label: str) -> list[str]:
    """version 取得専用の read-only argv 形だけを許可する。"""
    if (
        not isinstance(argv, list)
        or len(argv) != 2
        or not all(isinstance(arg, str) and arg for arg in argv)
    ):
        raise ValueError(f"{label}.argv は executable + version query 1引数が必要です")
    if argv[1] not in VERSION_QUERY_ARGS:
        raise ValueError(
            f"{label}.argv[1] は version query {sorted(VERSION_QUERY_ARGS)} のいずれかが必要です"
        )
    if Path(argv[0]).name != argv[0] or argv[0].startswith("."):
        raise ValueError(f"{label}.argv[0] は PATH 上の executable 名のみ許可します")
    return list(argv)


def _planned_postconditions(action: dict) -> list[dict]:
    planned: list[dict] = []
    for post in action.get("postconditions") or []:
        item = copy.deepcopy(post)
        marker = post.get("marker")
        item["effects"] = ["project_write"]
        item["writes"] = [marker] if isinstance(marker, str) and marker.strip() else []
        if post.get("kind") == "record-state-digest":
            item["reads"] = list(post.get("paths") or [])
        planned.append(item)
    return planned


def _project_tree_snapshot(root: Path) -> dict[str, tuple[int, int, int]]:
    """永続的な file/dir/symlink 変更を検知する軽量 snapshot。"""
    snapshot: dict[str, tuple[int, int, int]] = {}
    root_abs = root.resolve()
    try:
        for dirpath, dirnames, filenames in os.walk(root_abs, followlinks=False):
            parent = Path(dirpath)
            for name in [*dirnames, *filenames]:
                path = parent / name
                try:
                    metadata = path.lstat()
                except FileNotFoundError:
                    continue
                rel = path.relative_to(root_abs).as_posix()
                snapshot[rel] = (metadata.st_mode, metadata.st_size, metadata.st_mtime_ns)
    except OSError as exc:
        raise PreflightFatal(f"project snapshot failed: {exc}") from exc
    return snapshot


def _snapshot_changes(
    before: dict[str, tuple[int, int, int]],
    after: dict[str, tuple[int, int, int]],
) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def _safe_exists(root: Path, rel: str) -> bool:
    try:
        return resolve_in_project(root, rel).is_file()
    except PathSafetyError:
        return False


def run_preflight(contract: dict, root: Path) -> list[str]:
    errors: list[str] = []
    file_actions = collect_file_actions(contract)
    command_actions = collect_command_actions(contract)
    policy = (contract.get("provisioning") or {}).get("policy")
    if not file_actions and not command_actions and policy != "none":
        errors.append("runtime_materialization.actions と provisioning.command_actions が共に空です")
    for index, check in enumerate(collect_preflight_checks(contract)):
        kind = check.get("kind")
        guidance = check.get("guidance") or "bin/project-setup --plan を確認してください"
        label = f"provisioning.preflight_checks[{index}]"
        try:
            if kind == "executable-exists":
                exe = check.get("executable")
                if not isinstance(exe, str) or not exe.strip():
                    raise PreflightFatal(f"{label}.executable は必須です")
                if shutil.which(exe) is None:
                    errors.append(f"{exe} がありません。{guidance}")
            elif kind == "path-exists":
                rel = check.get("target")
                if not isinstance(rel, str) or not rel.strip():
                    raise PreflightFatal(f"{label}.target は必須です")
                if not resolve_in_project(root, rel).is_file():
                    errors.append(f"{rel} がありません。{guidance}")
            elif kind == "json-value-pattern":
                rel = check.get("target")
                pointer = check.get("pointer")
                pattern = check.get("pattern")
                if not isinstance(rel, str) or not rel.strip():
                    raise PreflightFatal(f"{label}.target は必須です")
                if not isinstance(pointer, str) or not pointer.strip():
                    raise PreflightFatal(f"{label}.pointer は必須です")
                if not isinstance(pattern, str) or not pattern.strip():
                    raise PreflightFatal(f"{label}.pattern は必須です")
                path = resolve_in_project(root, rel)
                if not path.is_file():
                    errors.append(f"{rel} がありません。{guidance}")
                    continue
                try:
                    data = _read_json_object(path, label)
                except PreflightFatal as exc:
                    raise exc
                value = _json_pointer_get(data, pointer)
                if value is None:
                    errors.append(f"{rel} に {pointer} がありません。{guidance}")
                    continue
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                if not _pattern_fullmatch(pattern, text, label):
                    errors.append(f"json-value-pattern 不一致: {pointer}={text!r} pattern={pattern!r}。{guidance}")
            elif kind == "json-key-present":
                rel = check.get("target")
                key = check.get("key")
                if not isinstance(rel, str) or not rel.strip():
                    raise PreflightFatal(f"{label}.target は必須です")
                if not isinstance(key, str) or not key.strip():
                    raise PreflightFatal(f"{label}.key は必須です")
                path = resolve_in_project(root, rel)
                if not path.is_file():
                    errors.append(f"{rel} がありません。{guidance}")
                    continue
                data = _read_json_object(path, label)
                if key not in data:
                    errors.append(f"{rel} に {key} がありません。{guidance}")
            elif kind == "installed-marker":
                rel = check.get("target")
                covers = check.get("covers_packages")
                validation = check.get("validation")
                if not isinstance(rel, str) or not rel.strip():
                    raise PreflightFatal(f"{label}.target は必須です")
                if not isinstance(covers, list) or not covers:
                    raise PreflightFatal(f"{label}.covers_packages は非空配列必須です")
                for index, pkg in enumerate(covers):
                    if not isinstance(pkg, str) or not pkg.strip():
                        raise PreflightFatal(f"{label}.covers_packages[{index}] が不正です")
                if not isinstance(validation, dict):
                    raise PreflightFatal(f"{label}.validation は必須です")
                path = resolve_in_project(root, rel)
                if not path.is_file():
                    errors.append(f"{rel} がありません。{guidance}")
                    continue
                errors.extend(_run_marker_validation(validation, path, label))
            elif kind == "absent-marker":
                rel = check.get("target")
                covers = check.get("covers_packages")
                if not isinstance(rel, str) or not rel.strip():
                    raise PreflightFatal(f"{label}.target は必須です")
                if not isinstance(covers, list) or not covers:
                    raise PreflightFatal(f"{label}.covers_packages は非空配列必須です")
                for index, pkg in enumerate(covers):
                    if not isinstance(pkg, str) or not pkg.strip():
                        raise PreflightFatal(f"{label}.covers_packages[{index}] が不正です")
                if resolve_in_project(root, rel).exists():
                    errors.append(f"{rel} が存在してはいけません。{guidance}")
            elif kind == "lockfile-present":
                rel = check.get("target")
                if not isinstance(rel, str) or not rel.strip():
                    raise PreflightFatal(f"{label}.target は必須です")
                if not resolve_in_project(root, rel).is_file():
                    errors.append(f"{rel} がありません。{guidance}")
            elif kind == "lockfile-absent":
                rel = check.get("target")
                if not isinstance(rel, str) or not rel.strip():
                    raise PreflightFatal(f"{label}.target は必須です")
                if resolve_in_project(root, rel).is_file():
                    errors.append(f"{rel} が存在してはいけません。{guidance}")
            elif kind == "state-digests":
                marker_rel = check.get("marker")
                paths = check.get("paths")
                if not isinstance(marker_rel, str) or not marker_rel.strip():
                    raise PreflightFatal(f"{label}.marker は必須です")
                if not isinstance(paths, list) or not paths:
                    raise PreflightFatal(f"{label}.paths は非空配列必須です")
                marker_path = resolve_in_project(root, marker_rel)
                if not marker_path.is_file():
                    errors.append(f"{marker_rel} がありません。{guidance}")
                    continue
                try:
                    recorded = _read_state_marker(marker_path, label)
                except PreflightFatal as exc:
                    raise exc
                digests = recorded["digests"]
                for path_index, rel in enumerate(paths):
                    if not isinstance(rel, str) or not rel.strip():
                        raise PreflightFatal(f"{label}.paths[{path_index}] が不正です")
                    if rel.startswith("/") or ".." in Path(rel).parts:
                        raise PreflightFatal(f"{label}.paths[{path_index}] が不正です")
                    target_path = resolve_in_project(root, rel)
                    if not target_path.is_file():
                        errors.append(f"{rel} がありません。{guidance}")
                        continue
                    expected = digests.get(rel)
                    if not isinstance(expected, str) or expected == "absent":
                        errors.append(f"{marker_rel} に {rel} の有効 digest 記録がありません。{guidance}")
                        continue
                    current = digest_path(target_path)
                    if current == "absent":
                        errors.append(f"{rel} の digest を計算できません。{guidance}")
                        continue
                    if current != expected:
                        errors.append(
                            f"state-digests 不一致: {rel} expected={expected} current={current}。{guidance}"
                        )
            elif kind == "non-empty-workspace":
                if not file_actions:
                    errors.append(f"workspace が空です。{guidance}")
                else:
                    materialized = any(resolve_in_project(root, a["target"]).is_file() for a in file_actions)
                    if not materialized:
                        errors.append(f"runtime ファイルが未 materialize です。{guidance}")
            else:
                raise PreflightFatal(f"未知の preflight kind: {kind}")
        except PathSafetyError as exc:
            raise exc
        except PreflightFatal as exc:
            raise exc
        except UnicodeDecodeError as exc:
            raise PreflightFatal(f"{label}: UTF-8 decode 失敗: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PreflightFatal(f"{label}: JSON 解析失敗: {exc}") from exc
        except re.error as exc:
            raise PreflightFatal(f"{label}.pattern が不正です: {exc}") from exc
        except (TypeError, AttributeError) as exc:
            raise PreflightFatal(f"{label}: {exc}") from exc
        except OSError as exc:
            raise PreflightFatal(f"{label}: {exc}") from exc
    return errors


def build_plan(contract: dict, root: Path) -> dict:
    actions: list[dict] = []
    for action in collect_file_actions(contract):
        target = resolve_in_project(root, action["target"])
        rendered = render_file_bytes(action, root)
        actions.append({
            "phase": "file",
            "kind": action["kind"],
            "target": action["target"],
            "ownership": action["ownership"],
            "conflict_policy": action["conflict_policy"],
            "payload_digest": payload_digest(action),
            "preimage": digest_path(target),
            "postimage": hashlib.sha256(rendered).hexdigest(),
        })
    for index, action in enumerate(collect_command_actions(contract)):
        actions.append({
            "phase": "command",
            "index": index,
            "argv": list(action["argv"]),
            "cwd": action.get("cwd", "."),
            "effects": list(action.get("effects") or []),
            "writes": list(action.get("writes") or []),
            "postconditions": _planned_postconditions(action),
            "payload_digest": payload_digest(action),
        })
    plan = {
        "contract_digest": contract["contract_digest"],
        "manifest_preimage": digest_path(root / "manifest.yaml"),
        "actions": actions,
    }
    plan["plan_digest"] = hashlib.sha256(_canonical_json(plan).encode("utf-8")).hexdigest()
    return plan


def _track_writes(root: Path, writes: list[str], before: dict[str, str], changed: list[str]) -> None:
    for rel in writes:
        after = digest_path(resolve_in_project(root, rel))
        if after != before.get(rel, "absent") and rel not in changed:
            changed.append(rel)


def _apply_postconditions(action: dict, root: Path, cwd: Path) -> None:
    for post in action.get("postconditions") or []:
        kind = post.get("kind")
        if kind == "capture-toolchain-version":
            argv = validate_capture_argv(
                post.get("argv"),
                "postcondition.capture-toolchain-version",
            )
            before_project = _project_tree_snapshot(root)
            result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
            changed_by_query = _snapshot_changes(before_project, _project_tree_snapshot(root))
            if changed_by_query:
                raise UndeclaredProjectWriteError(changed_by_query)
            if result.returncode != 0:
                raise ValueError("postcondition capture failed")
            version = result.stdout.strip()
            pattern = post.get("pattern")
            if not isinstance(pattern, str) or not pattern.strip():
                raise ValueError("postcondition pattern is required")
            if not _pattern_fullmatch(pattern, version, "postcondition.capture-toolchain-version"):
                raise ValueError("postcondition version pattern mismatch")
            marker = resolve_in_project(root, post["marker"])
            data: dict = {}
            if marker.is_file():
                data = _read_json_object(marker, "postcondition.capture-toolchain-version")
            parts = _split_pointer(post["pointer"])
            _set_at(data, parts, version)
            _atomic_write_json(marker, data)
        elif kind == "record-state-digest":
            marker_rel = post.get("marker")
            path_list = post.get("paths") or []
            if not isinstance(marker_rel, str) or not marker_rel.strip():
                raise ValueError("record-state-digest marker is required")
            if not isinstance(path_list, list) or not path_list:
                raise ValueError("record-state-digest paths must be non-empty")
            for path_index, rel in enumerate(path_list):
                if not isinstance(rel, str) or not rel.strip():
                    raise ValueError(f"record-state-digest paths[{path_index}] invalid")
                if rel.startswith("/") or ".." in Path(rel).parts:
                    raise ValueError(f"record-state-digest paths[{path_index}] invalid")
            marker = resolve_in_project(root, marker_rel)
            data: dict = {}
            if marker.is_file():
                data = _read_json_object(marker, "postcondition.record-state-digest")
            digests = data.get("digests")
            if not isinstance(digests, dict):
                digests = {}
            for rel in path_list:
                target = resolve_in_project(root, rel)
                if not target.is_file():
                    raise ValueError(f"record-state-digest path missing: {rel}")
                digest = digest_path(target)
                if digest == "absent":
                    raise ValueError(f"record-state-digest path unreadable: {rel}")
                digests[rel] = digest
            data["digests"] = digests
            _atomic_write_json(marker, data)
        else:
            raise ValueError(f"unknown postcondition kind: {kind}")


def _default_runner(argv: list[str], cwd: Path) -> int:
    exe = argv[0]
    if os.path.sep in exe or exe.startswith("."):
        candidate = (cwd / exe).resolve()
        if not candidate.is_file():
            raise CommandNotFoundError(f"command not found: {exe}")
    elif shutil.which(exe) is None:
        raise CommandNotFoundError(f"command not found: {exe}")
    return subprocess.run(argv, cwd=cwd, check=False).returncode


def apply_plan(
    plan: dict,
    contract: dict,
    root: Path,
    command_runner: Callable[[list[str], Path], int] | None = None,
) -> tuple[int, dict]:
    file_actions = collect_file_actions(contract)
    command_actions = collect_command_actions(contract)
    policy = (contract.get("provisioning") or {}).get("policy")
    if not file_actions and not command_actions:
        if policy == "none":
            return 0, {
                "completed": [],
                "pending": [],
                "changed_targets": [],
                "recovery": "不要",
            }
        return 2, _report([], plan.get("actions", []), [], "runtime_materialization.actions と command_actions が共に空です")
    completed: list[str] = []
    changed_targets: list[str] = []
    pending = list(plan["actions"])
    runner = command_runner or _default_runner

    file_index = 0
    command_index = 0
    while pending:
        planned = pending[0]
        if planned["phase"] == "file":
            action = file_actions[file_index]
            file_index += 1
            target = resolve_in_project(root, action["target"])
            if digest_path(target) != planned["preimage"]:
                return 2, _report(completed, pending, changed_targets, "target preimage drift")
            if payload_digest(action) != planned["payload_digest"]:
                return 2, _report(completed, pending, changed_targets, "payload digest drift")
            before = digest_path(target)
            try:
                apply_file_action(action, root, dry_run=False)
            except (ValueError, PathSafetyError, PreflightFatal) as exc:
                after = digest_path(target)
                if after != before:
                    changed_targets.append(action["target"])
                return 2, _report(completed, pending, changed_targets, str(exc))
            after = digest_path(target)
            expected = planned.get("postimage")
            if expected and after != expected:
                changed_targets.append(action["target"])
                return 2, _report(completed, pending, changed_targets, "postcondition digest mismatch")
            if after != before:
                changed_targets.append(action["target"])
            completed.append(action["target"])
            pending.pop(0)
            continue

        action = command_actions[command_index]
        command_index += 1
        if payload_digest(action) != planned["payload_digest"]:
            return 2, _report(completed, pending, changed_targets, "command payload drift")
        writes = list(action.get("writes") or planned.get("writes") or [])
        post_generated = _postcondition_generated_paths(action)
        command_owned = [rel for rel in writes if rel not in post_generated]
        tracked = list(dict.fromkeys(writes))
        before_writes = {
            rel: digest_path(resolve_in_project(root, rel)) if _safe_exists(root, rel) else "absent"
            for rel in tracked
        }
        cwd = resolve_in_project(root, action.get("cwd") or ".")
        try:
            code = runner(list(action["argv"]), cwd)
        except CommandNotFoundError as exc:
            _track_writes(root, tracked, before_writes, changed_targets)
            return 2, _report(completed, pending, changed_targets, str(exc))
        if code != 0:
            _track_writes(root, tracked, before_writes, changed_targets)
            return 1, _report(completed, pending, changed_targets, "command action failed")
        missing_command = [
            rel for rel in command_owned
            if not resolve_in_project(root, rel).is_file()
        ]
        if missing_command:
            _track_writes(root, tracked, before_writes, changed_targets)
            return 2, _report(
                completed, pending, changed_targets,
                f"declared writes missing: {', '.join(missing_command)}",
            )
        try:
            _apply_postconditions(action, root, cwd)
        except (ValueError, json.JSONDecodeError, OSError, PreflightFatal) as exc:
            if isinstance(exc, UndeclaredProjectWriteError):
                for rel in exc.paths:
                    if rel not in changed_targets:
                        changed_targets.append(rel)
            _track_writes(root, tracked, before_writes, changed_targets)
            return 2, _report(completed, pending, changed_targets, f"postcondition failed: {exc}")
        _track_writes(root, tracked, before_writes, changed_targets)
        missing_all = [rel for rel in writes if not resolve_in_project(root, rel).is_file()]
        if missing_all:
            return 2, _report(
                completed, pending, changed_targets,
                f"write not materialized after postcondition: {', '.join(missing_all)}",
            )
        completed.append(f"command:{command_index - 1}")
        pending.pop(0)

    if file_actions:
        missing = [a["target"] for a in file_actions if a["target"] not in completed]
        if missing:
            return 2, _report(completed, [], changed_targets, f"file actions not executed: {', '.join(missing)}")

    return 0, {
        "completed": completed,
        "pending": [],
        "changed_targets": changed_targets,
        "recovery": "不要",
    }


def _report(completed: list[str], pending: list[dict], changed: list[str], recovery: str) -> dict:
    return {
        "completed": completed,
        "pending": [
            x["target"] if x.get("phase") == "file" else f"command:{x.get('index')}"
            for x in pending
        ],
        "changed_targets": changed,
        "recovery": recovery,
    }
