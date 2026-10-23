# Third-party notices

## Agently

Project: https://github.com/AgentEra/Agently

Copyright 2023-2026 AgentEra(Agently.Tech).
Licensed under the Apache License, Version 2.0; see LICENSE-APACHE-2.0.

Portions of `llm_output_helper/locator.py` and `llm_output_helper/repair.py`
are adapted from Agently's JSON location, structural punctuation repair,
and JSON completion approach. These adapted files are distributed under
Apache-2.0. The exact original upstream revision was not recorded when
this project was created. The current provenance review compared against
Agently commit b385ab2b8abfaf583d79ddbb1d5218646610a9da.

Local modifications include standalone module/function APIs, fullwidth
bracket handling, extraction of truncated blocks, JSON5 string/comment-aware
location, candidate completion for schema scoring, and parsing valid JSON5
before applying repair heuristics. These modules do not depend on Agently
at runtime. The entry point, validator, and project-specific additions are
covered by the project's MIT LICENSE unless otherwise marked.

Distribution metadata therefore declares `MIT AND Apache-2.0`. This notice
documents source attribution; it does not imply endorsement by Agently.
