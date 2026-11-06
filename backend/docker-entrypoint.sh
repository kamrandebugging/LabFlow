#!/bin/sh
# Shared by the api, worker and beat containers. Only the api role sets
# RUN_MIGRATIONS=1 so migrations are applied exactly once per deploy.
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "Applying shared-schema migrations..."
    python manage.py migrate_schemas --shared --noinput
fi

exec "$@"
