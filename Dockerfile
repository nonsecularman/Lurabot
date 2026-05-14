# ================================================================
#  AuraBot — Dockerfile
#  Multi-stage build for minimal production image
# ================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    libcairo2-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="AuraBot"
LABEL org.opencontainers.image.description="Production-grade Telegram multimedia bot"
LABEL org.opencontainers.image.version="1.0.0"

# System dependencies (FFmpeg, fonts, Cairo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libcairo2 \
    fonts-noto \
    fonts-noto-color-emoji \
    fontconfig \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Refresh font cache
RUN fc-cache -f -v

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application source
COPY . .

# Create logs and sessions directories
RUN mkdir -p logs sessions assets/fonts

# Non-root user for security
RUN useradd -m -u 1000 aurabot && chown -R aurabot:aurabot /app
USER aurabot

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080 9090

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "app.py"]
