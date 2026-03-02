#!/usr/bin/env bash
set -euo pipefail

# Always run from the directory this script lives in (frontend/)
cd "$(dirname "$0")"

# Install dependencies
npm install

# Build for production
npm run build

# Serve the built app (Vite preview listens on PORT for Railway)
exec npx vite preview --host 0.0.0.0 --port "${PORT:-4173}"
