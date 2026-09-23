# The API image: built once per revision, promoted unchanged (D1, and
# `deployment-operations`: *"a deployable artifact SHALL be built once per
# revision and promoted between environments without rebuilding"*).
#
# Three rules decide everything below, and each of them is checked by
# `tests/tooling/test_container_artifacts.py` rather than trusted:
#
# 1. **Nothing environment-specific at build time.** No `ARG` carrying an
#    endpoint, no `ENV` carrying a credential, no `.env` copied in, no build
#    stage that reaches a network service of ours. The image cannot tell which
#    environment it is in, which is what makes staging's verification mean
#    something in production — and what makes *"inspecting an artifact reveals
#    nothing about where it is running"* true by construction.
# 2. **Configuration is the environment, with no file fallback.** The service
#    refuses to start naming every variable it does not have
#    (`cybercanon.adapters.wiring.configuration`), so a missing variable is a
#    refused boot rather than a request that fails at three in the morning.
# 3. **Migrations are a release step, not a start step** (D4). The start command
#    below serves and nothing else: Coolify runs
#    `python -m cybercanon.api.migrate` as the pre-deploy command, a non-zero
#    exit aborts the release, and no instance of the new version ever starts.
#    A `migrate && serve` entry point would run the migration once per instance,
#    which is exactly what *"no instance SHALL attempt a migration"* forbids.
#
# Reproducibility: the environment comes from the committed `uv.lock` with
# `--frozen`, so two builds of one revision install identical versions. What
# makes promotion safe is still the recorded digest (`deploy/digests.json`,
# `tools/canon_release`) rather than a hope that two builds agree byte for byte.

FROM python:3.12-slim

# Two packages, and neither is a convenience.
#
# **git**, because the working copy is the source of truth: the service reads
# specifications out of a real repository's object database and writes back by
# committing and pushing.
#
# **curl**, because the platform's health check runs *inside* the container.
# Coolify's check is an HTTP request issued by the container itself, so a health
# probe with no client to make it with reports unhealthy on a service that is
# perfectly well — and a container the platform believes is unhealthy is never
# routed to, which is the whole of `/readyz` being gated off. `python:3.12-slim`
# ships no `curl`, so this is what puts one there;
# `tests/tooling/test_container_artifacts.py` runs `curl --version` inside the
# built image rather than reading this line, because a base image that stopped
# shipping something is exactly the class of thing a `Dockerfile` cannot assert
# about itself.
RUN apt-get update \
 && apt-get install --yes --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY services ./services
COPY db ./db
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

# The working copies, the one piece of state this application owns (D6). One
# volume, one directory per project, and the recovery when it is lost is a
# re-clone — see `deploy/recovery.md`.
VOLUME ["/data/worktrees"]

EXPOSE 8000

# Serve. Nothing else: the release step ran before this container started.
CMD ["python", "-m", "cybercanon.api"]
