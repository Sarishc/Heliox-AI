# Multi-stage Dockerfile for Heliox-AI Backend

FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app


# Builder stage - install dependencies
FROM base as builder

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy production requirements (excludes pytest, black, ruff, mypy)
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt


# Runtime stage (minimal - no postgresql-client, app uses psycopg2 driver)
FROM base as runtime

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Create data directory for Celery Beat with proper permissions
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

# Copy application code and set ownership
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check (using Python stdlib - no external dependencies)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application (5 workers = CPU*2+1 for typical 2-core; override via UVICORN_WORKERS env)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "5"]

