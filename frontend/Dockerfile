# AI Receptionist frontend — production container image.
# Multi-stage: stage 1 builds the Vite bundle, stage 2 serves it with `serve`.

# -------- Stage 1: build the Vite bundle --------
FROM node:20-alpine AS build

WORKDIR /app

# Copy dependency manifests first so Docker caches the install layer
# when only source code changes.
COPY package.json package-lock.json ./
RUN npm ci

# Now copy the rest of the source.
COPY . .

# `npm run build` reads VITE_* env vars at this point and bakes them into
# the bundle. Railway passes service env vars through to the build by default.
RUN npm run build


# -------- Stage 2: serve the dist/ folder --------
# Fresh small image — no build tooling, no source code, no node_modules
# (except `serve`).
FROM node:20-alpine

WORKDIR /app

# `serve` is a tiny static-file server with SPA fallback support.
RUN npm install -g serve

# Bring over ONLY the built assets from stage 1.
COPY --from=build /app/dist ./dist

# Railway sets $PORT. Defaults to 3000 for local docker run.
# -s = SPA mode: any URL that doesn't match a file returns index.html
#      (so React Router handles client-side routes on refresh)
# -l = listen on this port
# exec replaces the shell with serve so SIGTERM reaches it cleanly.
CMD ["sh", "-c", "exec serve -s dist -l ${PORT:-3000}"]
