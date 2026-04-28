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


# ── Commands Setup ───────────────────────────────────────────────────────────

def setup_commands():
    try:
        commands = [
            telebot.types.BotCommand("start", "Start or restart the bot"),
            telebot.types.BotCommand("status", "Check connection status"),
            telebot.types.BotCommand("unlink", "Disconnect your account"),
        ]
        bot.set_my_commands(commands)
    except Exception as e:
        logger.error("Failed to set bot commands: %s", e)

# ── /start ───────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['start'])
def handle_start(message):
    from core.models import AdminUser
    
    admin = AdminUser.objects.filter(telegram_chat_id=message.chat.id).first()
    if admin:
        display = admin.display_name or admin.username
        bot.send_message(
            message.chat.id,
            f'👋 Welcome back, **{display}**!\n\n'
            f'✅ Your Telegram is already connected to the **{admin.username}** account.\n'
            f'You are receiving notifications for role: `{admin.role}`.\n\n'
            'Use /status to check connection details or /unlink to disconnect.',
            parse_mode='Markdown',
        )
    else:
        bot.send_message(
            message.chat.id,
            '👋 Welcome to Brightway Notifications!\n\n'
            'To connect your account, go to your **Profile** page in the admin panel, '
            'click **Generate Code**, then send the 5-digit code here.\n\n'
            'Example: `12345`',
            parse_mode='Markdown',
        )


# ── /status ──────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['status'])
def handle_status(message):
    from core.models import AdminUser
    
    admin = AdminUser.objects.filter(telegram_chat_id=message.chat.id).first()
    if admin:
        display = admin.display_name or admin.username
        bot.send_message(
            message.chat.id,
            f'📊 **Connection Status**\n\n'
            f'🟢 **Status:** Connected\n'
            f'👤 **Name:** {display}\n'
            f'🔑 **Username:** {admin.username}\n'
            f'🛡️ **Role:** {admin.role}\n\n'
            'You are receiving notifications for your assigned cases.',
            parse_mode='Markdown',
        )
    else:
        bot.send_message(
            message.chat.id,
            '🔴 **Not Connected**\n\n'
            'You are not currently linked to any Brightway account.\n'
            'Send a 5-digit code from your admin Profile page to connect.',
            parse_mode='Markdown',
        )


# ── /unlink ──────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['unlink'])
def handle_unlink(message):
    from core.models import AdminUser
    
    admin = AdminUser.objects.filter(telegram_chat_id=message.chat.id).first()
    if admin:
        username = admin.username
        admin.telegram_chat_id = None
        admin.save(update_fields=['telegram_chat_id'])
        bot.send_message(
            message.chat.id,
            f'🔌 Disconnected from account **{username}**.\n\n'
            'You will no longer receive notifications here. '
            'Send a new 5-digit code if you wish to reconnect.',
            parse_mode='Markdown',
        )
        logger.info('Admin %s unlinked from chat_id %d via bot command', username, message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            'You are not currently connected to any account.'
        )


# ── Code verification ────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text and m.text.strip().isdigit() and len(m.text.strip()) == 5)
def handle_code(message):
    from core.models import AdminUser

    code = message.text.strip()
    chat_id = message.chat.id
    now = datetime.now()

    # Check if this telegram account is already linked to someone else
    existing_admin = AdminUser.objects.filter(telegram_chat_id=chat_id).first()

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

    # If linked to a DIFFERENT account previously, disconnect the old one
    if existing_admin and existing_admin.pk != admin.pk:
        existing_admin.telegram_chat_id = None
        existing_admin.save(update_fields=['telegram_chat_id'])
        logger.info('Unlinked previous admin %s from chat_id %d', existing_admin.username, chat_id)

    # Link the account
    admin.telegram_chat_id = chat_id
    admin.notification_code = None
    admin.notification_code_expires = None
    admin.save(update_fields=['telegram_chat_id', 'notification_code', 'notification_code_expires'])

    display = admin.display_name or admin.username
    bot.send_message(
        chat_id,
        f'✅ Successfully connected!\n\n'
        f'👤 **Account:** {display} (@{admin.username})\n'
        f'🛡️ **Role:** {admin.role}\n\n'
        f'You will now receive notifications here. Use /status anytime to check.',
        parse_mode='Markdown',
    )
    logger.info('Linked admin %s (pk=%d) to chat_id %d', admin.username, admin.pk, chat_id)


# ── Catch-all ────────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: True)
def handle_other(message):
    from core.models import AdminUser
    
    admin = AdminUser.objects.filter(telegram_chat_id=message.chat.id).first()
    if admin:
        bot.send_message(
            message.chat.id,
            f'You are connected to **{admin.username}**.\n'
            'Use /status for info, or /unlink to disconnect.',
            parse_mode='Markdown'
        )
    else:
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
    setup_commands()
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == '__main__':
    run()
