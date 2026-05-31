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
COPY section_gateway ./section_gateway

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
    SECTION_ENV=production \
    SECTION_HOST=0.0.0.0 \
    SECTION_PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home /home/section --create-home section

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=section:section section_gateway ./section_gateway
COPY --chown=section:section migrations ./migrations
COPY --chown=section:section alembic ./alembic
COPY --chown=section:section alembic.ini ./alembic.ini
COPY --chown=section:section pyproject.toml README.md ./
COPY --chown=section:section docker-entrypoint.sh /usr/local/bin/section-entrypoint
RUN chmod +x /usr/local/bin/section-entrypoint

# When SECTION_AUTO_MIGRATE=0, the entrypoint skips `alembic upgrade head`.
ENV SECTION_AUTO_MIGRATE=1

USER section
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD python -c "import urllib.request,sys;urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/section-entrypoint"]
CMD ["python", "-m", "section_gateway.main"]
