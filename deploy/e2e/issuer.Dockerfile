# CyberdyneAuth, for the end-to-end stack only.
#
# `tools/canon_issuer` is the issuer the port-conformance, integration and BDD
# layers already mint against in process; `canon_issuer.service` puts it behind
# a socket so a real browser can complete an authorization-code exchange. The
# compose file used to name an address on the api that nothing served, so no
# credential could ever verify and no signed-in screen could ever be asserted.
#
# The first six instructions are byte-identical to `api.Dockerfile` so that
# BuildKit shares its layers: the issuer costs a `COPY` on a warm cache rather
# than a second `uv sync`. It is deliberately the same locked environment —
# an issuer resolving its own `joserfc` would be signing with a library the
# service was never checked against.
#
# This image is never promoted and never deployed. `deploy/coolify.yaml` holds
# the four hosted applications and `just deploy-check` refuses a fifth.
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

COPY tools/canon_issuer ./tools/canon_issuer

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONPATH=/app/tools
ENV PYTHONUNBUFFERED=1
EXPOSE 9000

CMD ["python", "-m", "canon_issuer.service"]
