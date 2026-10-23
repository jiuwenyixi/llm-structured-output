"""Optional Pydantic v2 validation without a mandatory framework dependency."""

from __future__ import annotations

from typing import Any, Callable, Optional

from llm_output_helper.validator import ValidationError


def prepare_output_model(
    output_model: type,
    strict: Optional[bool],
) -> tuple[Callable[[Any], Any], Optional[dict]]:
    """Validate configuration once, then build a validator and selection hints.

    Only Pydantic validation failures become retryable library ValidationErrors.
    Configuration, custom validator programming errors, and dump failures propagate.
    """
    try:
        from pydantic import BaseModel, ValidationError as ModelValidationError
    except ImportError as exc:
        raise ImportError(
            "output_model requires Pydantic v2. Install llm-output-helper[pydantic]."
        ) from exc

    if not hasattr(BaseModel, "model_validate"):
        raise ImportError("output_model requires Pydantic v2; Pydantic v1 is not supported.")
    if not isinstance(output_model, type) or not issubclass(output_model, BaseModel):
        raise TypeError("output_model must be a Pydantic v2 BaseModel class, not an instance.")
    if strict is not None and not isinstance(strict, bool):
        raise TypeError("model_strict must be True, False, or None.")

    selection_schema = None
    if not getattr(output_model, "__pydantic_root_model__", False):
        # Hints only: Pydantic remains the final authority on aliases, defaults,
        # nested values, and constraints. No JSON Schema generator is required.
        selection_schema = {name: object for name in output_model.model_fields}
        for field in output_model.model_fields.values():
            for alias in (field.alias, field.validation_alias):
                if isinstance(alias, str):
                    selection_schema[alias] = object

    def validate_model(data: Any) -> Any:
        try:
            instance = output_model.model_validate(data, strict=strict)
        except ModelValidationError as exc:
            errors = []
            # Pydantic 2.0 lacks include_input. Select only loc/msg below so raw
            # input entries never enter feedback on either old or new versions.
            details = exc.errors(include_url=False, include_context=False)
            for detail in details[:8]:
                path = _format_location(detail.get("loc", ()))
                errors.append(f"{path}: {detail.get('msg', 'Invalid value')}"[:300])
            raise ValidationError(errors or ["<root>: Model validation failed"], data) from exc
        # Return ordinary containers with validated/defaulted values. Python-mode
        # serialization intentionally preserves types such as datetime and Enum.
        return instance.model_dump(mode="python")

    return validate_model, selection_schema


def _format_location(location: tuple) -> str:
    path = ""
    for part in location:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += ("." if path else "") + str(part)
    return path or "<root>"
