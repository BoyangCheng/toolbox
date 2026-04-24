#!/usr/bin/env bash
cd "$(dirname "$0")"
# Prefer python3.12 / 3.11 if available; fall back to python3
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
if [ ! -d ".venv" ]; then
  "$PY" -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
.venv/bin/python app.py
