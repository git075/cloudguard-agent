# Production Dockerfile for CloudGuard FinOps Services
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir celery redis flower asyncpg email-validator greenlet bcrypt passlib PyJWT

# Copy application source code
COPY . /app

# Create non-root user for least-privilege container security
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Default command starts FastAPI application server
CMD ["uvicorn", "src.ui.dashboard_api:app", "--host", "0.0.0.0", "--port", "8000"]
