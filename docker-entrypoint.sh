#!/bin/sh
# Wires persistent storage at $PERSIST_DIR into the app at /app via symlinks.
# This avoids the Docker bind-mount pitfall of creating non-existent file
# paths as directories — we keep db/secret/etc inside one mountable directory.
set -eu

PERSIST="${PERSIST_DIR:-/persist}"

# Ensure all expected paths exist on the persistent volume
mkdir -p \
  "$PERSIST/data" \
  "$PERSIST/data/flowchart_versions" \
  "$PERSIST/uploads"

# data.db is a file — create empty placeholder so bind-mount doesn't make it a directory
[ -e "$PERSIST/data.db" ] || : > "$PERSIST/data.db"
# DO NOT pre-create secret_key as an empty file — Flask treats empty SECRET_KEY as missing
# and refuses to use sessions. Let app._load_or_create_secret_key() generate it on first run.
# (The dangling symlink below is fine: open(..., "w") creates the target file when written.)

# Replace any baked-in paths in /app with symlinks to the persistent volume
# (rm -rf is safe because these only contain runtime state, not source code)
rm -rf /app/data /app/uploads /app/data.db /app/.secret_key
ln -sfn "$PERSIST/data"       /app/data
ln -sfn "$PERSIST/uploads"    /app/uploads
ln -sfn "$PERSIST/data.db"    /app/data.db
ln -sfn "$PERSIST/secret_key" /app/.secret_key

# Print effective config for log visibility
echo "[entrypoint] PERSIST_DIR=$PERSIST"
echo "[entrypoint] SERVER_MODE=${SERVER_MODE:-dev}  PORT=${PORT:-5000}"

# Hand off to CMD (python app.py)
exec "$@"
