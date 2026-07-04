# ── Stage 1: build dependencies ───────────────────────────────────────────────
# Use the official Playwright Python image — includes Chromium + all system libs
# needed for headless browser crawling without any extra apt-get installs.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
# (required for Cloud Run log streaming)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install Python dependencies first (layer-cached separately from source code)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# ── Runtime config ─────────────────────────────────────────────────────────────
# Cloud Run injects PORT env var; default to 8000 for local docker run.
ENV PORT=8000

# Cloud Run requires the container to listen on $PORT, not a hardcoded port.
# Use shell form so $PORT is evaluated at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
