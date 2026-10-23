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

__version__ = "0.2.0"


def structured_output(
    text: str,
    schema: Optional[dict] = None,
    ensure_keys: Optional[list[str]] = None,
    max_retries: int = 2,
    on_retry: Optional[Callable[[str], str]] = None,
    *,
    output_model: Optional[type] = None,
    model_strict: Optional[bool] = None,
) -> Any:
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
        Maximum callback retries after JSON extraction, parsing, or
        ``ensure_keys`` validation fails. All stages share one budget.
        Each retry calls ``on_retry(feedback)`` to get fresh text,
        then runs the full pipeline again.
    on_retry:
        Callback that takes the error feedback string and returns new
        model response text.  Typically wraps your LLM call::

            on_retry=lambda fb: llm.chat(f"修正以下问题: {fb}")

        If not provided and retries are needed, a ``ValidationError``
        is raised after the first attempt.
    output_model:
        Optional Pydantic v2 BaseModel class. Validates the entire parsed value
        before ensure_keys checks, then returns model_dump(mode="python").
        Requires the optional [pydantic] extra. Without an explicit schema,
        model field names and string aliases guide JSON candidate selection.
        ensure_keys addresses normalized field names, after model validation.
    model_strict:
        Pydantic strict override: None honors model configuration (including
        normal Pydantic coercion), True rejects coercion, False permits it.
        This option requires output_model.

    Returns
    -------
    Parsed Python object or array. ``schema`` alone selects a candidate;
    only paths listed in ``ensure_keys`` are validated unless output_model is
    provided. Model output may contain Python-native types such as datetime.

    Raises
    ------
    ValidationError
        When ``ensure_keys`` validation fails after all retries.
    ValueError
        When the text contains no parseable JSON even after repair.
    """
    if ensure_keys is None:
        ensure_keys = []

    model_validator = None
    selection_schema = schema
    if output_model is not None:
        from llm_output_helper.model_validation import prepare_output_model

        model_validator, model_schema = prepare_output_model(output_model, model_strict)
        if schema is None:
            selection_schema = model_schema
    elif model_strict is not None:
        raise TypeError("model_strict requires output_model.")

    # --- attempt loop -------------------------------------------------------
    remaining = max(0, max_retries)
    last_errors: list[str] = []

    while True:
        parse_error = None
        data = None
        try:
            # Layer ①: locate
            if selection_schema and isinstance(selection_schema, dict):
                raw_json = locate_output_json(text, selection_schema)
            else:
                candidates = locate_all_json(text)
                raw_json = candidates[-1] if candidates else None
            if raw_json is None:
                raise ValueError("No JSON block found in the response text.")

            # Layer ②: repair + parse
            data = parse_json(raw_json)
        except ValueError as exc:
            parse_error = exc
            current_errors = [str(exc)]
        else:
            # Layer ③: validate
            try:
                if model_validator is not None:
                    data = model_validator(data)
            except ValidationError as exc:
                current_errors = exc.errors
            else:
                current_errors = validate(data, ensure_keys, schema or {})
        if not current_errors:
            return data

        last_errors = current_errors
        if remaining <= 0 or on_retry is None:
            if parse_error is not None:
                raise parse_error
            raise ValidationError(last_errors, data)

        # Generate feedback and retry
        remaining -= 1
        feedback = make_retry_feedback(current_errors)
        text = on_retry(feedback)


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
