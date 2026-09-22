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
# Measured runtime: ~350 s on a warm checkout — three timed runs of the same
# tree gave 319 s, 345 s and 397 s, which is the spread a laptop gives and the
# reason this is a record rather than a budget — 3775 Python tests (3765 passed,
# 10 skipped, 0 xfailed, 122 e2e deselected) plus 728 frontend tests across 35
# files, 657 scenarios (446 executing, 211 pending), 0 absent — of which the
# frontend's own suites (`web-check`) are ~6 s including the build the
# code-splitting assertion reads. The skips are the
# opt-in Blender cross-check, which runs only with `CANON_BLENDER` set; the
# xfail is gone because the defect it recorded — a multi-object OBJ losing every
# part name but one — is fixed rather than tolerated.
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
# assert a property about processes. Group 3's remaining work added the build
# context guard, the release ledger's three commands and the suite that starts
# the built web application to ask a running process whether it is ready with no
# API answering — about a second between them, because the build it runs is the
# one `web-check` already produced. Groups 6 and 7 added the rollover suite —
# which starts two real `uvicorn` processes and reads across a deploy, about ten
# seconds — and the three recovery drills, which destroy one volume at a time
# and time the procedure that gets it back against a real git, PostgreSQL and S3
# API. The drills are the expensive kind of test and they are the only kind that
# can tell anybody how long a recovery takes. Group 8 added the deployment
# manifest's conformance check (instant — it reads one file), the key cache's
# window, the component-restart matrix and the pre-production standup, which
# stands an environment up in the Migration Plan's order against a real
# PostgreSQL, a real S3 API and a real remote; plus the two un-hosted surfaces,
# which spawn `canon` and the agent server with the network — and then the
# ability to listen — denied in the child.
# Group 3's last three tasks and the deployment blockers found in review added
# the container suites that need a real engine: the API image built twice and
# compared (task 3.1), the web image built and *run* with no API reachable (3.2)
# and the rollback drill, which builds this revision and the one before it and
# redeploys the earlier digest with both build contexts deleted (3.5). They are
# skipped where there is no `docker`, and where there is one they are the
# slowest thing in `check` on a cold cache — a full `uv sync` per image — and
# seconds on a warm one. That is the cost of asserting a property of an
# artifact rather than of a Dockerfile; a suite that skipped silently would
# report green over nothing, which is how this project already lost one
# afternoon.
# add-concept-ingestion added the image half of the product: the domain's slot,
# limit and carry-forward rules (pure, instant), two more port conformance
# suites against Pillow, a `ViewIndex` suite against the same PostgreSQL the
# other index suites use, and one integration suite that builds two real git
# checkouts and drives `canon add-view` and the ingestion endpoint over them to
# compare what landed — which is the only way to check that the two surfaces
# write the same commit. About seventy seconds between them, nearly all of it
# the real repositories.
# add-model-sheet-2d added the annotation half of the product and it is the
# largest single addition since the hosted backend: the domain's threads,
# filters, marks and triage policy (pure, instant), the write path over a real
# `asset.yaml` through the comment-preserving round trip, the annotation and
# triage HTTP surface, and two integration suites over **real git** — the write
# path, which asserts that adding, replying to and resolving an annotation
# leaves every unrelated line of a hand-authored specification byte-identical,
# and the acceptance run, which drives a whole triage pass and then runs
# `canon compile` as a subprocess against it. Those two are where its ~20 s go,
# and they are the only way to check a claim about a file and a process. On the
# frontend it added the one shared `AnnotationViewModel` and the 2D sheet: 194
# more vitest cases, most of them the coordinate round trip exercised across
# every zoom, pan, display size, pixel ratio and rendition at once.
# add-viewer-3d added the 3D half and it is cheap where it matters: the anchor
# resolution domain, the preview descriptor, the clip coverage and the viewer's
# HTTP surface are all pure or in-memory (instant), and the frontend's own
# suites parse **real GLB bytes written from code** by
# `apps/cybercanon/web/tests/support/glb.ts` — the retopology acceptance loads
# two exports of one asset and asserts that three anchors resolve and one
# orphans, with no GPU anywhere. That is the whole point of D6's split: the
# expensive half is the drawing, and nothing in `check` draws.
# Group 7 of add-web-app-shell added the per-route enumeration of the closed
# route-state set — it drives every route's real `load` and renders what came
# back, so it costs milliseconds — and, outside `check`, 84 e2e assertions over
# the viewport matrix. It also added the route-module export rule to
# tests/tooling/test_web_structure.py, which reads four files.
# Re-measure and update that line when `check` grows a recipe;
# tests/tooling/test_recipes_and_ci.py fails the build if the record disappears.
#
# `web-check` runs **before** `test`, and that order is asserted rather than
# left to habit (tests/tooling/test_justfile.py): its vitest run builds the
# application, and tests/integration/test_web_readiness_process.py starts that
# build — the `node build` the image's CMD runs — to ask the running artifact
# whether it is ready with no API answering. A Python suite that had to build
# the frontend itself would duplicate the build; one that skipped when the build
# was absent would be a suite CI never really runs.
#
# `web` joined the list in sprint S9, with the application shell: the address
# scheme, the closed route-state set, the typed client and the invalidation map
# are decided in TypeScript, and a suite `check` does not run is a suite CI
# never runs. It installs the frontend's own locked dependencies, so it needs
# node and nothing else. The structural constraints that must bite even when
# node is absent — D1's ViewModel boundary, D4's design-system rule, D7's import
# boundary — are in tests/tooling/test_web_structure.py and run under `test`.
check: lint imports complexity features web-check test spec

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

# Run the three recovery drills against a pre-production project and record what
# they cost (add-coolify-deployment D9). It DESTROYS the named volumes and then
# runs the documented procedure over each, measuring only the recovery:
#
#     just drill --project ronin --working-copy /data/worktrees/ronin --blobs /data/blobs
#
# Every run appends date, procedure and measured duration to deploy/recovery.md,
# because a record somebody has to remember to write is a record nobody writes.
# Never point it at a production volume: the first thing it does is delete one.
drill *args:
    PYTHONPATH=tools uv run --locked python -m canon_drill run {{ args }}

# The gate over that log: non-zero when a procedure has never been drilled, when
# its most recent drill is older than the stated interval, or when that drill
# took longer than deploy/recovery.md says it should.
#
# Deliberately **not** part of `just check`. Staleness is a function of the date
# rather than of the change under review, so a build that ran it would start
# failing on a Tuesday for a repository nobody had touched — which teaches
# people to ignore it. It is the release pipeline's gate and the drill job's own
# exit code; `just check` asserts instead that the log is complete and that every
# recorded duration is within its expectation (tests/tooling/test_recovery_document.py).
drill-check *args:
    PYTHONPATH=tools uv run --locked python -m canon_drill check {{ args }}

# Record what a build produced: the digest an image was built as, against the
# revision it was built from (add-coolify-deployment, task 3.3). The build
# pipeline runs this immediately after it builds an image, and the digest comes
# from the engine that built it:
#
#     just release-record --image api --revision $GIT_SHA \
#         --digest "$(docker image inspect --format '{{{{.Id}}}}' cybercanon-api:$GIT_SHA)"
#
# Recording a second, different digest for one revision exits non-zero, which is
# how "built once per revision and promoted unchanged" is enforced rather than
# asked for: a rebuild has nowhere to write what it produced.
release-record *args:
    PYTHONPATH=tools uv run --locked python -m canon_release record {{ args }}

# The promotion gate: what each environment is running, against the record.
#
#     just release-promotion --image api --revision $GIT_SHA \
#         --running pre-production=sha256:... production=sha256:...
#
# Non-zero when an environment is running something the ledger did not record —
# an artifact that was rebuilt rather than promoted — naming both digests.
release-promotion *args:
    PYTHONPATH=tools uv run --locked python -m canon_release promotion {{ args }}

# The withdrawal: the digest to redeploy for the revision being returned to.
# It prints a digest and never builds one; a revision the ledger does not hold
# is reported instead, because an artifact nobody verified is not a rollback
# target.
release-rollback *args:
    PYTHONPATH=tools uv run --locked python -m canon_release rollback {{ args }}

# Is what we deploy what the specification says we deploy? (task 8.5)
#
# It reads deploy/coolify.yaml — the four applications, their hosts, volumes,
# environment and health configuration — against `deployment-operations` and
# against the settings the service declares. A fifth application, or one
# deploying the `canon` binary or the agent server, is a non-zero exit naming
# the specification: *"no other component SHALL be added to the hosted
# inventory without a specification change"*.
#
# Reachable on its own for a release pipeline, and part of `just check` through
# `test` (tests/tooling/test_deployment_inventory.py runs the same function), so
# a drifting manifest fails the build rather than the deploy.
deploy-check *args:
    PYTHONPATH=tools uv run --locked python -m canon_deploy check {{ args }}

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
