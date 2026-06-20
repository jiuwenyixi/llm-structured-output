"""JSON block locator — layer one of the structured output pipeline.

Scans raw LLM response text with a character-by-character state machine to find
every JSON object/array block, then optionally picks the best one by scoring
against an output schema.

Algorithm overview::

    Pre-process: convert ``\"\"\"...\"\"\"`` triple-quoted blocks to JSON-safe form.

    State machine (two phases):
      SEEK — looking for the next ``{`` or ``[`` to start a new block.
      CAPTURE — inside a block, tracking bracket depth, string boundaries,
                and escape sequences.  When depth returns to zero the block
                is complete.

    Scoring (when ``locate_output_json`` is called with a schema):
      Parse each candidate with json5, count how many schema keys are
      present.  Return the candidate with the highest score.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

# json5 is the only external dependency — used for lenient JSON parsing
# (trailing commas, comments, single quotes).  Falls back to stdlib json.
try:
    import json5 as _json5  # type: ignore[import-untyped]
    _json5_loads = _json5.loads
except ImportError:  # pragma: no cover — json5 is required by pyproject.toml
    _json5_loads = json.loads  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def locate_all_json(text: str) -> list[str]:
    """Extract every top-level JSON object or array block from *text*.

    Returns blocks in order of appearance.  Returns an empty list if no
    ``{...}`` or ``[...]`` blocks are found.

    Handles common LLM output patterns:
    - JSON embedded in natural-language text
    - Multiple JSON blocks in one response
    - Triple-quoted ``\"\"\"...\"\"\"`` Python-style string blocks
    - Nested objects/arrays
    """
    if not text:
        return []

    text = _preprocess(text)
    return list(_scan_json_blocks(text))


def locate_output_json(
    text: str,
    schema: Optional[dict] = None,
) -> Optional[str]:
    """Like :func:`locate_all_json`, but returns only the *best* candidate.

    When exactly one JSON block is found, it is returned directly.  When
    multiple blocks exist and *schema* is provided, each candidate is
    parsed and scored — the block with the most schema-key matches wins.

    Returns ``None`` when no JSON blocks are found.

    Parameters
    ----------
    text:
        Raw model response text.
    schema:
        A dict whose keys describe the expected output fields.  Values are
        type hints (``str``, ``int``, ``list``, …) or nested dicts.
        Example: ``{"question_type": str, "answer": str}``
    """
    candidates = list(_scan_json_blocks(_preprocess(text)))
    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Multiple candidates — score them against the schema.
    if schema is not None:
        best: Optional[str] = None
        best_score = -1
        schema_keys = _extract_leaf_keys(schema)
        for raw in candidates:
            score = _score_schema_match(raw, schema_keys)
            if score > best_score:
                best_score = score
                best = raw
        if best is not None and best_score >= 0:
            return best

    # No schema or no match — fall back to the last block (often the
    # "final answer" pattern common in chain-of-thought responses).
    return candidates[-1]


# ---------------------------------------------------------------------------
# Pre-processing
# ---------------------------------------------------------------------------

_TRIPLE_QUOTE_RE = re.compile(r'"""(.*?)"""', re.DOTALL)


def _preprocess(text: str) -> str:
    """Normalize *text* before the state machine scans it.

    Two transformations:
    1. Triple-quoted ``\"\"\"...\"\"\"`` blocks → json5-escaped strings.
       LLMs sometimes wrap content in Python-style triple quotes, which
       confuses the quote-tracking state machine.
    2. ``[OUTPUT]`` → ``$<<OUTPUT>>`` sentinel to protect it from being
       mistaken for a JSON array bracket.
    """
    text = _TRIPLE_QUOTE_RE.sub(
        lambda m: _json5_dumps(m.group(1)),
        text,
    )
    # Protect [OUTPUT] tags from being treated as array openings.
    text = text.replace("[OUTPUT]", "$<<OUTPUT>>")
    return text


def _json5_dumps(s: str) -> str:
    """json5.dumps a string, with fallback to stdlib json."""
    try:
        return _json5.dumps(s)
    except Exception:
        return json.dumps(s)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# Character classification helpers — tiny lookup sets for performance and
# readability (avoids sprinkling ``in '{}'`` all over the state machine).
# ASCII + fullwidth brackets (LLMs with Chinese prompts often emit these).
_BRACKET_OPEN  = frozenset("{[｛［")
_BRACKET_CLOSE = frozenset("}]｝］")


def _scan_json_blocks(text: str) -> "iter[str]":
    """Yield every top-level JSON block found in *text*.

    State machine with two high-level stages:

    * **SEEK** (``stage=1``) — looking for an opening bracket.
    * **CAPTURE** (``stage=2``) — inside a JSON block, tracking depth,
      string boundaries, and escape sequences.

    Blocks that are still open at end-of-text (e.g. truncated by
    ``max_tokens``) are also yielded so the repair layer can close them.
    """
    stage: int = 1       # 1=SEEK, 2=CAPTURE
    block: list[str] = []  # current block chars
    depth: int = 0
    in_string: bool = False
    skip_next: bool = False

    for i, ch in enumerate(text):
        # --- shared escape guard --------------------------------------
        if skip_next:
            skip_next = False
            continue

        # --- SEEK phase -----------------------------------------------
        if stage == 1:
            if ch == "\\":
                skip_next = True
                continue
            if ch in _BRACKET_OPEN:
                block = [ch]
                depth = 1
                in_string = False
                stage = 2
            continue  # keep seeking

        # --- CAPTURE phase --------------------------------------------
        # stage == 2 (inside a JSON block)

        if not in_string:
            # Backslash outside a string: could be an escaped quote
            # meant to be a literal inside a key/value.
            if ch == "\\":
                skip_next = True
                peek = _safe_peek(text, i)
                if peek == '"':
                    block.append('"')
                # for non-quote escapes we skip the backslash entirely,
                # keeping just the next char when it arrives next iteration
                continue

            if ch == '"':
                in_string = True

            elif ch in _BRACKET_OPEN:
                depth += 1
            elif ch in _BRACKET_CLOSE:
                depth -= 1

            block.append(ch)

        else:  # in_string == True
            if ch == "\\":
                # Preserve escape sequences inside strings.
                peek = _safe_peek(text, i)
                block.append(ch + peek)  # e.g. "\n", "\""
                skip_next = True
                continue

            if ch == "\n":
                block.append("\\n")
                continue
            if ch == "\t":
                block.append("\\t")
                continue

            if ch == '"':
                in_string = False

            block.append(ch)

        # --- block boundary check -------------------------------------
        if depth == 0 and stage == 2:
            yield "".join(block).replace("$<<OUTPUT>>", "[OUTPUT]")
            stage = 1
            block = []

    # End of text: yield truncated block so repair layer can close it.
    if stage == 2 and block:
        yield "".join(block).replace("$<<OUTPUT>>", "[OUTPUT]")


def _safe_peek(text: str, index: int) -> str:
    """Return ``text[index+1]``, or ``""`` if out of bounds."""
    try:
        return text[index + 1]
    except IndexError:
        return ""


# ---------------------------------------------------------------------------
# Schema scoring
# ---------------------------------------------------------------------------

def _extract_leaf_keys(schema: dict, prefix: str = "") -> set[str]:
    """Flatten a possibly-nested schema dict into a set of dot-path keys.

    >>> _extract_leaf_keys({"name": str, "addr": {"city": str, "zip": int}})
    {"name", "addr.city", "addr.zip"}
    """
    keys: set[str] = set()
    for k, v in schema.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _extract_leaf_keys(v, full)
        else:
            keys.add(full)
    return keys


def _score_schema_match(raw_json: str, schema_keys: set[str]) -> int:
    """Return the number of *schema_keys* present in *raw_json*.

    Returns -1 when *raw_json* cannot be parsed or is the wrong shape
    (e.g. a list when the schema describes a dict).

    Attempts repair before parsing so Chinese-punctuation candidates
    are scored correctly.
    """
    # Bail early if there are no keys to match — any valid JSON is fine.
    if not schema_keys:
        return 0

    # Try raw parse first, then repair + parse.
    parsed = None
    for candidate in _candidates_to_try(raw_json):
        try:
            parsed = _json5_loads(candidate)
            break
        except Exception:
            continue

    if parsed is None:
        return -1

    # Schema keys imply an object — reject arrays.
    if not isinstance(parsed, dict):
        return -1

    score = 0
    for dotted_key in schema_keys:
        if _has_dotted_key(parsed, dotted_key):
            score += 1
    return score


def _candidates_to_try(raw: str) -> "iter[str]":
    """Yield candidate forms of *raw* to try parsing, from cheapest to most
    expensive: raw → repaired → repaired+completed."""
    yield raw
    # Lazy import to avoid circular dependency at module level.
    from llm_output_helper.repair import complete_json, repair_json_fragment  # noqa: PLC0415

    repaired = repair_json_fragment(raw)
    if repaired != raw:
        yield repaired
        yield complete_json(repaired)


def _has_dotted_key(data: dict, dotted_key: str) -> bool:
    """Check whether nested dict *data* contains the dot-separated path.

    >>> _has_dotted_key({"user": {"name": "Alice"}}, "user.name")
    True
    >>> _has_dotted_key({"user": {"name": "Alice"}}, "user.age")
    False
    """
    parts = dotted_key.split(".")
    cursor: Any = data
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            return False
        cursor = cursor[part]
    return True
