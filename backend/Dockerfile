# ── Stage 1: build Python deps ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only PyTorch to save gigabytes of space since we don't have a GPU
RUN pip install --no-cache-dir --prefix=/install \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --prefix=/install \
        -r requirements.txt \
        --extra-index-url https://download.pytorch.org/whl/cpu

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libgles2 \
        libegl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

WORKDIR /app

COPY . .

RUN mkdir -p storage/jobs

# Non-root user for security
RUN useradd -r -u 1001 pdve && chown -R pdve /app
USER pdve

EXPOSE 8000

# Default: run the API server.
# Override CMD to run the worker: ["python", "worker/worker.py"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--log-level", "info"]
