# Synpo GTM Automation - backend + worker image.
#
# Runs as a non-root user, contains no secrets (inject via env / read-only
# volume), and defaults to the API. The worker reuses this image with a
# different command (see docker-compose.yml).

FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root runtime user.
RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --create-home app

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Application code only (no secrets, no venv, no tests).
COPY backend/app ./backend/app

USER app

WORKDIR /app/backend

EXPOSE 8000

# Default command: the API. Compose overrides this for the worker.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
