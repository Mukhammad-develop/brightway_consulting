#!/bin/bash
# Start the Telegram bot in the background

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/bot.pid"
LOGFILE="$PROJECT_DIR/bot.log"

cd "$PROJECT_DIR"

# Check if already running
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "Bot is already running (PID: $PID)"
        exit 1
    else
        rm "$PIDFILE"
    fi
fi

# Activate virtual environment if exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Start bot in background
echo "Starting Telegram bot..."
nohup python manage.py run_bot >> "$LOGFILE" 2>&1 &

# Save PID
echo $! > "$PIDFILE"
echo "Bot started with PID: $(cat $PIDFILE)"
echo "Logs: $LOGFILE"
