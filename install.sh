#!/usr/bin/env bash
set -euo pipefail
script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$script_root/scripts/install.py" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$script_root/scripts/install.py" "$@"
else
  printf '%s\n' 'Python 3.10+ is required. Install Python and run this script again.' >&2
  exit 1
fi
