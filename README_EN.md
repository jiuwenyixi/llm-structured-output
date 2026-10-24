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
pip install "git+https://github.com/jiuwenyixi/llm-structured-output.git@v0.2.0"

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

## Optional Pydantic v2 constraints (v0.2.0)

```bash
pip install "llm-output-helper[pydantic] @ git+https://github.com/jiuwenyixi/llm-structured-output.git@v0.2.0"
```

```python
from typing import Literal
from pydantic import BaseModel, Field
from llm_output_helper import structured_output

class Ticket(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    priority: int = Field(ge=1, le=3)
    status: Literal["open", "closed"]

data = structured_output(
    '{"title":"Fix parser", "priority":2, "status":"open"}',
    output_model=Ticket,
    model_strict=True,
)
```

The whole model is validated even without `ensure_keys`. Constraints, aliases,
defaults and custom model rules belong to Pydantic. Model errors use bounded
field feedback and share the existing callback retry budget; exhaustion raises
this library's `ValidationError`. Missing dependencies, configuration errors,
validator programming errors and dump failures propagate without retries.

Results remain ordinary containers from `model_dump(mode="python")`, using
normalized field names and validated/defaulted values. Types such as dates or
enums may remain Python objects, so results are not necessarily JSON-serializable.
`ensure_keys` checks normalized names after model validation. `model_strict=None`
honors model configuration and may coerce values; True forbids coercion and False
allows it. This setting does not disable JSON repair. Without an explicit schema,
model fields/string aliases provide candidate-selection hints; validation is the
final authority. RootModel arrays are supported; scalar roots are not.

See [examples/pydantic_validation.py](examples/pydantic_validation.py) for an
offline constraint failure followed by a successful bounded retry.

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

## Validation and recovery limits

- `schema` guides JSON candidate selection and type checks for paths listed in
  `ensure_keys`. Passing only a dictionary `schema` does not validate every field;
  use `output_model` for whole-model validation.
- Nested wildcards such as `groups[*].items[*].name` use the corresponding item
  schema. Plain schema checks reject booleans for integer/float fields; Pydantic
  coercion follows its configuration and `model_strict`.
- Extraction, parsing, and field validation share one `max_retries` callback
  budget. Without a callback or after exhaustion, extraction/parse failures raise
  `ValueError`; field failures raise `ValidationError`. Callback exceptions propagate.
- Closing brackets or strings does not recover missing facts or prove business
  correctness. Add domain validation before consuming important data.
- Pydantic v2 model validation is optional. A standalone JSON Schema validator,
  async callbacks, and incremental streaming are not implemented. Results may be
  objects or arrays.
- This is a GitHub release. The install command uses the version tag and does not
  claim publication on PyPI. See [examples/basic.py](examples/basic.py) for an
  offline executable example.

## Development

```bash
pip install -e ".[dev]"
pytest -v   # base: 148 passed, model suite skipped without Pydantic
pip install -e ".[pydantic]"
pytest -v   # 171 tests with Pydantic v2
```

## License

Project code is distributed under MIT and Apache-2.0, as applicable. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), [LICENSE](LICENSE), and
[LICENSE-APACHE-2.0](LICENSE-APACHE-2.0) for scope and terms.
