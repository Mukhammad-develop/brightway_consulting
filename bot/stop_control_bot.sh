#!/bin/bash
# Stop the consultant control bot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/control_bot.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "Control bot is not running (no PID file found)"
    exit 0
fi

PID=$(cat "$PIDFILE")

if ps -p $PID > /dev/null 2>&1; then
    echo "Stopping control bot (PID: $PID)..."
    kill $PID
    sleep 2

    # Force kill if still running
    if ps -p $PID > /dev/null 2>&1; then
        echo "Force killing control bot..."
        kill -9 $PID
    fi

    rm "$PIDFILE"
    echo "Control bot stopped"
else
    echo "Control bot process not found (PID: $PID)"
    rm "$PIDFILE"
fi
