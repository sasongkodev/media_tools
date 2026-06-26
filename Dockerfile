# ═══════════════════════════════════════════
# Media Tools — Dockerfile
# Multi-stage build for Universal Video Downloader + Flask Web UI
# ═══════════════════════════════════════════

FROM python:3.12-slim AS base

# System dependencies: ffmpeg for video processing, 
# plus minimal tools for yt-dlp and playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create downloads directory
RUN mkdir -p /app/downloads

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DOWNLOAD_DIR=/app/downloads \
    PORT=5000 \
    FLASK_DEBUG=0

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Run the Flask app
CMD ["python", "app.py"]
