# syntax=docker/dockerfile:1.7

# ---------- Builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    cp /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY praesidio_gateway ./praesidio_gateway

# Create venv with deps
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache .

# Download spaCy model
RUN . /opt/venv/bin/activate && \
    python -m spacy download en_core_web_sm

# ---------- Runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PRAESIDIO_ENV=production \
    PRAESIDIO_HOST=0.0.0.0 \
    PRAESIDIO_PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home /home/praesidio --create-home praesidio

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=praesidio:praesidio praesidio_gateway ./praesidio_gateway
COPY --chown=praesidio:praesidio migrations ./migrations
COPY --chown=praesidio:praesidio alembic ./alembic
COPY --chown=praesidio:praesidio alembic.ini ./alembic.ini
COPY --chown=praesidio:praesidio pyproject.toml README.md ./
COPY --chown=praesidio:praesidio docker-entrypoint.sh /usr/local/bin/praesidio-entrypoint
RUN chmod +x /usr/local/bin/praesidio-entrypoint

# When PRAESIDIO_AUTO_MIGRATE=0, the entrypoint skips `alembic upgrade head`.
ENV PRAESIDIO_AUTO_MIGRATE=1

USER praesidio
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD python -c "import urllib.request,sys;urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/praesidio-entrypoint"]
CMD ["python", "-m", "praesidio_gateway.main"]
