# Development log

## 2026-10-24 — Codex — first release preparation

- Scope: publish the first GitHub release and review current Agently structured
  output changes. Keep the library framework-independent; no paid model calls.
- Baseline: 9ff2c7efbfa34cbf2bd59ce850d5b79b0edc5570; 113 tests passed.
- Build initially failed: unavailable `setuptools.backends._legacy:_Backend`.
  Replaced it with the standard `setuptools.build_meta` backend.
- Reproduced and fixed JSON5 string/comment boundary corruption, missing
  completion during candidate scoring, wildcard item type leaks, multi-wildcard
  traversal, boolean-as-integer acceptance, and parse failures bypassing retry.
- Added 31 regression cases: 144 tests passed locally. New cases validate observable
  content preservation, nested type rejection, and shared callback budgets.
- Preserved existing schema-only behavior, documented explicit `ensure_keys`,
  early-stage limitations, and GitHub-tag installation.
- Compared adapted modules with current Agently sources; restored attribution
  and Apache-2.0 notices without replacing the project's MIT-covered additions.
- Release gate: build sdist/wheel, check metadata, install into a clean environment
  and run offline examples, then verify remote CI before creating the GitHub release.
- Local gate passed: both distributions built; `twine check` passed; a separate
  fresh venv imported the installed wheel outside the checkout, ran the offline
  example and all 144 tests, and verified all three license/notice files in the wheel.
  Python was 3.13.3. Build emitted legacy-license-metadata deprecation warnings;
  that metadata syntax is retained for the declared Python 3.8 build compatibility.
- Larger iterations (Pydantic, async/streaming, provenance) require separate API
  design and representative evaluation; they are not included in 0.1.0.
