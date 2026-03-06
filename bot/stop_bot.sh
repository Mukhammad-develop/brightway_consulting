#!/bin/bash
# Stop the Telegram bot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/bot.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "Bot is not running (no PID file found)"
    exit 0
fi

PID=$(cat "$PIDFILE")

if ps -p $PID > /dev/null 2>&1; then
    echo "Stopping bot (PID: $PID)..."
    kill $PID
    sleep 2
    
    # Force kill if still running
    if ps -p $PID > /dev/null 2>&1; then
        echo "Force killing bot..."
        kill -9 $PID
    fi
    
    rm "$PIDFILE"
    echo "Bot stopped"
else
    echo "Bot process not found (PID: $PID)"
    rm "$PIDFILE"
fi
