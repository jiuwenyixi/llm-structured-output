# Changelog

## 0.1.0 — 2026-10-24

First GitHub release of LLM Output Helper, an early-stage, framework-independent
Python library. Runtime dependency: json5. Python requirement: >=3.8.

### Features

- Locate JSON objects and arrays in model text and choose candidates by schema keys.
- Normalize Chinese/fullwidth structural punctuation and complete missing delimiters.
- Check required paths and primitive/container types with nested array wildcards.
- Retry extraction, parsing, and field failures through a caller-owned callback,
  under one shared bounded retry budget.

### Release preparation fixes

- Replace the invalid build backend with `setuptools.build_meta`.
- Preserve single-quoted strings and comments containing braces during location.
- Parse valid JSON5 before heuristic repair to preserve string contents.
- Complete unchanged truncated candidates when scoring schema matches.
- Resolve wildcard item schemas at each nesting level and report full error paths.
- Reject booleans for numeric fields and check required container shapes.
- Restore Agently attribution, Apache-2.0 notices, and combined license metadata.
- Add CI for Python 3.8/3.10/3.13, packaging checks, and installed-wheel smoke.

### Validation and limitations

144 deterministic tests pass locally on Python 3.13.3. No paid model request was
made. CI is the evidence for other declared matrix versions. This release does
not claim a benchmark win, ecosystem adoption, semantic correctness, or PyPI
publication. `schema` alone does not enforce the full schema: set `ensure_keys`.
Delimiter completion cannot recover missing facts. Async/streaming APIs,
Pydantic constraints, and repair provenance remain future work.
