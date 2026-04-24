FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.14-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Install uv
COPY --from=uv /uv /uvx /bin/

# Install application dependencies
COPY pyproject.toml uv.lock ./
COPY app ./app
RUN uv sync --frozen --no-dev

FROM python:3.14-slim AS runtime

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends whois && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY pyproject.toml uv.lock ./

# Expose port
EXPOSE 8000

# Run application
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
