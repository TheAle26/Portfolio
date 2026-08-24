#!/bin/sh

set -eu

if [ "${BACKGROUND_PROCESSES_ENABLED:-false}" != "true" ]; then
    echo "Background process disabled; set BACKGROUND_PROCESSES_ENABLED=true after the final restore."
    exec python -c "import time; time.sleep(10**9)"
fi

exec "$@"
