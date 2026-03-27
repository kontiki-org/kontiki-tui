FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (keep minimal). We install Poetry to match pyproject/poetry.lock.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

# Install dependencies first for better layer caching
COPY pyproject.toml poetry.lock README.md /app/
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main --no-root

# Copy application code
COPY kontiki_tui /app/kontiki_tui
COPY examples /app/examples

# Default command is intentionally not set; docker-compose selects the entrypoint.
