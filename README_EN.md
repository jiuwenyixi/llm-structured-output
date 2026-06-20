# LLM Output Helper

[![中文](https://img.shields.io/badge/中文-README.md-red)](README.md)

Framework-free structured JSON output extraction for LLM responses. One function, three layers, zero framework dependencies.

```python
from llm_output_helper import structured_output

data = structured_output(
    text=model_response,
    schema={
        "summary": (str, "meeting conclusion, under 100 chars"),
        "action_items": [{
            "task": (str, "action item description"),
            "owner": (str, "assignee name"),
            "deadline": (str, "due date"),
        }],
    },
    ensure_keys=["summary", "action_items[*].task", "action_items[*].owner"],
    max_retries=2,
    on_retry=lambda feedback: call_your_llm(feedback),
)
```

## Why?

LLMs produce messy JSON — markdown fences, Chinese punctuation, trailing commas, truncated fragments, and chatty preambles. This tool uses three-layer fallback to turn any model response into clean structured data.

| Layer | Module | Job |
|-------|--------|-----|
| ① | `locator.py` | State machine finds JSON blocks in raw text; schema scoring picks best candidate |
| ② | `repair.py` | Chinese → English punctuation, bracket completion, json5 parsing |
| ③ | `validator.py` | Field presence & type check, auto-generates retry feedback |

## Install

```bash
pip install llm-output-helper

# or from source
git clone https://github.com/jiuwenyixi/llm-structured-output.git
cd llm-structured-output
pip install -e ".[dev]"
```

## Quick Start

```python
from llm_output_helper import structured_output

response = """
Let me think about this...

｛
  "question_type"： "math"，
  "answer"： "the answer is 42"
｝
"""

data = structured_output(
    text=response,
    schema={"question_type": (str, ""), "answer": (str, "")},
    ensure_keys=["question_type", "answer"],
)
print(data["answer"])  # → the answer is 42
```

With retry:

```python
def ask_llm(prompt):
    return your_model.chat(prompt)

data = structured_output(
    text=ask_llm("Summarize the meeting..."),
    schema={
        "summary": (str, "conclusion"),
        "action_items": [{
            "task": (str, "task"),
            "owner": (str, "person"),
        }],
    },
    ensure_keys=["summary", "action_items[*].task", "action_items[*].owner"],
    max_retries=2,
    on_retry=lambda fb: ask_llm(f"Fix the following issues:\n{fb}"),
)
```

## How It Works

### Layer ①: JSON Locator

Character-by-character state machine. Two phases: SEEK (find `{` `[`) and CAPTURE (track depth, strings, escapes). Handles fullwidth brackets `｛｝［］`. Truncated blocks are yielded for repair.

### Layer ②: JSON Repair

- **`repair_json_fragment`** — context-aware normalization of Chinese punctuation (`：→:` `，→,` `｛→{`), preserving string content
- **`complete_json`** — closes unclosed brackets, strings, and comments
- **`parse_json`** — one-call repair → complete → json5 parse

### Layer ③: Field Validation & Retry

`ensure_keys` supports `[*]` wildcards and dot paths:
- `"summary"` — must exist at top level
- `"action_items[*].task"` — every array element must have `task`

Validation failure → auto-generates feedback → calls `on_retry` → new text back to layer ①. Raises `ValidationError` when retries are exhausted.

## Development

```bash
pip install -e ".[dev]"
pytest -v   # 113 tests
```

## License

MIT
