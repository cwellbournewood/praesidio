#!/bin/sh
# Section gateway container entrypoint.
#
# Runs `alembic upgrade head` against the configured database (resolved from
# SECTION_DATABASE_URL or DATABASE_URL) before exec'ing the application,
# unless SECTION_AUTO_MIGRATE=0 (e.g. when a Helm pre-upgrade Job already
# applied migrations, or when running ad-hoc commands locally).

set -eu

if [ "${SECTION_AUTO_MIGRATE:-1}" = "1" ]; then
    echo "[entrypoint] running alembic upgrade head"
    cd /app
    # Alembic resolves the URL from SECTION_DATABASE_URL / DATABASE_URL via
    # alembic/env.py. We retry briefly so a slow Postgres start doesn't kill
    # the gateway on first boot.
    attempt=0
    until alembic upgrade head; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 30 ]; then
            echo "[entrypoint] alembic upgrade head failed after $attempt attempts" >&2
            exit 1
        fi
        echo "[entrypoint] alembic not ready yet (attempt $attempt), retrying in 2s"
        sleep 2
    done
    echo "[entrypoint] migrations complete"
else
    echo "[entrypoint] SECTION_AUTO_MIGRATE=0, skipping alembic"
fi

exec "$@"
