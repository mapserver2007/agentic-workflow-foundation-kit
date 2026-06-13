#!/usr/bin/env python3
"""root manifest の per-project 値を解決して engine を実行する foundation 専用ラッパー。"""
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

ROOT_OVERLAY_KEYS = ("project", "tech_stack", "session", "quality_gate_contract")
FRAMEWORK_OVERLAY_KEYS = ("accd_axes",)


def _yaml_quote(value) -> str:
    s = "" if value is None else str(value)
    if "\n" in s:
        raise genlib.YamlError("複数行スカラは resolved manifest でサポートしない")
    if '"' in s:
        return "'" + s.replace("'", "''") + "'"
    return '"' + s + '"'


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
                lines.append(f"{pad}{key}: {_yaml_scalar(item)}")
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
        normalized["adopted"] = "[要確認] 採用する軽量実装"
    if "not_adopted" not in normalized:
        normalized["not_adopted"] = "[要確認] 意図的に非採用とする重い機構"
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


def resolved_manifest(seed_manifest_path: str, root_manifest_path: str) -> dict:
    manifest = genlib.load_manifest(seed_manifest_path)
    if not os.path.isfile(root_manifest_path):
        return manifest

    overlay = genlib.load_manifest(root_manifest_path)
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
    return merged


def prepare_skill_dir(resolved_dir: str, manifest: dict) -> str:
    with open(os.path.join(resolved_dir, "manifest.yaml"), "w", encoding="utf-8") as f:
        f.write(dump_manifest(manifest))
    shutil.copytree(
        os.path.join(SKILL_DIR, "templates"),
        os.path.join(resolved_dir, "templates"),
    )
    return resolved_dir


def run_engine(command: str, resolved_dir: str) -> int:
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
    return subprocess.call(args, cwd=ROOT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="foundation の resolved manifest で engine を実行する")
    parser.add_argument("command", choices=("generate", "audit", "check"))
    parser.add_argument("--seed-manifest", default=os.path.join(SKILL_DIR, "manifest.yaml"))
    parser.add_argument("--root-manifest", default=os.path.join(ROOT, "manifest.yaml"))
    args = parser.parse_args(argv)

    try:
        manifest = resolved_manifest(args.seed_manifest, args.root_manifest)
        with tempfile.TemporaryDirectory(
            prefix=".resolved-agentic-workflow-foundation-",
            dir=os.path.join(ROOT, ".cursor", "skills"),
        ) as tmp_skill_dir:
            resolved_dir = prepare_skill_dir(tmp_skill_dir, manifest)
            return run_engine(args.command, resolved_dir)
    except genlib.YamlError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"FATAL: resolved skill-dir 作成失敗: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
