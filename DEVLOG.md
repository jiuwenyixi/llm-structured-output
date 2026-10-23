# Development log

## 2026-10-24 — Codex — v0.2.0 optional model validation

- v0.1.0 was published at dd041fd29820f8ce4a3b818611b07dff54dbf8f6:
  https://github.com/jiuwenyixi/llm-structured-output/releases/tag/v0.1.0.
  CI 39995381231 passed all Python 3.8/3.10/3.13 jobs. The first tag and its
  wheel/sdist are retained unchanged.
- User explicitly requested a subsequent code iteration and a second release.
  Selected the optional Pydantic integration from the Agently comparison.
- Added output_model and model_strict without changing the original positional
  arguments or eagerly importing a new dependency. Configuration is checked once
  before callback work. Model constraints, normalized results, and ensure_keys
  participate in the same bounded attempt loop.
- Bounded Pydantic errors exclude input/context entries; custom validator TypeError
  and serialization errors propagate. Normal coercion follows model configuration;
  callers may explicitly enable strict mode. The output is a Python-mode dump,
  not a model instance or guaranteed JSON-serializable representation.
- Local optional suite: 171 tests passed; includes nested aliases/defaults,
  ranges/enums/lengths, root arrays, cross-field validators, budget sharing,
  missing/v1 dependency errors, lazy import, and invalid configuration.
- Release gate: base-only installation plus optional-extra installation, offline
  examples, wheel/sdist metadata checks, and the full remote Python matrix.
- No model requests or paid services are used in this release verification.

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
- Remote CI recovery: the gh OAuth credential could not create workflows, so the
  already-authorized GitHub connector created/updated the workflow. No account
  permission was expanded. The first workflow-only baseline run hit the original
  broken build backend. The first release-candidate run then hit a runner setup
  issue: `ubuntu-latest` selected Ubuntu 26.04, for which setup-python could not
  provision Python 3.8. Python 3.10 and 3.13 completed all functional/build/smoke
  steps. Pinned Ubuntu 22.04 and disabled matrix fail-fast; verify the replacement
  run before publishing, rather than treating the failed aggregate as passed.
