# The API, for the end-to-end stack only. `add-coolify-deployment` owns the
# image that is built once and promoted; this one exists so the browser talks to
# a real service instead of a fixture, and it is deliberately the simplest thing
# that does that: the locked environment, the source, and the entry point the
# `just api` recipe uses.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install --yes --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY services ./services
COPY db ./db
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000

# Migrations are a release step (openspec/project.md), and the index is
# droppable by definition, so a failed migration is recoverable by rebuilding.
CMD ["sh", "-c", "python -m cybercanon.api.migrate && python -m cybercanon.api --host 0.0.0.0 --port 8000"]
