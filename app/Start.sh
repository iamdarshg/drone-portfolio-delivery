#!/usr/bin/env bash
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
for python in python3 python; do
  if command -v "$python" >/dev/null 2>&1 && "$python" -c 'import sys; raise SystemExit(sys.version_info < (3,10))' 2>/dev/null; then
    exec "$python" serve.py 0 --open
  fi
done
printf '%s\n' 'Python 3.10+ is required. Install it manually, then run this launcher again.' >&2
exit 1
