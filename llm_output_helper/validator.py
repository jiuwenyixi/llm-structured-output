"""Field validation & retry — layer three of the structured output pipeline.

Validates parsed JSON against an output schema and ``ensure_keys`` list,
generating human-readable error feedback for the LLM to fix on retry.

The ``structured_output()`` entry point in ``__init__.py`` orchestrates
all three layers through this module.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional


# ============================================================================
# Public API
# ============================================================================

class ValidationError(Exception):
    """Raised when ``ensure_keys`` validation fails after all retries."""

    def __init__(self, errors: list[str], data: Any = None):
        self.errors = errors
        self.data = data
        super().__init__("\n".join(errors))


def validate(
    data: Any,
    ensure_keys: list[str],
    schema: dict,
) -> list[str]:
    """Check *data* against *ensure_keys* and *schema*.

    Returns a list of human-readable error messages (empty = valid).

    Parameters
    ----------
    data:
        Parsed JSON object (dict or list).
    ensure_keys:
        Key patterns to enforce.  Supports ``[*]`` wildcard for arrays
        and dot-notation for nesting:
        ``["summary", "action_items[*].task", "action_items[*].owner"]``
    schema:
        Output schema dict whose values are ``(type, description)`` tuples
        or nested dicts/lists.
    """
    if not ensure_keys:
        return []

    errors: list[str] = []
    for pattern in ensure_keys:
        _check_pattern(data, pattern, schema, errors)
    return errors


def make_retry_feedback(errors: list[str]) -> str:
    """Build an LLM-friendly retry prompt from validation errors.

    The feedback is designed to be injected into the next model call so
    the LLM knows exactly what was missing or wrong.
    """
    numbered = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(errors))
    return (
        f"上次输出的 JSON 解析失败，存在以下问题：\n"
        f"{numbered}\n"
        f"请根据上述问题修正后重新输出完整的 JSON，不要遗漏任何字段。"
    )


# ============================================================================
# Pattern matching
# ============================================================================

_WILDCARD_RE = re.compile(r"\[\*\]")


def _check_pattern(
    data: Any,
    pattern: str,
    schema: dict,
    errors: list[str],
    path: str = "",
) -> None:
    """Walk *pattern* against *data*, appending errors when keys are missing
    or have wrong types."""
    # Split on "[*]." boundaries — handle the wildcard array traversal.
    segments = _WILDCARD_RE.split(pattern)

    if len(segments) == 1:
        # No wildcard — a simple dotted path.
        _check_dotted(data, segments[0], schema, errors, path)
        return

    # There's a [*] — walk through the prefix, then fan out over the array.
    prefix = segments[0].rstrip(".")
    suffix = ".".join(s for s in segments[1:] if s).lstrip(".")

    # Resolve the prefix to the array.
    if prefix:
        arr, _ = _resolve_path(data, prefix.split("."))
    else:
        arr = data

    if not isinstance(arr, list):
        errors.append(
            f"字段 '{path or pattern}' 应为数组，实际类型为 {type(arr).__name__}"
        )
        return

    if len(arr) == 0:
        errors.append(
            f"字段 '{path or pattern}' 是空数组，需要至少包含一个元素"
        )
        return

    for idx, item in enumerate(arr):
        item_path = f"{path}[{idx}]" if path else f"[{idx}]"
        if suffix:
            _check_dotted(item, suffix, schema, errors, item_path)
        elif item is None:
            errors.append(f"字段 '{item_path}' 不能为空")


def _check_dotted(
    data: Any,
    dotted: str,
    schema: dict,
    errors: list[str],
    path: str = "",
) -> None:
    """Check a dotted path (without ``[*]``) against *data*."""
    raw_parts = [p for p in dotted.split(".") if p]
    if not raw_parts:
        return

    # Walk to the parent of the last key so we can report type info.
    *parent_parts, last_key = raw_parts
    cursor = data
    walked = ""

    for part in parent_parts:
        if not isinstance(cursor, dict) or part not in cursor:
            errors.append(
                f"缺少字段: {_fmt_path(path, dotted)}"
            )
            return
        cursor = cursor[part]
        walked += f".{part}" if walked else part

    # Check the final key.
    if not isinstance(cursor, dict):
        errors.append(
            f"字段 '{_fmt_path(path, dotted)}' 无法访问——"
            f"'{walked or path}' 不是对象"
        )
        return

    if last_key not in cursor:
        expected_type = _get_expected_type(schema, raw_parts)
        type_hint = f" (类型应为 {expected_type})" if expected_type else ""
        errors.append(
            f"缺少字段: {_fmt_path(path, dotted)}{type_hint}"
        )
        return

    # Type check.
    expected_type = _get_expected_type(schema, raw_parts)
    if expected_type:
        value = cursor[last_key]
        if not _type_matches(value, expected_type):
            errors.append(
                f"字段 '{_fmt_path(path, dotted)}' 类型错误: "
                f"期望 {expected_type}, 实际 {type(value).__name__}"
            )


def _resolve_path(data: Any, parts: list[str]) -> tuple[Any, str]:
    """Walk *parts* through *data*, returning (value, walked_path)."""
    cursor = data
    walked = ""
    for part in parts:
        if isinstance(cursor, dict) and part in cursor:
            walked += f".{part}" if walked else part
            cursor = cursor[part]
        else:
            return None, walked
    return cursor, walked


def _fmt_path(base: str, dotted: str) -> str:
    """Format a full path string."""
    if base and dotted:
        return f"{base}.{dotted}"
    return base or dotted


# ============================================================================
# Schema helpers
# ============================================================================


def _get_expected_type(schema: dict, parts: list[str]) -> Optional[str]:
    """Walk *schema* along *parts* and return the type name, if any.

    Schema values can be ``(type, description)`` tuples, nested dicts,
    or lists containing dict templates (for arrays of objects).
    """
    cursor: Any = schema
    for part in parts:
        if isinstance(cursor, dict):
            cursor = cursor.get(part)
            if cursor is None:
                return None
        elif isinstance(cursor, list):
            # Schema says "list of X" — look inside first template element.
            if cursor:
                cursor = cursor[0].get(part)
            else:
                return None
        else:
            return None

    # cursor is now the schema leaf: either (type, desc) tuple, a type, or nested.
    if isinstance(cursor, tuple):
        return _type_name(cursor[0])
    if isinstance(cursor, type):
        return _type_name(cursor)
    return None


def _type_name(t: type) -> str:
    """Human-readable type name."""
    mapping = {str: "str", int: "int", float: "float", bool: "bool", list: "list", dict: "dict"}
    return mapping.get(t, t.__name__)


def _type_matches(value: Any, expected: str) -> bool:
    """Check if *value*'s Python type matches the expected type name."""
    type_map = {
        "str": str, "string": str,
        "int": int, "integer": int,
        "float": float, "number": float,
        "bool": bool, "boolean": bool,
        "list": list,
        "dict": dict,
    }
    py_type = type_map.get(expected)
    if py_type is None:
        return True  # unknown type — skip check
    return isinstance(value, py_type)
