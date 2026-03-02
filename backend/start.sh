#!/usr/bin/env bash
set -euo pipefail

# Always run from the directory this script lives in (backend/)
cd "$(dirname "$0")"

# Install dependencies (Railway may or may not run a separate build step)
pip install -r requirements.txt

# Start the FastAPI app with Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

