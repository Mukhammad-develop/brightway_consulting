#!/bin/bash
# Check status of bot and userbot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Brightway Consulting Bot Status ==="
echo ""

# Check main bot
BOT_PID_FILE="$PROJECT_DIR/bot.pid"
if [ -f "$BOT_PID_FILE" ]; then
    BOT_PID=$(cat "$BOT_PID_FILE")
    if ps -p $BOT_PID > /dev/null 2>&1; then
        echo "✅ Telegram Bot: RUNNING (PID: $BOT_PID)"
    else
        echo "❌ Telegram Bot: STOPPED (stale PID file)"
    fi
else
    echo "❌ Telegram Bot: STOPPED"
fi

# Check userbot
USERBOT_PID_FILE="$PROJECT_DIR/userbot.pid"
if [ -f "$USERBOT_PID_FILE" ]; then
    USERBOT_PID=$(cat "$USERBOT_PID_FILE")
    if ps -p $USERBOT_PID > /dev/null 2>&1; then
        echo "✅ Telegram Userbot: RUNNING (PID: $USERBOT_PID)"
    else
        echo "❌ Telegram Userbot: STOPPED (stale PID file)"
    fi
else
    echo "❌ Telegram Userbot: STOPPED"
fi

echo ""
echo "Log files:"
echo "  Bot: $PROJECT_DIR/bot.log"
echo "  Userbot: $PROJECT_DIR/userbot.log"
