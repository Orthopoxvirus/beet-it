#!/bin/sh
set -e

# Pass through a provided command (compose `command:` for celery worker/beat).
# Only the default path (no args, i.e. the `backend` service) runs migrations
# + uvicorn, which also avoids worker/beat/backend racing `alembic upgrade head`.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --timeout-keep-alive=600 --timeout-graceful-shutdown=30
