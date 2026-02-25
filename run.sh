#!/bin/bash
# Launcher untuk WordPress Video Downloader
# Jalankan: ./run.sh
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/venv/bin/python" "$DIR/downloader.py" "$@"
