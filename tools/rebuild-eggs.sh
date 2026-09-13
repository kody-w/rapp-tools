#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [ "${1:-}" != "--check" ] || [ "$#" != 1 ]; then
  printf '%s\n' \
    "Retired eggs are immutable historical artifacts; rebuilding them is disabled." \
    "Use tools/rebuild-eggs.sh --check to verify published archive hashes." \
    "New RAPP/1 artifacts require the current canonical producer and a new release." >&2
  exit 2
fi
exec python3 "$HERE/verify_legacy_eggs.py"
