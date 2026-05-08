# ── Stage 1: build Python deps ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CUDA-enabled PyTorch first, then the rest of the requirements.
# The --extra-index-url makes pip find the CUDA wheels.
RUN pip install --no-cache-dir --prefix=/install \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu121 \
    && pip install --no-cache-dir --prefix=/install \
        -r requirements.txt \
        --extra-index-url https://download.pytorch.org/whl/cu121

# ── Stage 2: CUDA runtime ────────────────────────────────────────────────────
# Use NVIDIA CUDA base so the GPU is accessible inside the container.
# CUDA 12.1 + cuDNN 8 matches PyTorch 2.x wheels.
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04 AS runtime

# Install Python 3.11 on the CUDA base (Ubuntu 22.04 has 3.10 by default)
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-distutils python3-pip \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        curl \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
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
