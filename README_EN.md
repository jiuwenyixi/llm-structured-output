# LLM Output Helper

[![中文](https://img.shields.io/badge/中文-README.md-red)](README.md)

Framework-free structured JSON output extraction for LLM responses.
Zero dependencies on LangChain or any other agent framework.
Only requires `json5` for lenient JSON parsing.

## Why?

LLMs are notoriously bad at producing clean JSON. They add markdown backticks, trailing commas, Chinese punctuation, half-finished blocks, and chatty preambles. `response_format: json_object` helps, but not every model supports it — and even when it does, the output still needs cleaning.

This tool uses a **three-layer fallback** strategy:

| Layer | Module | Job |
|-------|--------|-----|
| ① | `locator.py` | State-machine scan to find JSON blocks in raw text, schema-guided best-candidate selection |
| ② | `repair.py` | Chinese→English punctuation, bracket completion, comment stripping, json5 parsing |
| ③ | `validator.py` | Field presence & type check against schema, auto-retry with error feedback |

## Status

- [x] **Layer ① — `locator.py`** — complete, 48 tests passing
- [x] **Layer ② — `repair.py`** — complete, 44 tests passing
- [ ] Layer ③ — `validator.py` — planned

## Install

```bash
pip install llm-output-helper
```

Or from source:

```bash
git clone https://github.com/jiuwenyixi/llm-structured-output.git
cd llm-structured-output
pip install -e ".[dev]"
```

## Quick Start

```python
from llm_output_helper import locate_output_json, parse_json

# A typical messy Chinese LLM response
response = """
Let me think about this...
The user wants to know: 什么是机器学习？

｛
  "question_type"： "定义解释"，
  "answer"： "机器学习是人工智能的一个分支"，
  "confidence"： 0.9
｝
"""

# Layer ①: Find the JSON block in the raw text
raw_json = locate_output_json(
    response,
    schema={"question_type": str, "answer": str, "confidence": float}
)

# Layer ②: Fix Chinese punctuation, close brackets, parse
data = parse_json(raw_json)
print(data["answer"])  # → 机器学习是人工智能的一个分支
```

## How It Works

### Layer ①: JSON Locator

A character-by-character state machine that:

1. **Pre-processes** — converts Python-style `"""..."""` blocks and protects `[OUTPUT]` tags
2. **Scans** in two alternating phases: *SEEK* (looking for `{` or `[`) and *CAPTURE* (tracking bracket depth, string boundaries, escape sequences)
3. **Scores** — when multiple candidates are found and a schema is provided, each is parsed with json5 and scored by key overlap

### Layer ②: JSON Repair

Two-step pipeline:

**`repair_json_fragment`** — context-aware state machine:
- Normalizes Chinese/fullwidth structural punctuation (`：→:` `，→,` `｛→{` etc.)
- Normalizes smart quotes (`" "` → `"`)
- Preserves string content (Chinese colons inside values like `"地址：北京"` are left untouched)

**`complete_json`** — stack scanner:
- Closes unclosed brackets (`{` `[`)
- Closes unclosed string quotes
- Handles `//` and `/* */` comments

**`parse_json`** — one-call pipeline: repair → complete → json5.loads, with fallback wrapping for bare key:value pairs.

### What json5 alone CAN'T handle (why layer ② exists)

| Error | json5 | repair.py |
|-------|:---:|:---:|
| `：` Chinese colon | ❌ | ✅ |
| `，` Chinese comma | ❌ | ✅ |
| `｛｝［］` fullwidth brackets | ❌ | ✅ |
| `"` `"` smart quotes | ❌ | ✅ |
| missing closing `}`/`]` | ❌ | ✅ |
| trailing comma `,}` | ✅ | — |
| single quotes `'key'` | ✅ | — |
| `//` comments | ✅ | — |

## Development

```bash
pip install -e ".[dev]"
pytest -v
```

## License

MIT
