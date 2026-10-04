# Use official lightweight Python runtime with Playwright dependencies
FROM python:3.11-slim

# Install system dependencies for Chromium & Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libasound2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

# Copy application source
COPY . .

# Expose Web UI port
EXPOSE 8080

ENV HEADLESS=true
ENV PYTHONUNBUFFERED=1

# Default: Start Web UI Launchpad
CMD ["python", "run.py", "--ui", "--port", "8080"]
