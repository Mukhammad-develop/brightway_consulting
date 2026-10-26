#!/bin/bash
# Start the consultant control bot in the background

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/control_bot.pid"
LOGFILE="$PROJECT_DIR/control_bot.log"

cd "$PROJECT_DIR"

# Check if already running
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "Control bot is already running (PID: $PID)"
        exit 1
    else
        rm "$PIDFILE"
    fi
fi

# Activate virtual environment if exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Start control bot in background
echo "Starting consultant control bot..."
nohup python manage.py run_control_bot >> "$LOGFILE" 2>&1 &

# Save PID
echo $! > "$PIDFILE"
echo "Control bot started with PID: $(cat $PIDFILE)"
echo "Logs: $LOGFILE"
