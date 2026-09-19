# The SvelteKit application, built the way `just web-build` builds it and served
# by the node adapter. The two @cyberdynecorp packages are installed from GitHub
# Packages when NPM_TOKEN is provided as a build secret; without it the build
# uses the application's own components, which is the state task 1.2 changes.
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
EXPOSE 5173
CMD ["node", "build"]
