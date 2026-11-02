#!/usr/bin/env bash
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
printf '%s' 'Clone public source repositories? Existing folders are skipped. [y/N] '
IFS= read -r answer
case "$answer" in y|Y|yes|YES) ;; *) exit 0 ;; esac
for python in python3 python; do
  if command -v "$python" >/dev/null 2>&1 && "$python" -c 'import sys; raise SystemExit(sys.version_info < (3,10))' 2>/dev/null; then
    exec "$python" clone_repositories.py "$@"
  fi
done
printf '%s\n' 'Python 3.10+ is required. No software was installed.' >&2
exit 1
