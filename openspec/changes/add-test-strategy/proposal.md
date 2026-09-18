# Proposal

## Why

The specs contain **657 GIVEN/WHEN/THEN scenarios**. Nothing executes them. Left
that way they are 657 statements that were true the day they were written, and the
code drifts away from them silently — the failure mode this whole project exists to
prevent, reproduced one level up.

The harness has to exist **before the first line of domain code**, for a blunt
reason: eleven changes are about to be implemented, and without one agreed harness
each arrives with its own. Retrofitting a test strategy across eleven changes costs
more than writing it once now.

This is **roadmap position S0** — the sprint before the first domain code.

## What Changes

- **Three layers, mapped to the architecture.**
  - **Unit (pytest)** — domain and application, pure, no I/O. The validator suite
    runs over hand-built `MeshFacts` with zero files on disk, as
    `add-asset-spec-and-validator` already requires.
  - **BDD (pytest-bdd)** — the spec scenarios, executable.
  - **E2E (Playwright)** — the web application, plus subprocess runs of `canon`.
  - **Port conformance** — one suite per port, run against the in-memory fake *and*
    every real adapter, so a fake that lies is a failing build.
- **`.feature` files are GENERATED from the spec deltas, never hand-written.** A
  generator reads `openspec/changes/*/specs/*/spec.md` and emits Gherkin preserving
  the requirement name, the scenario name and its GIVEN/WHEN/THEN lines. The spec is
  the source; the features are build output.
- **Two traceability gates in CI:**
  1. a requirement with no scenario that executes → **fail**;
  2. a generated feature whose steps have no definition → **fail**, naming the spec
     file and line.
- **`just test-unit`, `just test-bdd`, `just test-e2e`**, with `just check` running
  unit + BDD + the traceability gates, and e2e gated behind a compose stack.
- **Coverage thresholds on the domain package only** — the layer where a gap is a
  real hole rather than an adapter nobody can unit test.

## Capabilities

### New Capabilities

None. This change introduces **no product behaviour**: it adds a test harness and a
build gate. Per the project's own rule — specs describe behaviour, so if behaviour
does not change, no spec should change — this change sets `skip_specs: true` rather
than inventing a requirement to satisfy validation.

### Modified Capabilities

None.

## Non-goals

- **No test content.** This change delivers the harness and the gates; the tests
  themselves belong to the change whose behaviour they verify.
- **No hand-written `.feature` files, ever.** A hand-edited feature is a fork of the
  spec, and the generator overwrites it.
- **No mutation testing, no property-based testing, no load testing.** Each is
  defensible later; none is needed to stop drift.
- **No visual regression testing.** The design system owns that.
- **No BDD for the CLI's own help text or for infrastructure recipes.**
- **No coverage threshold outside the domain package.** A number on adapter coverage
  buys tests written to move the number.

## Impact

- **New dependencies** — `pytest-bdd`, `playwright`, `pytest-cov` (already present),
  and a small generator script under `scripts/`.
- **New layout** — `tests/unit/`, `tests/bdd/{features,steps}/`, `tests/e2e/`,
  `tests/conformance/`.
- **Binds every later change** — each arrives with unit tests for its domain, step
  definitions for its generated features, and e2e only where it ships a surface.
  The task lists already written assume pytest; they gain step definitions.
- **Changes `just check`** — which `add-asset-spec-and-validator` makes the single
  CI entry point, so the gates apply from the first commit of code.
