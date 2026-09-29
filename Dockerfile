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
# Examples use the Kontiki 2.0.0 API (max_attempts, add_context,
# activity_tracker). Overlay 2.0.0 from the 2.0.0_alpha branch LAST —
# kontiki-monitor requires kontiki (a pre-release does not satisfy
# a plain ">=1.12.0"), so an earlier install would be downgraded to 1.16.
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main --no-root \
    && pip install --no-cache-dir "kontiki-monitor>=1.0.0,<2.0.0" \
    && pip install --no-cache-dir --no-deps "https://github.com/kontiki-org/kontiki/archive/refs/heads/2.0.0_alpha.tar.gz"

# Copy application code
COPY kontiki_tui /app/kontiki_tui
COPY examples /app/examples

# Default command is intentionally not set; docker-compose selects the entrypoint.
