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

# Vite env vars must be present *during the build* — Vite hard-codes them
# into the bundle at compile time. Inside a Dockerfile, env vars are only
# visible to RUN steps if they're declared as ARG and exported as ENV.
# Railway passes service variables in as build args automatically; without
# these ARG declarations they'd be silently dropped and the bundle would
# have empty Auth0/API values (manifesting as a broken sign-in page).
ARG VITE_AUTH0_DOMAIN
ARG VITE_AUTH0_CLIENT_ID
ARG VITE_AUTH0_AUDIENCE
ARG VITE_API_BASE
ARG VITE_TWILIO_NUMBER
ARG VITE_SMS_BANNER
ENV VITE_AUTH0_DOMAIN=${VITE_AUTH0_DOMAIN}
ENV VITE_AUTH0_CLIENT_ID=${VITE_AUTH0_CLIENT_ID}
ENV VITE_AUTH0_AUDIENCE=${VITE_AUTH0_AUDIENCE}
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_TWILIO_NUMBER=${VITE_TWILIO_NUMBER}
ENV VITE_SMS_BANNER=${VITE_SMS_BANNER}

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
# -l tcp://0.0.0.0:$PORT explicitly binds to all interfaces. Without
#      0.0.0.0, `serve` can default to localhost-only which Railway can't
#      route to from outside the container → 502.
# exec replaces the shell with serve so SIGTERM reaches it cleanly.
CMD ["sh", "-c", "exec serve -s dist -l tcp://0.0.0.0:${PORT:-3000}"]
