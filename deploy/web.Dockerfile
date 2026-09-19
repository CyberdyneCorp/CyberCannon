# The web image: the SvelteKit application on its server runtime (D10).
#
# It runs with the node adapter rather than as a static bundle, because
# server-side rendering of authenticated pages and the sign-in callback both
# want a server — and because D10's readiness rule has to be *this process's*
# answer: the application never calls the API to decide whether it is ready, and
# a page whose data cannot be fetched renders an explicit unavailable state
# rather than an error.
#
# Built once and promoted, like the API image. `PUBLIC_` variables are read at
# runtime through `$env/dynamic/public`, so the address of the API is not baked
# in here and the same image serves pre-production and production.

FROM node:22-alpine AS build

WORKDIR /app
COPY apps/cybercanon/web/package.json apps/cybercanon/web/pnpm-lock.yaml apps/cybercanon/web/.npmrc ./
RUN corepack enable && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm install --frozen-lockfile
COPY apps/cybercanon/web ./
RUN COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/build ./build
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json

ENV HOST=0.0.0.0
ENV PORT=5173
ENV NODE_ENV=production
EXPOSE 5173

# The node adapter's server. It needs nothing else running to answer.
CMD ["node", "build"]
