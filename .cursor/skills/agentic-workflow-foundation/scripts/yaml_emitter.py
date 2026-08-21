"""genlib の最小 YAML ローダ向け block style emitter。"""
from __future__ import annotations

import json
import re


def _dump_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _dump_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return key
    return _dump_scalar(key)


def _block_indicator(value: str) -> str:
    if not value.endswith("\n"):
        return "|-"
    return "|+" if value.endswith("\n\n") else "|"


def _append_block_lines(
    lines: list[str],
    header: str,
    body_pad: str,
    value: str,
) -> None:
    lines.append(f"{header}{_block_indicator(value)}")
    body = value[:-1] if value.endswith("\n") else value
    lines.extend(f"{body_pad}{part}" for part in body.split("\n"))


def _append_scalar_lines(
    lines: list[str],
    pad: str,
    key_text: str,
    value: object,
) -> None:
    if isinstance(value, str) and "\n" in value:
        _append_block_lines(lines, f"{pad}{key_text}: ", f"{pad}  ", value)
    else:
        lines.append(f"{pad}{key_text}: {_dump_scalar(value)}")


def dump_yaml(value: object, indent: int = 0) -> list[str]:
    """値を block style YAML の行配列へ決定論的に変換する。"""
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{pad}{{}}"]
        lines: list[str] = []
        for key, child in value.items():
            key_text = _dump_key(str(key))
            if isinstance(child, list) and not child:
                lines.append(f"{pad}{key_text}: []")
            elif isinstance(child, dict) and not child:
                lines.append(f"{pad}{key_text}: {{}}")
            elif isinstance(child, (dict, list)):
                lines.append(f"{pad}{key_text}:")
                lines.extend(dump_yaml(child, indent + 2))
            else:
                _append_scalar_lines(lines, pad, key_text, child)
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}[]"]
        lines = []
        for child in value:
            if isinstance(child, dict):
                keys = list(child)
                if not keys:
                    lines.append(f"{pad}- {{}}")
                    continue
                first, *rest = keys
                first_value = child[first]
                first_key = _dump_key(str(first))
                if isinstance(first_value, list) and not first_value:
                    lines.append(f"{pad}- {first_key}: []")
                elif isinstance(first_value, dict) and not first_value:
                    lines.append(f"{pad}- {first_key}: {{}}")
                elif isinstance(first_value, (dict, list)):
                    lines.append(f"{pad}- {first_key}:")
                    lines.extend(dump_yaml(first_value, indent + 4))
                elif isinstance(first_value, str) and "\n" in first_value:
                    _append_block_lines(
                        lines,
                        f"{pad}- {first_key}: ",
                        f"{pad}    ",
                        first_value,
                    )
                else:
                    lines.append(f"{pad}- {first_key}: {_dump_scalar(first_value)}")
                for key in rest:
                    child_value = child[key]
                    key_text = _dump_key(str(key))
                    if isinstance(child_value, list) and not child_value:
                        lines.append(f"{pad}  {key_text}: []")
                    elif isinstance(child_value, dict) and not child_value:
                        lines.append(f"{pad}  {key_text}: {{}}")
                    elif isinstance(child_value, (dict, list)):
                        lines.append(f"{pad}  {key_text}:")
                        lines.extend(dump_yaml(child_value, indent + 4))
                    else:
                        _append_scalar_lines(lines, pad + "  ", key_text, child_value)
            elif isinstance(child, str) and "\n" in child:
                _append_block_lines(lines, f"{pad}- ", f"{pad}  ", child)
            else:
                lines.append(f"{pad}- {_dump_scalar(child)}")
        return lines
    return [f"{pad}{_dump_scalar(value)}"]


def dump_yaml_text(value: object) -> str:
    """末尾改行付きの block style YAML を返す。"""
    return "\n".join(dump_yaml(value)) + "\n"
