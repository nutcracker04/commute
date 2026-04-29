#!/usr/bin/env bash
# Sync env vars + secrets to Cloudflare Workers and deploy.
#
# Usage:
#   ./scripts/sync.sh              # deploy code + vars, skip secrets if secrets.json missing
#   ./scripts/sync.sh --secrets    # also bulk-push secrets from secrets.json
#   ./scripts/sync.sh --secrets-only  # push secrets only, no code deploy
#
# secrets.json is gitignored. Copy secrets.example.json → secrets.json and fill in values.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_FILE="$ROOT/secrets.json"

push_secrets=false
secrets_only=false

for arg in "$@"; do
  case "$arg" in
    --secrets) push_secrets=true ;;
    --secrets-only) push_secrets=true; secrets_only=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

if $push_secrets; then
  if [[ ! -f "$SECRETS_FILE" ]]; then
    echo "ERROR: secrets.json not found at $SECRETS_FILE"
    echo "       Copy secrets.example.json → secrets.json and fill in your values."
    exit 1
  fi
  echo "→ Pushing secrets from secrets.json …"
  npx wrangler secret bulk "$SECRETS_FILE"
  echo "✓ Secrets updated."
fi

if ! $secrets_only; then
  echo "→ Deploying worker (code + vars from wrangler.toml) …"
  npx wrangler deploy
  echo "✓ Deploy complete."
fi
