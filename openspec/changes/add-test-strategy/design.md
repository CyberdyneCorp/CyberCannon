# Design

## Context

See `proposal.md — Why`. One constraint dominates: the spec deltas are already
written in a structure very close to Gherkin — `### Requirement:` with
`#### Scenario:` blocks whose bullets are `- **GIVEN** / **WHEN** / **THEN**`. That
was not an accident of style; it is what makes generation possible instead of
transcription.

## Goals / Non-Goals

**Goals:**

- Make spec drift a failing build rather than a discovery.
- One runner, one fixture system, one command.
- Keep the domain test suite fast enough that nobody avoids running it.

**Non-Goals:**

- No abstraction over the test frameworks. Tests import pytest directly.
- No shared "test utilities" package beyond the fakes that already live in
  `application/testing/`.

## Decisions

### D1 — `.feature` files are generated, committed, and verified to be unchanged

The generator emits Gherkin from the spec deltas. Output is committed, and CI
regenerates and fails on any difference.

*Why:* committing gives readable diffs and lets step definitions reference real
files; regenerating in CI means a hand edit cannot survive. The spec stays the
single source without giving up tooling that expects files on disk.
**Alternative rejected:** generating at test-collection time only — no diff to
review, and a spec change silently rewrites what is being tested mid-run.

### D2 — pytest-bdd over behave, because there must be exactly one runner

*Why:* behave reads more like pure Gherkin, but it brings its own runner, its own
fixture model and a second entry in `just check`. pytest-bdd puts scenarios in the
same process, the same fixtures and the same conftest as the unit and conformance
suites — which matters because a BDD step for `asset-validation` needs precisely the
hand-built `MeshFacts` fixtures the unit tests already have.
**Cost accepted:** step definitions are Python decorators rather than a separate
layer, so a non-programmer can read the `.feature` but not the steps. The `.feature`
is the half that needed to be readable.

### D3 — Two gates, and they fail in opposite directions

- **Requirement without an executing scenario** → fail. Catches a requirement nobody
  verified.
- **Generated scenario without a step definition** → fail, naming the spec file and
  line. Catches a spec that moved ahead of the code.

*Why:* one gate alone is satisfiable by cheating. Coverage-only lets someone write a
scenario that asserts nothing; step-completeness alone lets a requirement carry no
scenario at all. Together they pin the spec and the code to each other.

*Consequence to accept:* adding a requirement to a spec **breaks the build until
someone implements its step**. That is the point, and it will be annoying in exactly
the moment it is doing its job.

### D4 — Step definitions are scoped per capability, not shared globally

`tests/bdd/steps/<capability>.py`. A shared module holds only genuinely universal
steps (an actor exists, a project exists).

*Why:* a global step namespace is how BDD suites rot — a step phrased for one
capability silently matches another's scenario and asserts the wrong thing. Scoping
keeps a step's meaning attached to the capability that wrote it.

### D5 — Generated features carry the spec path as a tag

Each feature is tagged with its change and capability, so `just test-bdd --tag
asset-validation` runs one capability, and a failure names where the requirement
lives.

*Why:* 657 scenarios is too many to run tightly while working on one change, and a
failure that does not point at a spec file wastes the traceability.

### D6 — Playwright, and e2e is gated rather than part of `just check`

`just check` runs unit + BDD + conformance + gates. E2E needs a compose stack and is
run by `just test-e2e` and by CI on the branch, not on every local save.

*Why:* `just check` is specified as the thing whose green state means a green
pipeline, so it must stay fast enough to run constantly. **Cost accepted:** e2e
failures are found later than unit failures — acceptable, because e2e covers surfaces
that unit and BDD cannot reach at all.

*Playwright rather than Cypress:* it drives multiple viewports in one run, which the
iPad-width and stylus requirements in `model-sheet-2d` need, and it can attach a
trace to a failure, which is the difference between a flaky e2e suite being debugged
and being deleted.

### D7 — Coverage thresholds on the domain package only

*Why:* the domain is pure, so a gap there is a genuine untested rule. Adapters are
integration-shaped, and a coverage number on them produces tests written to move the
number rather than to catch a defect. **Alternative rejected:** a repository-wide
threshold, which is the standard choice and reliably produces exactly those tests.

## Risks / Trade-offs

- **The generator cannot parse a spec someone wrote unusually** → the generator fails
  loudly naming the file, rather than skipping it. A skipped spec is an untested
  requirement that looks tested.
- **657 scenarios take too long to run** → D5's tags plus pytest-xdist; if the full
  suite becomes slow enough to avoid, that is a signal to split by capability in CI,
  not to run less.
- **D3 breaks the build when a spec is edited ahead of the code** → deliberate.
  The escape hatch is a single explicitly-marked pending list, reviewed like any
  other exception, never a silent skip.
- **Cost accepted:** a generator to write and maintain, and a rule that no one edits
  a `.feature`. In exchange the specs stop being documentation and start being the
  test suite.

## Migration Plan

Greenfield — this lands before any domain code, so there is nothing to migrate. The
first run generates 657 scenarios, every one of them pending, and the pending list
shrinks as changes are implemented. That list is also a live progress measure the
roadmap does not otherwise have.

## Open Questions

- **Whether generated features live under `tests/bdd/features/` or beside their
  change.** A path choice; changes no gate.
- **Whether to run the full BDD suite per pull request or only the touched
  capabilities.** Answerable once the suite has a measured runtime.
