#!/bin/sh
set -eu
if [ "${CONFIGURATION:-Debug}" != "Release" ]; then exit 0; fi
info="$PROJECT_DIR/App/public/build-info.json"
development=$(/usr/bin/plutil -extract development raw -o - "$info")
backend=$(/usr/bin/plutil -extract backend raw -o - "$info")
if [ "$development" != "false" ]; then
    echo 'error: Run npm run ios -- --url https://your-backend.example before archiving.'
    exit 1
fi
case "$backend" in
    https://*) ;;
    *) echo 'error: Release builds require an HTTPS backend.'; exit 1 ;;
esac
