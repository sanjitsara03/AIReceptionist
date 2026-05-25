# AI Receptionist backend — production container image.
# Built by Railway on every push from GitHub.

FROM python:3.12-slim

# Pull the `uv` binary from its official image. Avoids `pip install uv` and
# the slow Python-level bootstrap.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests FIRST so Docker can cache the install layer.
# A code change won't bust this cache; only a pyproject/uv.lock change will.
COPY pyproject.toml uv.lock ./

# Install production deps only. --frozen makes the build fail if uv.lock and
# pyproject.toml have drifted, which guarantees prod uses exactly the versions
# the lockfile pins (same as local dev).
RUN uv sync --frozen --no-dev

# Application code + Alembic migration scripts.
COPY app/ ./app/
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Railway injects $PORT and routes external traffic to it. Bind 0.0.0.0 so
# connections from outside the container reach uvicorn.
#
# JSON array form + `exec` inside sh: silences the JSONArgsRecommended lint
# AND ensures uvicorn (not sh) is the process that receives SIGTERM, so the
# container shuts down gracefully on every Railway deploy.
CMD ["sh", "-c", "exec uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
