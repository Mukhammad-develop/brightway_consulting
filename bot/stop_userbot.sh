#!/bin/bash
# Stop the Telegram userbot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/userbot.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "Userbot is not running (no PID file found)"
    exit 0
fi

PID=$(cat "$PIDFILE")

if ps -p $PID > /dev/null 2>&1; then
    echo "Stopping userbot (PID: $PID)..."
    kill $PID
    sleep 2
    
    # Force kill if still running
    if ps -p $PID > /dev/null 2>&1; then
        echo "Force killing userbot..."
        kill -9 $PID
    fi
    
    rm "$PIDFILE"
    echo "Userbot stopped"
else
    echo "Userbot process not found (PID: $PID)"
    rm "$PIDFILE"
fi
