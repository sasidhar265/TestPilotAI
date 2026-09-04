#!/bin/sh
set -eu

# Render containers cannot reuse the developer workstation's interactive Codex login.
# Authenticate the installed CLI from the deployment secret when one is configured.
if [ -n "${OPENAI_API_KEY:-}" ]; then
    if ! printf '%s' "$OPENAI_API_KEY" | codex login --with-api-key >/dev/null; then
        echo "Warning: Codex CLI API-key authentication failed; other providers may still work." >&2
    fi
fi

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-10000}" \
    --proxy-headers \
    --no-server-header \
    --timeout-graceful-shutdown 30
