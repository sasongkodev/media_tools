#!/bin/bash
# ═══════════════════════════════════════════
# Media Tools Launcher
# ═══════════════════════════════════════════
# Modes:
#   ./run.sh              → CLI interaktif (mode lama)
#   ./run.sh web          → Web UI di http://localhost:5000
#   ./run.sh -u URL       → Download satu URL via CLI
#   ./run.sh --help       → Bantuan CLI

DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$DIR/venv/bin/python"

if [ "$1" = "web" ]; then
    echo "🚀 Starting Media Tools Web UI..."
    shift
    "$PYTHON" "$DIR/app.py" "$@"
else
    "$PYTHON" "$DIR/downloader.py" "$@"
fi
