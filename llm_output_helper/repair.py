"""JSON repair & completion — layer two of the structured output pipeline.

Two-step pipeline for fixing broken LLM JSON output:

1. **repair_json_fragment** — context-aware state machine that normalizes
   Chinese/fullwidth structural punctuation without touching string content.
2. **complete_json** — stack scanner that closes unclosed brackets, strings,
   and comments.

Combined entry point: :func:`parse_json` — repairs, completes, then parses
with json5 in one call.

Usage::

    from llm_output_helper import parse_json

    data = parse_json('{"name"："张三"，"items"：["a"，"b"')
    # → {'name': '张三', 'items': ['a', 'b']}
"""

from __future__ import annotations

import json
from typing import Any, Optional

try:
    import json5 as _json5  # type: ignore[import-untyped]
    _json5_loads = _json5.loads
except ImportError:  # pragma: no cover
    _json5_loads = json.loads  # type: ignore[assignment]


# ============================================================================
# Public API
# ============================================================================

def repair_json_fragment(text: str) -> str:
    """Fix structural Chinese/fullwidth punctuation in a JSON fragment.

    Context-aware: replaces structural colons, commas, brackets, and quotes
    while leaving string *content* untouched.  A Chinese colon inside a
    string value (e.g. ``"地址：北京"``) is preserved as-is.

    Handles:
    - Fullwidth/CJK brackets:  ``｛｝［］``
    - Chinese colons/commas in structural positions: ``：→:``, ``，→,``
    - Smart/curly quotes:  ``\"\"`` ``''`` → ``\"\"``
    - Fullwidth quotes: ``＂＇`` → ``\"'``
    - Unquoted keys (primitive mode fallback)
    """
    if not text:
        return text
    try:
        return _repair_fragment(text)
    except Exception:
        return text


def complete_json(text: str) -> str:
    """Close unclosed brackets, strings, and comments in a JSON fragment.

    Scans *text* with a stack, tracking ``{}``/``[]`` depth, string state,
    and ``//``/``/**/`` comment regions.  After scanning, appends the
    necessary closing characters so the result is structurally valid JSON.

    Useful when a model response is cut off by ``max_tokens``, or when a
    streaming chunk arrives mid-object.
    """
    if not text:
        return text
    return _complete_fragment(text)


def parse_json(text: str) -> Any:
    """Repair, complete, and json5-parse *text* in one call.

    Returns the parsed Python object (``dict``, ``list``, etc.).

    Raises ``ValueError`` if the text cannot be parsed even after repair.
    """
    if not text or not text.strip():
        raise ValueError("Cannot parse empty input as JSON")

    repaired = repair_json_fragment(text)
    completed = complete_json(repaired)

    # Try direct parse first.
    try:
        return _json5_loads(completed)
    except Exception:
        pass

    # If repair left us with bare key:value pairs (no outer braces),
    # try wrapping in an object.
    stripped = completed.strip()
    if not stripped.startswith(("{", "[")):
        try:
            return _json5_loads("{" + completed + "}")
        except Exception:
            pass

    raise ValueError(f"Cannot parse JSON even after repair: {completed!r}")


def parse_json_safe(text: str) -> Optional[Any]:
    """Like :func:`parse_json`, but returns ``None`` on failure."""
    try:
        return parse_json(text)
    except Exception:
        return None


# ============================================================================
# Structural translation map
# ============================================================================

# Fullwidth/CJK brackets, colons, commas → ASCII equivalents.
# Applied ONLY in structural positions (never inside string values).
_STRUCTURAL_TRANSLATIONS: dict[str, str] = {
    "：": ":",
    "，": ",",
    "｛": "{",
    "｝": "}",
    "［": "[",
    "］": "]",
}

# Quote variants that map to the same delimiter character.
_QUOTE_VARIANTS_DOUBLE = frozenset({'"', "“", "”", "＂"})  # " “ ” ＂
_QUOTE_VARIANTS_SINGLE = frozenset({"'", "‘", "’", "＇"})  # ' ' ' ＇


def _is_quote_variant(ch: str, delimiter: str) -> bool:
    """Return True if *ch* is any form of the given quote delimiter."""
    if delimiter == '"':
        return ch in _QUOTE_VARIANTS_DOUBLE
    return ch in _QUOTE_VARIANTS_SINGLE


# ============================================================================
# Context-aware fragment repair
# ============================================================================


def _repair_fragment(text: str) -> str:
    """State-machine repair of structural punctuation.

    Uses a context stack to track nesting (object/array/root) and the
    current state within each context (key_or_end, colon, value, etc.).
    This allows the repairer to distinguish structural colons from colons
    inside string values.
    """
    contexts: list[dict[str, str]] = [{"type": "root", "state": "value_or_end"}]
    out: list[str] = []
    in_string = False
    string_delim = '"'
    string_role = "value"  # "key" or "value"
    escape = False
    in_primitive = False
    primitive_role = "value"
    i = 0

    def _ctx() -> dict[str, str]:
        return contexts[-1]

    def _mark_value_done() -> None:
        ctx_ = _ctx()
        ctx_["state"] = "comma_or_end" if ctx_["type"] in ("object", "array") else "done"

    while i < len(text):
        ch = text[i]
        norm = _STRUCTURAL_TRANSLATIONS.get(ch, ch)

        # --- inside a string literal ---------------------------------
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                i += 1
                continue

            if ch == "\\":
                out.append(ch)
                escape = True
                i += 1
                continue

            # Detected a matching quote → does it actually close?
            if _is_quote_variant(ch, string_delim):
                if _can_close_string(text, i, string_role):
                    out.append(string_delim)  # emit normalized delimiter
                    in_string = False
                    # A "value" quote followed by colon is really a key.
                    nxt = _next_non_ws(text, i + 1)
                    if string_role == "key" or nxt in {":", "："}:
                        _ctx()["state"] = "colon"
                    else:
                        _mark_value_done()
                else:
                    out.append(ch)  # quote inside string content, keep original
                i += 1
                continue

            out.append(ch)
            i += 1
            continue

        # --- inside an unquoted primitive (key or value) ------------
        if in_primitive:
            if primitive_role == "key":
                if norm == ":":
                    out.append(":")
                    _ctx()["state"] = "value"
                    in_primitive = False
                    i += 1
                    continue
                out.append(ch)
                i += 1
                continue

            # primitive value
            if ch.isspace():
                out.append(ch)
                _mark_value_done()
                in_primitive = False
                i += 1
                continue
            if norm in {",", "}", "]"}:
                _mark_value_done()
                in_primitive = False
                continue  # re-process this char in the normal flow
            out.append(ch)
            i += 1
            continue

        # --- whitespace — pass through -------------------------------
        if ch.isspace():
            out.append(ch)
            i += 1
            continue

        # --- structural decisions -----------------------------------
        ctx_ = _ctx()
        state = ctx_["state"]

        # Open a double-quoted string
        if state in ("key_or_end", "value", "value_or_end") and _is_quote_variant(ch, '"'):
            in_string = True
            string_delim = '"'
            string_role = "key" if state == "key_or_end" else "value"
            out.append('"')
            i += 1
            continue

        # Open a single-quoted string
        if state in ("key_or_end", "value", "value_or_end") and _is_quote_variant(ch, "'"):
            in_string = True
            string_delim = "'"
            string_role = "key" if state == "key_or_end" else "value"
            out.append("'")
            i += 1
            continue

        # Open a nested object or array
        if norm in {"{", "["} and state in ("value", "value_or_end"):
            out.append(norm)
            if norm == "{":
                contexts.append({"type": "object", "state": "key_or_end"})
            else:
                contexts.append({"type": "array", "state": "value_or_end"})
            i += 1
            continue

        # Close an object
        if norm == "}" and ctx_["type"] == "object" and state in ("key_or_end", "comma_or_end"):
            out.append("}")
            contexts.pop()
            _mark_value_done()
            i += 1
            continue

        # Close an array
        if norm == "]" and ctx_["type"] == "array" and state in ("value_or_end", "comma_or_end"):
            out.append("]")
            contexts.pop()
            _mark_value_done()
            i += 1
            continue

        # Colon — also allow root context (implicit top-level object)
        if norm == ":" and ctx_["type"] in ("object", "root") and state == "colon":
            out.append(":")
            if ctx_["type"] == "root":
                ctx_["type"] = "object"  # upgrade: root → implicit object
            ctx_["state"] = "value"
            i += 1
            continue

        # Comma — also allow root-turned-object
        if norm == "," and state == "comma_or_end":
            out.append(",")
            if ctx_["type"] in ("object", "root"):
                if ctx_["type"] == "root":
                    ctx_["type"] = "object"
                ctx_["state"] = "key_or_end"
            elif ctx_["type"] == "array":
                ctx_["state"] = "value_or_end"
            else:
                ctx_["state"] = "done"
            i += 1
            continue

        # Unquoted key start
        if state == "key_or_end":
            in_primitive = True
            primitive_role = "key"
            out.append(ch)
            i += 1
            continue

        # Unquoted value start
        if state in ("value", "value_or_end"):
            in_primitive = True
            primitive_role = "value"
            out.append(ch)
            i += 1
            continue

        # Fallthrough — pass character as-is
        out.append(ch)
        i += 1

    return "".join(out)


def _can_close_string(text: str, index: int, role: str) -> bool:
    """Check if a quote at *index* can close the current string.

    A quote closes a string when the next non-whitespace character is
    structurally appropriate:

    - For a **key** string: next char should be ``:`` or ``：``
    - For a **value** string: next char should be ``,``, ``}``, ``]``,
      their Chinese equivalents, *or* a colon (because a "value" in a
      ``value_or_end`` context might actually be a key — the machine
      can't always distinguish until the colon appears).
    """
    nxt = _next_non_ws(text, index + 1)
    if nxt is None:
        return role == "value"  # end-of-input closes value strings
    if role == "key":
        return nxt in {":", "："}
    # value role — also accept colon (key-in-disguise)
    return nxt in {",", "，", "}", "]", "｝", "］", ":", "："}


def _next_non_ws(text: str, start: int) -> Optional[str]:
    """Return the first non-whitespace char from *start*, or ``None``."""
    for i in range(start, len(text)):
        if not text[i].isspace():
            return text[i]
    return None


# ============================================================================
# Stack-based completion
# ============================================================================


def _complete_fragment(text: str) -> str:
    """Scan *text* and append missing closing brackets, strings, comments."""
    stack: list[str] = []
    out = text
    i = 0
    in_string = False
    string_delim: Optional[str] = None
    escape = False
    comment: Optional[str] = None  # "//" or "/*"

    while i < len(out):
        ch = out[i]
        nxt = out[i + 1] if i + 1 < len(out) else ""

        if comment is None:
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == string_delim:
                    in_string = False
                    string_delim = None
            elif ch in '"\'':
                in_string = True
                string_delim = ch
            elif ch == "/" and nxt == "/":
                comment = "//"
                i += 1
            elif ch == "/" and nxt == "*":
                comment = "/*"
                i += 1
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    opener = stack[-1]
                    if (opener == "{" and ch == "}") or (opener == "[" and ch == "]"):
                        stack.pop()
        else:
            if comment == "//" and ch in "\n\r":
                comment = None
            elif comment == "/*" and ch == "*" and nxt == "/":
                comment = None
                i += 1

        i += 1

    # --- append missing closers ------------------------------------------
    if in_string and string_delim is not None:
        out += string_delim

    if comment == "//":
        out += "\n"
    elif comment == "/*":
        out += "*/"

    if stack:
        closer = {"{": "}", "[": "]"}
        out += "".join(closer[op] for op in reversed(stack))

    return out
