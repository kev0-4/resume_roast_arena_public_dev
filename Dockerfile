# Shared image for the FastAPI backend and every worker except the
# renderer (extraction, normalization, anonymization, scoring, llm) --
# they all run from the same root requirements.txt in one environment
# (see requirements.txt's own comment), so one image with a different
# `command` per Container App is simpler than seven near-identical
# images. The renderer gets its own image (Dockerfile.renderer) because
# it needs a real browser -- everything here stays intentionally small.
FROM python:3.12-slim

WORKDIR /app

# System deps for building any wheel-less packages (most of
# requirements.txt has prebuilt wheels for linux/amd64, but keeping gcc
# around avoids a silent failure the day one doesn't).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY workers/ workers/

# No default CMD -- each Container App (backend API, or one of the five
# lightweight workers) supplies its own start command at deploy time,
# e.g. `uvicorn app:app --app-dir backend --host 0.0.0.0 --port 8000` or
# `python -m workers.scoring.main`.
