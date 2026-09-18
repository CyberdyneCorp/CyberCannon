# CyberCanon task runner.
#
# There is exactly one way to run any operation, and it is a recipe here.
# `just check` is the contract: CI runs that recipe and nothing else, so a green
# local `just check` means a green pipeline. A check that exists in CI but not in
# this file is a bug in the justfile, and tests/tooling/test_ci_workflow.py fails
# the build over it.

# Pinned so CI, the image build and a developer's machine validate with the same
# openspec. npx installs it on demand, which keeps CI's only step `just check`.
openspec_version := "1.13.1"

# Backend cognitive complexity target (openspec/project.md).
max_complexity := "15"

# Show the available recipes.
default:
    @just --list

# Install the Python environment from the committed lock file.
setup:
    uv sync --frozen

# Everything CI runs, in CI's order: lint, the layering contract, complexity,
# the generated features, unit + BDD + conformance + integration + both
# traceability gates, and `openspec validate`. E2E is not here by design (D6) —
# `just test-e2e`.
#
# Measured runtime: ~16 s on a warm checkout (889 tests, 657 scenarios, 0 absent).
# Re-measure and update that line when `check` grows a recipe;
# tests/tooling/test_recipes_and_ci.py fails the build if the record disappears.
check: lint imports complexity features test spec

# ruff — style and formatting.
lint:
    uv run --locked ruff check .
    uv run --locked ruff format --check .

# import-linter — domain <- application <- adapters, inbound never imports
# outbound, and the domain imports no third-party package (D10).
imports:
    PYTHONPATH=tools uv run --locked lint-imports

# Cognitive complexity against the backend target.
complexity:
    uv run --locked complexipy --max-complexity-allowed {{ max_complexity }} libs services tools tests scripts

# Unit, BDD, port-conformance and integration tests, with the traceability gates
# and the domain coverage threshold (D7). E2E is excluded: it needs a compose
# stack and browsers, and `just check` has to stay fast enough to run
# constantly (D6).
test *args:
    uv run --locked pytest --cov -m "not e2e" {{ args }}

# Only the unit layer: domain and application, pure, no I/O.
test-unit *args:
    uv run --locked pytest -m unit {{ args }}

# Only the port-conformance suites: every port against its in-memory fake and
# every real adapter, so a fake that lies fails the build.
test-conformance *args:
    uv run --locked pytest -m conformance {{ args }}

# Only the generated spec scenarios and the traceability gates.
# `just test-bdd --tag asset-validation` runs one capability (D5). A tag selects
# scenarios and nothing else, so while a capability is still entirely pending it
# selects nothing and pytest exits 5.
test-bdd *args:
    uv run --locked pytest -m bdd {{ args }}

# Only the integration layer: the real outbound adapters against real files,
# written from code by `tools/canon_fixtures` so nothing binary lives in git.
# Reachable on its own, and part of `just check` through `test` — CI runs
# `just check` and nothing else, so a suite outside it is a suite CI never runs.
test-integration *args:
    uv run --locked pytest -m integration {{ args }}

# End to end: Playwright over the web app, plus subprocess runs of `canon`.
# Deliberately outside `just check` (D6) — browsers and a compose stack are too
# slow to run constantly, and CI runs this recipe in its own job. The browsers,
# the compose stack and the trace artifacts are group 6 of add-test-strategy
# (sprint S9); until then this runs the e2e layer as it stands.
test-e2e *args:
    uv run --locked pytest -m e2e {{ args }}

# Regenerate tests/bdd/features/ from the spec deltas. Nobody hand-writes a
# .feature; this recipe overwrites any that somebody did.
gen-features:
    uv run --locked python scripts/gen_features.py

# D1 — the committed features are exactly what the spec deltas generate.
features:
    uv run --locked python scripts/gen_features.py --check

# openspec validate --all --strict.
spec:
    npx --yes @fission-ai/openspec@{{ openspec_version }} validate --all --strict

# Apply every unformatted fix ruff can make.
format:
    uv run --locked ruff check --fix .
    uv run --locked ruff format .
