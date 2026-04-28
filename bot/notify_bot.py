#!/usr/bin/env python3
"""
Brightway Consulting – Notification Bot for Consultants.

A lightweight Telegram bot that:
  1. Accepts 5-digit pairing codes from consultants to link their
     Telegram account to their AdminUser profile.
  2. Provides a send_notification() helper that other parts of the system
     can call to push messages to linked consultants.

Usage:
    python bot/notify_bot.py

Requires NOTIFY_BOT_TOKEN in .env (separate from the main BOT_TOKEN).
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# ── Bootstrap Django ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bwc.settings')

import django
django.setup()

import telebot
from django.conf import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / 'notify_bot.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Bot init ─────────────────────────────────────────────────────────────────
NOTIFY_BOT_TOKEN = getattr(settings, 'NOTIFY_BOT_TOKEN', None) or os.getenv('NOTIFY_BOT_TOKEN')

if not NOTIFY_BOT_TOKEN:
    logger.error('NOTIFY_BOT_TOKEN not configured – notification bot will not start.')
    sys.exit(1)

bot = telebot.TeleBot(NOTIFY_BOT_TOKEN)


# ── /start ───────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(
        message.chat.id,
        '👋 Welcome to Brightway Notifications!\n\n'
        'To connect your account, go to your **Profile** page in the admin panel, '
        'click **Generate Code**, then send the 5-digit code here.\n\n'
        'Example: `12345`',
        parse_mode='Markdown',
    )


# ── Code verification ────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text and m.text.strip().isdigit() and len(m.text.strip()) == 5)
def handle_code(message):
    from core.models import AdminUser

    code = message.text.strip()
    chat_id = message.chat.id
    now = datetime.now()

    try:
        admin = AdminUser.objects.get(notification_code=code)
    except AdminUser.DoesNotExist:
        bot.send_message(chat_id, '❌ Invalid code. Please check and try again.')
        return

    # Check expiry
    if admin.notification_code_expires and admin.notification_code_expires < now:
        bot.send_message(chat_id, '⏰ This code has expired. Please generate a new one from your profile.')
        admin.notification_code = None
        admin.notification_code_expires = None
        admin.save(update_fields=['notification_code', 'notification_code_expires'])
        return

    # Link the account
    admin.telegram_chat_id = chat_id
    admin.notification_code = None
    admin.notification_code_expires = None
    admin.save(update_fields=['telegram_chat_id', 'notification_code', 'notification_code_expires'])

    display = admin.display_name or admin.username
    bot.send_message(
        chat_id,
        f'✅ Connected! Hi **{display}**, you will now receive notifications here.',
        parse_mode='Markdown',
    )
    logger.info('Linked admin %s (pk=%d) to chat_id %d', admin.username, admin.pk, chat_id)


# ── Catch-all ────────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: True)
def handle_other(message):
    bot.send_message(
        message.chat.id,
        'ℹ️ Send your 5-digit code from the admin panel Profile page to connect.\n'
        'Type /start for instructions.',
    )


# ── Helper: send a notification to a linked admin ────────────────────────────

def send_notification(admin_id: int, text: str) -> bool:
    """
    Send a Telegram notification to a linked admin user.
    Returns True if sent, False if admin has no linked chat.
    Can be called from any Django code (views, signals, etc.).
    """
    from core.models import AdminUser

    try:
        admin = AdminUser.objects.get(pk=admin_id)
    except AdminUser.DoesNotExist:
        return False

    if not admin.telegram_chat_id:
        return False

    try:
        _bot = telebot.TeleBot(NOTIFY_BOT_TOKEN)
        _bot.send_message(admin.telegram_chat_id, text, parse_mode='Markdown')
        return True
    except Exception as e:
        logger.error('Failed to send notification to admin %d: %s', admin_id, e)
        return False


def send_notification_to_all_linked(text: str, exclude_id: int = None):
    """Send a notification to ALL admins with linked Telegram accounts."""
    from core.models import AdminUser

    admins = AdminUser.objects.filter(telegram_chat_id__isnull=False)
    if exclude_id:
        admins = admins.exclude(pk=exclude_id)

    _bot = telebot.TeleBot(NOTIFY_BOT_TOKEN)
    for admin in admins:
        try:
            _bot.send_message(admin.telegram_chat_id, text, parse_mode='Markdown')
        except Exception as e:
            logger.error('Failed to send to admin %d: %s', admin.pk, e)


# ── Entry point ──────────────────────────────────────────────────────────────

def run():
    logger.info('Starting Brightway Notification Bot…')
    me = bot.get_me()
    logger.info('Notification bot started: @%s', me.username)
    print(f'Notification bot started: @{me.username}')
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == '__main__':
    run()
