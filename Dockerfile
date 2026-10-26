# Stage 1: Builder stage
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies if needed for compiling packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Upgrade pip, setuptools, wheel and build wheels
RUN pip install --no-cache-dir --upgrade pip "setuptools>=78.1.1" wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt

# Stage 2: Final runtime stage
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Run apt-get upgrade and remove apt lists in the same RUN layer
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Install packages from pre-built wheels with no build tools in final image
COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip "setuptools>=78.1.1" && \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

# Create dedicated non-root user (appuser, UID 10001)
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/sh -m appuser

# Copy application files and set ownership
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 5000

# Healthcheck calling /health using standard library urllib
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["gunicorn", "-w", "2", "-t", "120", "-b", "0.0.0.0:5000", "app:app"]
