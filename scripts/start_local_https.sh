#!/bin/sh
# TLS only on loopback. Keep FastAPI in a separate terminal on 127.0.0.1:8000.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CASCADE_PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CASCADE_LOCAL_TLS_DIR="$CASCADE_PROJECT_DIR/.local-https"
export CASCADE_LOCAL_TLS_DIR
if ! command -v caddy >/dev/null 2>&1; then
  echo 'Install Caddy first: brew install caddy' >&2
  exit 1
fi
if [ ! -f "$CASCADE_LOCAL_TLS_DIR/localhost.pem" ] || [ ! -f "$CASCADE_LOCAL_TLS_DIR/localhost-key.pem" ]; then
  echo 'Generate the trusted localhost certificate first; see docs/local-https.md.' >&2
  exit 1
fi
exec caddy run --config "$SCRIPT_DIR/local_https.Caddyfile" --adapter caddyfile
