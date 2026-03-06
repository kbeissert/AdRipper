#!/bin/bash

# AdRipper Cron Runner
# Usage: ./run.sh [customer_param]
# Example: ./run.sh --all
# Example: ./run.sh --customer cerdo-fachwerkhaus

# Basis-Verzeichnis des Projekts (absolut)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_FILE="$PROJECT_DIR/logs/cron.log"

echo "=== AdRipper Cron Start: $(date) ===" >> "$LOG_FILE"

# Virtual Environment aktivieren
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "FEHLER: Virtual Environment nicht gefunden!" >> "$LOG_FILE"
    exit 1
fi

# Argumente prüfen (Default --all wenn leer)
ARGS="$@"
if [ -z "$ARGS" ]; then
    ARGS="--all"
fi

# Python Script ausführen
python "$PROJECT_DIR/src/adripper.py" $ARGS >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "=== AdRipper Erfolg: $(date) ===" >> "$LOG_FILE"
else
    echo "=== AdRipper FEHLER (Code $EXIT_CODE): $(date) ===" >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"
exit $EXIT_CODE
