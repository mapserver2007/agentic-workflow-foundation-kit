#!/usr/bin/env python3
"""immutable design docs と root manifest を解決して engine を実行する foundation 専用ラッパー。"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
ENGINE_DIR = os.path.join(ROOT, ".cursor", "skills", "agentic-workflow-engine", "scripts")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import genlib  # noqa: E402

ROOT_OVERLAY_KEYS = (
    "project",
    "tech_stack",
    "session",
    "quality_gate_contract",
    "domain_docs",
    "code_review",
    "github_pr",
    "github_issue",
    "coderabbit",
    "agent_workflow",
    "cross_repo_knowledge",
    "dual_thinking",
)
FRAMEWORK_OVERLAY_KEYS = ("accd_axes",)
UPSTREAM_DESIGN_INPUTS = (
    (
        ".cursor/docs/AI_AGENT_UNIFIED_DESIGN.md",
        "session-management-and-layered-architecture",
    ),
    (
        ".cursor/docs/AI_BUSINESS_AGENT_SUITE.md",
        "agent-conduct-and-accd",
    ),
)


def _yaml_quote(value) -> str:
    s = "" if value is None else str(value)
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


def _dump_scalar_key(key: str, value, indent: int) -> list[str]:
    pad = " " * indent
    if value is None:
        return [f"{pad}{key}:"]
    if isinstance(value, bool):
        return [f"{pad}{key}: {'true' if value else 'false'}"]
    if isinstance(value, int):
        return [f"{pad}{key}: {value}"]
    s = str(value)
    if "\n" in s:
        lines = [f"{pad}{key}: |"]
        block_pad = " " * (indent + 2)
        for line in s.split("\n"):
            lines.append(f"{block_pad}{line}")
        return lines
    return [f"{pad}{key}: {_yaml_quote(s)}"]


def _yaml_scalar(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return _yaml_quote(value)


def _dump_yaml_node(value, indent: int = 0):
    pad = " " * indent
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_dump_yaml_node(item, indent + 2))
            else:
                lines.extend(_dump_scalar_key(key, item, indent))
        return lines
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{pad}-")
                    continue
                first = True
                for key, child in item.items():
                    prefix = f"{pad}- " if first else " " * (indent + 2)
                    first = False
                    if isinstance(child, (dict, list)):
                        lines.append(f"{prefix}{key}:")
                        lines.extend(_dump_yaml_node(child, indent + 4))
                    elif isinstance(child, str) and "\n" in child:
                        lines.append(f"{prefix}{key}: |")
                        block_pad = " " * (len(prefix) + 2)
                        for line in child.split("\n"):
                            lines.append(f"{block_pad}{line}")
                    else:
                        lines.append(f"{prefix}{key}: {_yaml_scalar(child)}")
            elif isinstance(item, list):
                lines.append(f"{pad}-")
                lines.extend(_dump_yaml_node(item, indent + 2))
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
        return lines
    lines.append(f"{pad}{_yaml_scalar(value)}")
    return lines


def dump_manifest(manifest: dict) -> str:
    """engine の最小 YAML ローダが読める block style YAML を返す。"""
    return "\n".join(_dump_yaml_node(manifest)) + "\n"


def _normalize_accd_axis(axis: dict, base: dict | None = None) -> dict:
    normalized = dict(base or {})
    normalized.update(axis)
    if "adopted" not in axis and axis.get("impl"):
        normalized["adopted"] = axis["impl"]
    if "adopted" not in normalized:
        normalized["adopted"] = "軽量実装（開発型 / パイプライン型 / ドキュメント型では自動採用）"
    if "not_adopted" not in normalized:
        normalized["not_adopted"] = "BAS 固有の重い機構（経営型で必要時のみ検討）"
    return normalized


def _merge_accd_axes(seed_axes, overlay_axes):
    if not isinstance(overlay_axes, list):
        return seed_axes

    seed_by_id = {
        axis.get("id"): axis
        for axis in seed_axes or []
        if isinstance(axis, dict) and axis.get("id")
    }
    overlay_by_id = {
        axis.get("id"): axis
        for axis in overlay_axes
        if isinstance(axis, dict) and axis.get("id")
    }

    merged = []
    seen = set()
    for axis in seed_axes or []:
        if not isinstance(axis, dict):
            merged.append(axis)
            continue
        axis_id = axis.get("id")
        override = overlay_by_id.get(axis_id)
        merged.append(_normalize_accd_axis(override or {}, axis))
        seen.add(axis_id)

    for axis in overlay_axes:
        if not isinstance(axis, dict):
            continue
        axis_id = axis.get("id")
        if axis_id in seen:
            continue
        merged.append(_normalize_accd_axis(axis, seed_by_id.get(axis_id)))
    return merged


def _apply_framework_overlay(merged: dict, overlay: dict) -> dict:
    overlay_framework = overlay.get("framework")
    if not isinstance(overlay_framework, dict):
        return merged

    framework = dict(merged.get("framework") or {})
    for key in FRAMEWORK_OVERLAY_KEYS:
        if key == "accd_axes" and key in overlay_framework:
            framework[key] = _merge_accd_axes(
                framework.get("accd_axes") or [],
                overlay_framework.get("accd_axes"),
            )
    merged["framework"] = framework
    return merged


def _upstream_design_metadata() -> list[dict]:
    """immutable upstream docs の存在と fingerprint を resolved manifest に記録する。"""
    items = []
    for rel_path, role in UPSTREAM_DESIGN_INPUTS:
        abs_path = os.path.join(ROOT, rel_path)
        item = {
            "path": rel_path,
            "role": role,
            "status": "missing",
            "sha256": "",
        }
        if os.path.isfile(abs_path):
            item["status"] = "present"
            item["sha256"] = genlib.sha256_file(abs_path)
        items.append(item)
    return items


def _apply_upstream_design_inputs(merged: dict) -> dict:
    """統一設計書を stateless input として resolved manifest にだけ反映する。"""
    framework = dict(merged.get("framework") or {})
    framework["upstream_design_inputs"] = _upstream_design_metadata()

    handoff = dict(framework.get("handoff") or {})
    handoff["resolved_policy"] = (
        "immutable upstream docs + seed defaults + root manifest から、"
        "毎回一時 resolved manifest/templates を生成して engine に渡す"
    )
    framework["handoff"] = handoff
    merged["framework"] = framework
    return merged


def _is_feature_enabled(manifest: dict, feature: str) -> bool:
    """feature トグルを評価する。

    トップレベル（code_review / agent_workflow）と dot パス
    （agent_workflow.orchestrator_skill / agent_workflow.maintenance_docs）に対応する。
    末端が dict で enabled キーを持つ場合はその値を、それ以外は truthiness を返す。
    """
    if not feature:
        return False
    node: object = manifest
    parts = feature.split(".")
    for i, part in enumerate(parts):
        if not isinstance(node, dict):
            return False
        if i > 0 and "enabled" in node and not bool(node["enabled"]):
            return False
        node = node.get(part)
        if node is None:
            return False
        if i == len(parts) - 1:
            if isinstance(node, dict) and "enabled" in node:
                return bool(node.get("enabled"))
            return bool(node)
    return False


_LEGACY_WORKFLOW_KEY = "execute_skill"
_CANONICAL_WORKFLOW_KEY = "orchestrator_skill"


def _migrate_agent_workflow_keys(manifest: dict) -> dict:
    """agent_workflow.execute_skill → orchestrator_skill の正規化（fail-closed）。

    - 旧キーのみ → 新キーへ移行
    - 新旧が同値で併存 → 旧キーを除去
    - 新旧が異なる値で併存 → exit 2（暗黙の選択をしない）
    """
    aw = manifest.get("agent_workflow")
    if not isinstance(aw, dict):
        return manifest

    has_old = _LEGACY_WORKFLOW_KEY in aw
    has_new = _CANONICAL_WORKFLOW_KEY in aw

    if has_old and has_new:
        if aw[_LEGACY_WORKFLOW_KEY] != aw[_CANONICAL_WORKFLOW_KEY]:
            print(
                f"FATAL: agent_workflow に旧キー '{_LEGACY_WORKFLOW_KEY}: {aw[_LEGACY_WORKFLOW_KEY]}' と "
                f"新キー '{_CANONICAL_WORKFLOW_KEY}: {aw[_CANONICAL_WORKFLOW_KEY]}' が異なる値で併存。"
                f"手動で解決してください。",
                file=sys.stderr,
            )
            sys.exit(2)
        del aw[_LEGACY_WORKFLOW_KEY]
        print(f"[migrate] agent_workflow.{_LEGACY_WORKFLOW_KEY} を除去（同値の {_CANONICAL_WORKFLOW_KEY} が存在）")
    elif has_old and not has_new:
        aw[_CANONICAL_WORKFLOW_KEY] = aw.pop(_LEGACY_WORKFLOW_KEY)
        print(f"[migrate] agent_workflow.{_LEGACY_WORKFLOW_KEY} → {_CANONICAL_WORKFLOW_KEY} へ移行")

    return manifest


def _migrate_root_manifest_file(root_manifest_path: str) -> int:
    """root manifest ファイルのテキストレベルで旧キーを正規化する。

    dict レベルの検証は _migrate_agent_workflow_keys で行うため、
    ここでは検証済みのテキスト置換のみ行う。0=更新あり/不要、2=競合。
    """
    if not os.path.isfile(root_manifest_path):
        return 0

    with open(root_manifest_path, "r", encoding="utf-8") as f:
        text = f.read()

    import re

    old_key_pat = re.compile(r"^(\s+)execute_skill:", re.MULTILINE)
    new_key_pat = re.compile(r"^(\s+)orchestrator_skill:", re.MULTILINE)
    old_matches = old_key_pat.findall(text)
    new_matches = new_key_pat.findall(text)

    if not old_matches:
        return 0

    if old_matches and new_matches:
        old_line = re.search(r"^\s+execute_skill:\s*(.+)$", text, re.MULTILINE)
        new_line = re.search(r"^\s+orchestrator_skill:\s*(.+)$", text, re.MULTILINE)
        if old_line and new_line and old_line.group(1).strip() != new_line.group(1).strip():
            print(
                "FATAL: root manifest に execute_skill と orchestrator_skill が異なる値で併存。",
                file=sys.stderr,
            )
            return 2
        updated = re.sub(
            r"^\s+execute_skill:.*\n?",
            "",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        updated = re.sub(r"execute_skill", "orchestrator_skill", text)
    updated = re.sub(
        r"execute-agent-workflow",
        "workflow-orchestrator",
        updated,
    )

    if updated != text:
        with open(root_manifest_path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"[migrate] root manifest のテキストレベル正規化完了: {root_manifest_path}")
    return 0


def _cleanup_legacy_skill_dir() -> int:
    """旧生成ディレクトリ .cursor/skills/execute-agent-workflow/ を安全に削除する。

    - 生成マーカー（agentic-workflow-foundation スキルの生成物）が確認できる SKILL.md のみ削除
    - 想定外の内容・追加ファイルがある場合は exit 2
    - 新スキルが存在しない場合は exit 2（新旧同時不在を防止）
    """
    legacy_dir = os.path.join(ROOT, ".cursor", "skills", "execute-agent-workflow")
    new_dir = os.path.join(ROOT, ".cursor", "skills", "workflow-orchestrator")

    if not os.path.isdir(legacy_dir):
        return 0

    if not os.path.isdir(new_dir):
        print(
            "FATAL: 旧ディレクトリ execute-agent-workflow が存在するが "
            "新ディレクトリ workflow-orchestrator が未生成。先に generate を実行してください。",
            file=sys.stderr,
        )
        return 2

    entries = os.listdir(legacy_dir)
    if set(entries) != {"SKILL.md"}:
        print(
            f"FATAL: execute-agent-workflow/ に想定外のファイルが存在: {entries}. "
            f"手動で確認してください。",
            file=sys.stderr,
        )
        return 2

    skill_path = os.path.join(legacy_dir, "SKILL.md")
    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()
    if "agentic-workflow-foundation" not in content:
        print(
            "FATAL: execute-agent-workflow/SKILL.md に生成マーカーがありません。手動で確認してください。",
            file=sys.stderr,
        )
        return 2

    shutil.rmtree(legacy_dir)
    print("[cleanup] 旧ディレクトリ .cursor/skills/execute-agent-workflow/ を安全に削除")
    return 0


_LEGACY_WORKFLOW_DOCS = {
    "02-task-decision.md": "# ①退出ゲート — タスク確定の判定",
    "03-report-creation.md": "# ③ タスクレポートの作成",
    "04-implementation.md": "# ④ 実装の実行",
    "05-testing.md": "# ⑤ テスト実装",
    "06-pr-review.md": "# ⑥ PR レビュー検証",
    "07-completion.md": "# ⑦ 完了報告",
}


def _cleanup_legacy_workflow_docs() -> int:
    """連番化前の生成済み step docs を生成マーカー付きの内容だけ安全に削除する。"""
    workflow_dir = os.path.join(ROOT, "docs", "agent-tasks", "agent-workflow")
    for filename, expected_heading in _LEGACY_WORKFLOW_DOCS.items():
        path = os.path.join(workflow_dir, filename)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().rstrip("\n")
        if first_line != expected_heading:
            print(
                f"FATAL: 旧 step doc '{path}' の内容が想定と異なります。"
                "手動で確認してください。",
                file=sys.stderr,
            )
            return 2
        os.remove(path)
        print(f"[cleanup] 旧 step doc を削除: {path}")
    return 0


def _filter_outputs_by_features(manifest: dict) -> dict:
    """feature フラグが無効な outputs エントリを除外する。

    outputs[].feature が指定されている場合、対応する feature トグルが
    truthy でなければそのエントリを生成対象から除外する。
    feature が未指定の outputs はそのまま通過する。

    feature がリスト（例: [code_review, github_pr]）の場合は OR 判定:
    いずれか1つでも enabled なら生成対象に含める。
    """
    outputs = manifest.get("outputs") or []
    filtered = []
    for out in outputs:
        feature = out.get("feature")
        if feature is None:
            filtered.append(out)
            continue
        features = feature if isinstance(feature, list) else [feature]
        if any(_is_feature_enabled(manifest, f) for f in features):
            filtered.append(out)
    manifest["outputs"] = filtered
    return manifest


def resolved_manifest(seed_manifest_path: str, root_manifest_path: str) -> dict:
    manifest = genlib.load_manifest(seed_manifest_path)
    if not os.path.isfile(root_manifest_path):
        return _filter_outputs_by_features(_apply_upstream_design_inputs(manifest))

    overlay = genlib.load_manifest(root_manifest_path)
    _migrate_agent_workflow_keys(overlay)
    merged = dict(manifest)
    for key in ROOT_OVERLAY_KEYS:
        if key not in overlay:
            continue
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(overlay[key], dict)
        ):
            merged[key] = genlib.deep_merge(merged[key], overlay[key])
        else:
            merged[key] = overlay[key]
    merged = _apply_framework_overlay(merged, overlay)
    merged = _apply_upstream_design_inputs(merged)
    return _filter_outputs_by_features(merged)


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_top_block(lines, key: str):
    """インデント0の `key:` 行から、その配下（インデント>0）が続く範囲を返す。"""
    start = None
    for idx, line in enumerate(lines):
        if line.rstrip() == f"{key}:" and _indent_of(line) == 0:
            start = idx
            break
    if start is None:
        return None, None
    last = start
    j = start + 1
    while j < len(lines):
        if lines[j].strip() == "":
            j += 1
            continue
        if _indent_of(lines[j]) > 0:
            last = j
            j += 1
            continue
        break
    return start, last


def bootstrap_root_manifest(seed_manifest_path: str, root_manifest_path: str) -> int:
    """root manifest の framework ブロックを seed から単一 SoT として同期する。

    生成に実際に使われる framework は seed が SoT（resolved_manifest が seed.framework を基底にし、
    root からは ROOT_OVERLAY_KEYS / framework.accd_axes のみ overlay する）。root の framework は
    生成に使われない複製であり、手編集はドリフト源になる。本コマンドは framework ブロックだけを
    seed 由来に揃え、root のヘッダ・project.* / tech_stack / quality_gate などの確定値は保持する。
    """
    with open(seed_manifest_path, "r", encoding="utf-8") as f:
        seed_text = f.read()

    if not os.path.isfile(root_manifest_path):
        with open(root_manifest_path, "w", encoding="utf-8") as f:
            f.write(seed_text)
        print("[bootstrap] PASS: root manifest を seed から新規生成（project.* は Phase 1.5 で確定）")
        return 0

    with open(root_manifest_path, "r", encoding="utf-8") as f:
        root_text = f.read()

    newline = "\r\n" if "\r\n" in root_text else "\n"
    seed_lines = [ln.rstrip("\r") for ln in seed_text.split("\n")]
    root_lines = [ln.rstrip("\r") for ln in root_text.split("\n")]

    s_start, s_last = _find_top_block(seed_lines, "framework")
    r_start, r_last = _find_top_block(root_lines, "framework")
    if s_start is None or r_start is None:
        print("[bootstrap] ERROR: framework ブロックを特定できない", file=sys.stderr)
        return 2

    framework_block = seed_lines[s_start:s_last + 1]
    new_lines = root_lines[:r_start] + framework_block + root_lines[r_last + 1:]
    new_text = newline.join(new_lines)
    changed = new_text != root_text

    if changed:
        with open(root_manifest_path, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
    print(f"[bootstrap] PASS: framework を seed から root へ同期（{'更新あり' if changed else '更新なし=冪等'}）")
    return 0


def prepare_skill_dir(resolved_dir: str, manifest: dict) -> str:
    with open(os.path.join(resolved_dir, "manifest.yaml"), "w", encoding="utf-8") as f:
        f.write(dump_manifest(manifest))
    shutil.copytree(
        os.path.join(SKILL_DIR, "templates"),
        os.path.join(resolved_dir, "templates"),
    )
    return resolved_dir


def _run_dual_thinking_validator(manifest: dict) -> int:
    """dual_thinking が有効なら静的契約検査を実行する。無効時は skip。"""
    if not _is_feature_enabled(manifest, "dual_thinking"):
        return 0
    config_path = os.path.join(
        ROOT, ".cursor", "skills", "dual-thinking", "config.yaml",
    )
    if not os.path.isfile(config_path):
        print("[validate_dual_thinking] SKIP: config.yaml 不在（feature 有効だが未生成）")
        return 0
    from validate_dual_thinking import run as validate_run
    return validate_run(config_path)


def run_engine(command: str, resolved_dir: str, manifest: dict | None = None) -> int:
    if command in ("generate", "check"):
        args = [
            sys.executable,
            os.path.join(ENGINE_DIR, "generate.py"),
            "--skill-dir",
            resolved_dir,
        ]
        if command == "check":
            args.append("--check")
    elif command == "audit":
        args = [
            sys.executable,
            os.path.join(ENGINE_DIR, "audit.py"),
            "--skill-dir",
            resolved_dir,
        ]
    else:
        raise ValueError(f"未知の command: {command}")
    rc = subprocess.call(args, cwd=ROOT)
    if rc != 0:
        return rc
    if command == "audit" and manifest is not None:
        return _run_dual_thinking_validator(manifest)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="foundation の resolved manifest で engine を実行する")
    parser.add_argument("command", choices=("generate", "audit", "check", "bootstrap"))
    parser.add_argument("--seed-manifest", default=os.path.join(SKILL_DIR, "manifest.yaml"))
    parser.add_argument("--root-manifest", default=os.path.join(ROOT, "manifest.yaml"))
    args = parser.parse_args(argv)

    rc = _migrate_root_manifest_file(args.root_manifest)
    if rc != 0:
        return rc

    if args.command == "bootstrap":
        try:
            return bootstrap_root_manifest(args.seed_manifest, args.root_manifest)
        except OSError as e:
            print(f"FATAL: bootstrap 失敗: {e}", file=sys.stderr)
            return 2

    try:
        manifest = resolved_manifest(args.seed_manifest, args.root_manifest)
        with tempfile.TemporaryDirectory(
            prefix=".resolved-agentic-workflow-foundation-",
            dir=os.path.join(ROOT, ".cursor", "skills"),
        ) as tmp_skill_dir:
            resolved_dir = prepare_skill_dir(tmp_skill_dir, manifest)
            rc = run_engine(args.command, resolved_dir, manifest)
            if rc != 0:
                return rc
            if args.command == "generate":
                rc = _cleanup_legacy_workflow_docs()
                if rc != 0:
                    return rc
                return _cleanup_legacy_skill_dir()
            return 0
    except genlib.YamlError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"FATAL: resolved skill-dir 作成失敗: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
