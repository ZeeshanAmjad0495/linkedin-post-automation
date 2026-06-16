#!/usr/bin/env bash
# Activate the venv (if present) and run one posting cycle.
# Used by launchd and for manual runs.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

exec python -m src.bot "$@"
