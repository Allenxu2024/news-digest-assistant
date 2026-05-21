#!/bin/bash
# Shell wrapper to execute the fetcher script with virtual environment dependencies.
# This script is suitable for cron schedules.

# Get current script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Write execution logs to fetcher.log
LOG_FILE="$DIR/fetcher.log"
echo "=== Start Fetcher Run: $(date) ===" >> "$LOG_FILE"

# Activate virtual environment
if [ -f "$DIR/.venv/bin/activate" ]; then
    source "$DIR/.venv/bin/activate" >> "$LOG_FILE" 2>&1
    python3 "$DIR/fetcher.py" >> "$LOG_FILE" 2>&1
    DEACTIVATE_STATUS=$?
    echo "Fetcher run finished with exit code: $DEACTIVATE_STATUS" >> "$LOG_FILE"
else
    echo "[Error] Virtual environment .venv not found. Run start_dashboard.sh first." >> "$LOG_FILE"
fi

echo "=== End Fetcher Run: $(date) ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
