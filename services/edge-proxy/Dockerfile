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

RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    cp /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY section_edge_proxy ./section_edge_proxy

RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache .

# ---------- Runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    SECTION_EDGE_LISTEN_HOST=0.0.0.0 \
    SECTION_EDGE_LISTEN_PORT=8888 \
    SECTION_EDGE_CA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10002 --home /home/section --create-home section \
    && mkdir -p /data \
    && chown section:section /data

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=section:section section_edge_proxy ./section_edge_proxy
COPY --chown=section:section pyproject.toml README.md ./

USER section
VOLUME ["/data"]
EXPOSE 8888

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD python -c "from section_edge_proxy.status import read_status, default_status_path; import sys; s=read_status(default_status_path()); sys.exit(0 if s else 1)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["section-edge-proxy", "start"]
