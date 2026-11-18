#!/usr/bin/env bash
# Launch OBD Pro desktop (creates the virtualenv on first run).
cd "$(dirname "$(readlink -f "$0")")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python run.py "$@"
