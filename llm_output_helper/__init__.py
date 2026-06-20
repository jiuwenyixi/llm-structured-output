"""LLM Output Helper — framework-free structured output extraction.

Three-layer fallback for extracting JSON from LLM responses:

1. **locator** — state machine JSON block detection + schema-guided selection
2. **repair**  — Chinese punctuation fix, bracket completion, json5 parsing
3. **validator** — field presence/type check with auto-retry feedback loop

Quick Start::

    from llm_output_helper import locate_output_json, parse_json

    # Step 1: find the right JSON block in model output
    raw_json = locate_output_json(model_response, schema={"name": str})

    # Step 2: repair broken punctuation, complete missing brackets, parse
    if raw_json:
        data = parse_json(raw_json)
        # → {'name': '张三', 'items': ['值1', '值2']}
"""

from llm_output_helper.locator import locate_all_json, locate_output_json
from llm_output_helper.repair import (
    complete_json,
    parse_json,
    parse_json_safe,
    repair_json_fragment,
)

__version__ = "0.1.0"

__all__ = [
    # locator
    "locate_all_json",
    "locate_output_json",
    # repair
    "repair_json_fragment",
    "complete_json",
    "parse_json",
    "parse_json_safe",
]
