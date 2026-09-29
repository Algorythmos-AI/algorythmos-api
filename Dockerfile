# Override this at build time if Docker Hub TLS is flaky:
#   --build-arg PY_BASE=mirror.gcr.io/library/python:3.12-slim
ARG PY_BASE=python:3.12-slim

############################
# Builder
############################
FROM ${PY_BASE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# minimal toolchain
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy only what we need to resolve and install
COPY requirements.txt pyproject.toml README.md /app/
COPY app.py config.py database.py models_api_key.py models_user.py /app/
COPY alembic.ini /app/alembic.ini
COPY app /app/app
COPY core /app/core
COPY document_processing /app/document_processing
COPY vendor_libs /app/vendor_libs
COPY alembic /app/alembic
COPY pdf_usage_extractor /app/pdf_usage_extractor

# create venv and install deps with pip (simpler than uv inside Docker)
RUN python -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN pip install --upgrade pip wheel
# Pinned runtime dependencies first (the same file Vercel installs), then the
# package itself without re-resolving them, so the image matches production.
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --no-deps .

############################
# Runtime
############################
FROM ${PY_BASE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# runtime libs; keep this lean
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 libjpeg62-turbo zlib1g \
    poppler-utils ghostscript ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# bring the environment and app code
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# non-root
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# healthcheck (no heredoc)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD ["python","-c","import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/alg/healthz').getcode()==200 else 1)"]

# Canonical runtime: top-level app.py exports the deployable ASGI app.
# Run `alembic upgrade head` before starting this container in each environment.
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8080"]
