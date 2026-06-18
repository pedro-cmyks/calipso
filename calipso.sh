#!/usr/bin/env bash
# Lanzador de Calipso para Linux/Bazzite
# Uso: ./calipso.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [[ ! -d "$VENV" ]]; then
    echo "[calipso] Creando entorno virtual..."
    python3 -m venv "$VENV"
    source "$VENV/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet chromadb ollama playwright litellm fastapi "uvicorn[standard]" pyotp qrcode pillow
    playwright install chromium
fi

source "$VENV/bin/activate"
exec python "$SCRIPT_DIR/launch_calipso.py" "$@"
