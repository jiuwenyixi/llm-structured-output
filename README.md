# LLM Output Helper

Framework-free structured JSON output extraction for LLM responses.  
Zero dependencies on LangChain, Agently, or any other agent framework.  
Only requires `json5` for lenient JSON parsing.

## Why?

LLMs are notoriously bad at producing clean JSON. They add markdown backticks, trailing commas, Chinese punctuation, half-finished blocks, and chatty preambles. `response_format: json_object` helps, but not every model supports it — and even when it does, the output still needs cleaning.

This tool uses a **three-layer fallback** strategy (inspired by [Agently](https://github.com/AgentEra/Agently)'s proven approach):

| Layer | Module | Job |
|-------|--------|-----|
| ① | `locator.py` | State-machine scan to find JSON blocks in raw text, schema-guided best-candidate selection |
| ② | `repair.py` | Chinese→English punctuation, bracket completion, comment stripping, json5 parsing |
| ③ | `validator.py` | Field presence & type check against schema, auto-retry with error feedback |

## Status

- [x] **Layer ① — `locator.py`** — complete, 48 tests passing
- [ ] Layer ② — `repair.py` — coming next
- [ ] Layer ③ — `validator.py` — planned

## Install

```bash
pip install llm-output-helper
```

Or from source:

```bash
git clone https://github.com/your-username/llm-output-helper.git
cd llm-output-helper
pip install -e ".[dev]"
```

## Quick Start

```python
from llm_output_helper import locate_all_json, locate_output_json

response = '''
Let me think about this...
The answer should be:

```json
{"question_type": "math", "answer": 42, "confidence": 0.95}
```
'''

# Find all JSON blocks
blocks = locate_all_json(response)
# → ['{"question_type": "math", "answer": 42, "confidence": 0.95}']

# Find the best match against a schema
best = locate_output_json(
    response,
    schema={"question_type": str, "answer": int}
)
# → '{"question_type": "math", "answer": 42, "confidence": 0.95}'
```

## How It Works

### Layer ①: JSON Locator

A character-by-character state machine that:

1. **Pre-processes** — converts Python-style `"""..."""` blocks and protects `[OUTPUT]` tags
2. **Scans** in two alternating phases: *SEEK* (looking for `{` or `[`) and *CAPTURE* (tracking bracket depth, string boundaries, escape sequences)
3. **Scores** — when multiple candidates are found and a schema is provided, each is parsed with json5 and scored by key overlap

## Development

```bash
pip install -e ".[dev]"
pytest -v
```

## License

MIT
