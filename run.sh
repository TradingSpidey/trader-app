#!/usr/bin/env bash
# Start the app on 0.0.0.0:${PORT:-8080}. Set SEC_USER_AGENT="Your Name you@example.com" for SEC data.
cd "$(dirname "$0")"
PY=${PYTHON:-.venv/bin/python}
[ -x "$PY" ] || PY=python3
# One worker: the /desk paper book lives in this process. More workers would each keep a separate book.
exec "$PY" -m gunicorn -w ${WORKERS:-1} --threads 4 -t 300 -b ${HOST:-0.0.0.0}:${PORT:-8080} app:app
