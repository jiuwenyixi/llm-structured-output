"""LLM Output Helper — framework-free structured output extraction.

One function, three layers, zero frameworks::

    from llm_output_helper import structured_output

    data = structured_output(
        text=model_response,
        schema={
            "summary": (str, "会议核心结论"),
            "action_items": [{
                "task": (str, "待办事项"),
                "owner": (str, "负责人"),
            }],
        },
        ensure_keys=["summary", "action_items[*].task", "action_items[*].owner"],
        max_retries=2,
        on_retry=lambda feedback: call_your_llm(feedback),
    )

Under the hood:

1. **locator** — state machine finds JSON blocks, schema scoring picks best
2. **repair** — Chinese punctuation fix, bracket completion, json5 parse
3. **validator** — field presence + type check, auto-generates retry feedback
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from llm_output_helper.locator import locate_all_json, locate_output_json
from llm_output_helper.repair import complete_json, parse_json, repair_json_fragment
from llm_output_helper.validator import ValidationError, make_retry_feedback, validate

__version__ = "0.1.0"


def structured_output(
    text: str,
    schema: Optional[dict] = None,
    ensure_keys: Optional[list[str]] = None,
    max_retries: int = 2,
    on_retry: Optional[Callable[[str], str]] = None,
) -> dict:
    """Extract structured JSON from LLM response text with three-layer fallback.

    Parameters
    ----------
    text:
        Raw model response text (may contain markdown, Chinese punctuation,
        chatty preambles, truncated JSON, etc.).
    schema:
        Output schema as a dict whose values are ``(type, description)`` tuples
        or nested dicts/lists.  Example::

            {
                "summary": (str, "会议核心结论，100字以内"),
                "action_items": [{
                    "task": (str, "待办事项描述"),
                    "owner": (str, "负责人姓名"),
                }],
            }

        Used for JSON block selection and type checking.
    ensure_keys:
        Key patterns that MUST be present.  Supports ``[*]`` wildcard for
        arrays and dot-notation for nesting::

            ["summary", "action_items[*].task", "action_items[*].owner"]

        If validation fails and *max_retries* > 0, error feedback is
        generated and passed to *on_retry*.
    max_retries:
        Maximum retry attempts when ``ensure_keys`` validation fails.
        Each retry calls ``on_retry(feedback)`` to get fresh text,
        then runs the full pipeline again.
    on_retry:
        Callback that takes the error feedback string and returns new
        model response text.  Typically wraps your LLM call::

            on_retry=lambda fb: llm.chat(f"修正以下问题: {fb}")

        If not provided and retries are needed, a ``ValidationError``
        is raised after the first attempt.

    Returns
    -------
    Parsed Python dict.

    Raises
    ------
    ValidationError
        When ``ensure_keys`` validation fails after all retries.
    ValueError
        When the text contains no parseable JSON even after repair.
    """
    if ensure_keys is None:
        ensure_keys = []

    # --- attempt loop -------------------------------------------------------
    remaining = max(0, max_retries)
    last_errors: list[str] = []

    while True:
        # Layer ①: locate
        if schema and isinstance(schema, dict):
            raw_json = locate_output_json(text, schema)
        else:
            candidates = locate_all_json(text)
            raw_json = candidates[-1] if candidates else None

        if raw_json is None:
            raise ValueError("No JSON block found in the response text.")

        # Layer ②: repair + parse
        try:
            data = parse_json(raw_json)
        except ValueError as e:
            raise ValueError(f"JSON parse failed after repair: {e}") from e

        # Layer ③: validate
        current_errors = validate(data, ensure_keys, schema or {})
        if not current_errors:
            return data

        last_errors = current_errors
        remaining -= 1
        if remaining < 0:
            break

        if on_retry is None:
            raise ValidationError(
                current_errors,
                data,
            )

        # Generate feedback and retry
        feedback = make_retry_feedback(current_errors)
        text = on_retry(feedback)

    raise ValidationError(last_errors, data)


__all__ = [
    "structured_output",
    "ValidationError",
    "make_retry_feedback",
    # Lower-level API (for advanced use)
    "locate_all_json",
    "locate_output_json",
    "repair_json_fragment",
    "complete_json",
    "parse_json",
    "validate",
]
