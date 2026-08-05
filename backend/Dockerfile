# Backend Dockerfile for Beets Web Manager
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    libffi-dev \
    libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# librosa powers the beets `autobpm` plugin (BPM analysis). Deliberately baked
# into the image (adds ~490 MB of site-packages: llvmlite/scipy/sklearn/numpy)
# so enabling `plugins: [autobpm]` in a library config never hits a
# ModuleNotFoundError at runtime. Own layer: it changes far less often than
# requirements.txt and is expensive to rebuild. resampy is a hard requirement:
# autobpm loads audio with res_type="kaiser_fast", which librosa only supports
# via resampy — without it every track fails with "No module named 'resampy'".
RUN pip install "librosa>=0.10,<0.11" "resampy>=0.4"

# Copy application code
COPY . .

RUN chmod +x entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
