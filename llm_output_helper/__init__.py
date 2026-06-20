"""LLM Output Helper — framework-free structured output extraction.

Three-layer fallback for extracting JSON from LLM responses:

1. **locator** — state machine JSON block detection + schema-guided selection
2. **repair** — Chinese punctuation fix, bracket completion, json5 parsing
3. **validator** — field presence/type check with auto-retry feedback loop

Usage::

    from llm_output_helper import locate_all_json, locate_output_json

    candidates = locate_all_json(model_response)
    best_json = locate_output_json(model_response, schema={"name": str, "age": int})
"""

from llm_output_helper.locator import locate_all_json, locate_output_json

__version__ = "0.1.0"

__all__ = [
    "locate_all_json",
    "locate_output_json",
]
