# Docsmith GitHub Action image.
# The local embedding model (bge-small) is baked in at build time so the Action
# is fully self-contained and needs no embedding API key at runtime.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for git operations inside the Action.
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-download the local embedding model into the image layer.
# TODO(impl): warm the sentence-transformers cache for BAAI/bge-small-en-v1.5.

COPY . .

ENTRYPOINT ["python", "/app/docsmith.py", "--github-action"]
