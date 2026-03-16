#!/bin/sh
# Celery Beat entrypoint: ensure /app/data is writable by appuser before starting.
# Required when a Docker volume is mounted at /app/data (root-owned by default).
set -e
mkdir -p /app/data
chown -R appuser:appuser /app/data
# Verify appuser can write (fail fast if something is wrong)
if ! gosu appuser touch /app/data/.write-test 2>/dev/null; then
  echo "[Beat] ERROR: /app/data is not writable by appuser" >&2
  exit 1
fi
rm -f /app/data/.write-test
echo "[Beat] /app/data permissions OK, starting Celery Beat..."
exec gosu appuser "$@"
