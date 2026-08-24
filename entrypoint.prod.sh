#!/bin/sh

set -eu

python manage.py collectstatic --noinput

# La base es un recurso separado en Coolify y puede tardar unos segundos más
# en quedar disponible después de reiniciar el servidor.
attempt=1
until python manage.py migrate --noinput; do
    if [ "$attempt" -ge 12 ]; then
        echo "Database did not become ready after $attempt attempts." >&2
        exit 1
    fi

    echo "Database not ready (attempt $attempt/12); retrying in 5 seconds..." >&2
    attempt=$((attempt + 1))
    sleep 5
done

exec python -m gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 2 mysiteFulbo.wsgi:application
