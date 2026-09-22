# Tasks

## 1. Harness layout and runners

- [x] 1.1 Create `tests/{unit,bdd/features,bdd/steps,e2e,conformance}/` and configure pytest with markers per layer; verify `pytest --collect-only` finds each layer and `-m unit` selects only unit tests
- [x] 1.2 Add `pytest-bdd`, `playwright` and `pytest-xdist` via `uv`, commit the updated lock, and verify `uv sync --frozen` reproduces the environment
- [x] 1.3 Configure coverage on the domain package only with an enforced threshold (D7) and verify the run fails when domain coverage drops below it and does not fail on adapter coverage

## 2. The spec-to-feature generator

- [x] 2.1 Write `scripts/gen_features.py` reading every `openspec/changes/*/specs/*/spec.md` and emitting Gherkin that preserves the requirement name, scenario name and GIVEN/WHEN/THEN lines verbatim; verify the current 657 scenarios generate without loss
- [x] 2.2 Tag each generated feature with its change and capability (D5) and verify `just test-bdd --tag asset-validation` selects only that capability's scenarios
- [x] 2.3 Make generation deterministic and idempotent; verify running it twice produces byte-identical output
- [x] 2.4 Fail loudly and name the file when a spec cannot be parsed (never skip it) and verify with a deliberately malformed spec fixture
- [x] 2.5 Add `just gen-features`, commit the generated features, and add a CI check that regenerates and fails on any difference (D1); verify a hand-edited feature fails that check

## 3. Traceability gates

- [x] 3.1 Implement the gate that fails when a requirement has no scenario that executes, naming the requirement and its spec path; verify against a spec fixture with a scenario-less requirement
- [x] 3.2 Implement the gate that fails when a generated scenario has no step definition, naming the spec file and line (D3); verify the message points at the spec, not at the generated feature
- [x] 3.3 Implement the single explicitly-marked pending list as the only escape hatch, and verify an unlisted missing step still fails while a listed one reports as pending
- [x] 3.4 Emit a per-capability report of scenarios executing, pending and absent, and verify it is written on every `just check` so the pending count is a live progress measure

## 4. Step definitions and fixtures

- [x] 4.1 Establish per-capability step modules under `tests/bdd/steps/<capability>.py` (D4) and verify a step defined for one capability does not match another capability's scenario
- [x] 4.2 Expose the in-memory fakes from `application/testing/` as shared BDD fixtures and verify a BDD step and a unit test can use the same fake instance shape
- [x] 4.3 Write the universal steps only (an actor exists, a project exists, an asset exists) and verify no capability-specific vocabulary leaks into the shared module

## 5. Port conformance suites

- [x] 5.1 Establish the conformance suite pattern — one parametrised suite per port, run against the in-memory fake and every real adapter; verify it is collected for both
- [x] 5.2 Verify a fake that diverges from its real adapter fails the suite, using a deliberately divergent fake fixture

## 6. End-to-end

- [x] 6.1 Configure Playwright with browsers installed in CI and a viewport matrix including tablet width (D6); verify a smoke test runs in every configured viewport
- [x] 6.2 Provide the compose stack e2e runs against and verify `just test-e2e` brings it up, runs and tears it down cleanly
- [x] 6.3 Add the subprocess harness for `canon` end-to-end runs and verify it asserts exit codes and stdout separately
- [x] 6.4 Attach traces, screenshots and video to failing e2e runs and verify the artifacts appear for a deliberately failing test

## 7. Recipes and CI

- [x] 7.1 Add `just test-unit`, `just test-bdd`, `just test-e2e`, `just gen-features` and verify each runs standalone from a clean checkout
- [x] 7.2 Make `just check` run unit + BDD + conformance + both traceability gates, with e2e excluded (D6); verify its runtime on the current suite and record it
- [x] 7.3 Wire CI to run `just check` on every push and `just test-e2e` on the branch, and verify the initial run reports 657 pending scenarios and zero failures
