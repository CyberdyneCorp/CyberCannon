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

# The SvelteKit application, and the package manager it is run with. pnpm comes
# from corepack, which ships with node, so a developer and CI need node and
# nothing else; the version is pinned by `packageManager` in the app's
# package.json, which is what makes `corepack pnpm` reproducible.
web_dir := "apps/cybercanon/web"
pnpm := "COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm"

# Install the Python environment and the frontend one, both from committed
# lock files. `--frozen`/`--frozen-lockfile` on both halves for the same reason:
# CI, the image build and a developer's machine must resolve identically.
setup:
    uv sync --frozen
    cd {{ web_dir }} && {{ pnpm }} install --frozen-lockfile

# Everything CI runs, in CI's order: lint, the layering contract, complexity,
# the generated features, unit + BDD + conformance + integration + both
# traceability gates, and `openspec validate`. E2E is not here by design (D6) —
# `just test-e2e`.
#
# Measured runtime: ~150 s on a warm checkout (2564 tests, 657 scenarios, 0 absent),
# of which the frontend's own suites (`web-check`) are ~8 s including the
# production build the code-splitting assertion reads.
# Groups 6 and 7 of add-web-backend added a real PostgreSQL (pgserver) and a real
# S3 API (moto) to the conformance and integration layers; that is most of the
# increase, and it is the cost of the two hosted adapters being checked rather
# than described. Group 8 added an in-process CyberdyneAuth (`tools/canon_issuer`)
# for the same reason and at almost no cost: it signs with cached RSA keys and
# opens no socket. Groups 10 and 11 added the cross-surface equivalence suite and
# the recovery and concurrency drills, which run real git, a real PostgreSQL and a
# real S3 API against one project — the claim M2 makes is only worth its drill.
# Groups 1 and 2 of add-coolify-deployment added the boot-time configuration
# refusal, the readiness classification, the status surface and the access log —
# all in memory, so they cost about a second between them. Groups 3 to 5 added
# the container artifacts and the two secret scans (fast: the whole object
# database is under a megabyte), the migration release step and the
# `drop → migrate → rebuild` recovery against a real PostgreSQL, and the
# persistent-state suite, which stages real working copies and runs a real
# `uvicorn` to assert that a failed release leaves the previous version serving.
# That last one is where most of the added time is, and it is the only way to
# assert a property about processes.
# Re-measure and update that line when `check` grows a recipe;
# tests/tooling/test_recipes_and_ci.py fails the build if the record disappears.
#
# `web` joined the list in sprint S9, with the application shell: the address
# scheme, the closed route-state set, the typed client and the invalidation map
# are decided in TypeScript, and a suite `check` does not run is a suite CI
# never runs. It installs the frontend's own locked dependencies, so it needs
# node and nothing else. The structural constraints that must bite even when
# node is absent — D1's ViewModel boundary, D4's design-system rule, D7's import
# boundary — are in tests/tooling/test_web_structure.py and run under `test`.
check: lint imports complexity features test web-check spec

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
# `CANON_BLENDER=<path to blender>` additionally runs the FBX cross-check against
# a real DCC (tests/integration/test_fbx_against_blender.py); without it those
# tests skip, so this recipe behaves the same on every machine.
# Reachable on its own, and part of `just check` through `test` — CI runs
# `just check` and nothing else, so a suite outside it is a suite CI never runs.
test-integration *args:
    uv run --locked pytest -m integration {{ args }}

# End to end: Playwright over the web app, plus subprocess runs of `canon`.
# Deliberately outside `just check` (D6) — browsers and a compose stack are too
# slow to run constantly, and CI runs this recipe in its own job.
#
# The recipe stays one command because everything it needs, it brings up itself:
# the browsers are installed by the run (tests/e2e/conftest.py) and the stack is
# started and torn down by it (tests/e2e/stack.py, deploy/e2e/compose.yaml). Set
# CANON_E2E_BASE_URL to run against a stack that is already up instead; with
# neither that variable nor docker, the browser suites skip and say so rather
# than reporting green over nothing.
#
# A failing run leaves its trace, screenshot and video under reports/e2e/ (6.4);
# a passing one leaves nothing, because artifacts nobody keeps are not there on
# the day one is needed.
test-e2e *args:
    uv run --locked pytest -m e2e {{ args }}

# Run the FastAPI service. It reads its configuration from the environment and
# refuses to start naming every required variable it does not have — there is no
# file fallback, because Coolify supplies configuration as environment and a file
# that disagrees with it is a deployment behaving differently from how it is
# described (openspec/project.md).
api *args:
    uv run --locked python -m cybercanon.api {{ args }}

# Apply db/migrations to the configured database — the release step, run before
# a new version starts serving (openspec/project.md). It reads CANON_DATABASE_URL
# from the same configuration the service reads, so a deployment cannot migrate
# one database and serve another, and it is idempotent: re-running it applies
# nothing, which is what makes a retried deploy safe.
migrate *args:
    uv run --locked python -m cybercanon.api.migrate {{ args }}

# `drop → migrate → rebuild` — the recovery for an index that was lost or left
# at a schema no migration can advance (add-coolify-deployment D5). There is no
# backup and there will not be one: the index is derived, so the working copies
# named here are what it is rebuilt from.
#
#     just recover-index /data/worktrees/ronin
#
# It reads CANON_DATABASE_URL from the same configuration the service reads, and
# it is the procedure `docs/recovery.md` documents rather than a second one.
recover-index *args:
    uv run --locked python -m cybercanon.api.recover {{ args }}

# Run the FastMCP read server over stdio for the repository this is run in.
# An agent client spawns `canon mcp serve` directly — this recipe is the way a
# person starts the same server by hand, so there is still exactly one way to
# run the operation.
mcp *args:
    uv run --locked canon mcp serve {{ args }}

# Write every export fixture into a directory so a person can open one. The
# suites build these at test time; this is how you look at what they built.
fixtures directory:
    PYTHONPATH=tools uv run --locked python -m canon_fixtures {{ directory }}

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

# Run the SvelteKit dev server against the API named by PUBLIC_CANON_API_URL.
web *args:
    cd {{ web_dir }} && {{ pnpm }} run dev {{ args }}

# Build the application the way a deployment builds it.
web-build:
    cd {{ web_dir }} && {{ pnpm }} install --frozen-lockfile
    cd {{ web_dir }} && {{ pnpm }} run build

# The frontend's own checks: svelte-check over the whole application, then its
# unit suites — the address scheme (D3), the closed route-state set (D6), the
# typed client, the invalidation map (D2) and the code-splitting assertion,
# which builds the application and reads the client manifest (D7).
web-check:
    cd {{ web_dir }} && {{ pnpm }} install --frozen-lockfile
    cd {{ web_dir }} && {{ pnpm }} run check
    cd {{ web_dir }} && {{ pnpm }} run test

# Apply every unformatted fix ruff can make.
format:
    uv run --locked ruff check --fix .
    uv run --locked ruff format .
