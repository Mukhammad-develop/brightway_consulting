#!/bin/bash
# Start the Telegram userbot in the background

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/userbot.pid"
LOGFILE="$PROJECT_DIR/userbot.log"

cd "$PROJECT_DIR"

# Check if already running
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "Userbot is already running (PID: $PID)"
        exit 1
    else
        rm "$PIDFILE"
    fi
fi

# Activate virtual environment if exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Start userbot in background
echo "Starting Telegram userbot..."
nohup python manage.py run_userbot >> "$LOGFILE" 2>&1 &

# Save PID
echo $! > "$PIDFILE"
echo "Userbot started with PID: $(cat $PIDFILE)"
echo "Logs: $LOGFILE"
