#!/usr/bin/env python3
"""
Brightway Consulting – Consultant Control Bot.

Lets consultants control the client-facing bot from Telegram:

  1. Forward any message from a client's chat to this bot.
  2. The bot identifies the client (by Telegram id, or by name when the
     client hides their account in forwarded messages) and shows a menu.
  3. From the menu the consultant can:
       ⏸ Stop bot    – the assistant goes silent in that chat
       🙋 Take over   – stop the bot AND assign the case to yourself
       ▶️ Resume bot  – turn the assistant back on for that chat
       🔄 Refresh     – re-check the current status

The stop/resume flag is Case.ai_enabled — the same flag the userbot and the
simple bot check before replying, so stopping works across processes.

Instead of forwarding, a consultant may also send the client's @username or
numeric Telegram ID.

Run:
    python manage.py run_control_bot

Requires CONTROL_BOT_TOKEN in .env.
Authorisation: the sender must be linked to an AdminUser account — the same
5-digit pairing code used by the notification bot (bot/notify_bot.py).
A consultant already linked there is authorised here automatically.
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
from telebot import types
from django.conf import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / 'control_bot.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Bot init ─────────────────────────────────────────────────────────────────
CONTROL_BOT_TOKEN = getattr(settings, 'CONTROL_BOT_TOKEN', None) or os.getenv('CONTROL_BOT_TOKEN')

if not CONTROL_BOT_TOKEN:
    logger.error('CONTROL_BOT_TOKEN not configured – control bot will not start.')
    sys.exit(1)

bot = telebot.TeleBot(CONTROL_BOT_TOKEN)


# ── Auth helpers ─────────────────────────────────────────────────────────────

def _get_admin(tg_user_id: int):
    """Return the linked, active AdminUser for this Telegram user, or None."""
    from core.models import AdminUser
    return AdminUser.objects.filter(telegram_chat_id=tg_user_id, is_active=True).first()


def _require_admin(message) -> bool:
    """Reply with an authorisation prompt if the sender is not linked."""
    if _get_admin(message.from_user.id):
        return True
    bot.send_message(
        message.chat.id,
        '⛔ This bot is for Brightway consultants only.\n\n'
        'To link your account: open your Profile page in the admin panel, '
        'click Generate Code, then send the 5-digit code here.',
    )
    return False


# ── Client lookup helpers ────────────────────────────────────────────────────

def _get_user(tg_id: int):
    from core.models import TgUser
    return TgUser.objects.filter(telegram_id=tg_id).first()


def _get_active_case(user):
    from core.models import Case
    if not user:
        return None
    return Case.objects.filter(user=user, status='active').order_by('-updated_at').first()


def _search_clients(query: str) -> list:
    """Find clients by @username, name, or numeric Telegram ID (up to 5)."""
    from django.db.models import Q
    from core.models import TgUser
    q = query.strip().lstrip('@')
    if not q:
        return []
    if q.isdigit():
        user = TgUser.objects.filter(telegram_id=int(q)).first()
        return [user] if user else []
    return list(
        TgUser.objects.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q)
        ).order_by('-created_at')[:5]
    )


# ── Forwarded-message identification ─────────────────────────────────────────

def _extract_forward_target(message) -> tuple | None:
    """
    Identify who a forwarded message came from.

    Returns ('id', telegram_id) when the sender's account is visible,
    ('name', display_name) when the sender hides their account,
    or None when the message is not forwarded from a user.
    """
    origin = getattr(message, 'forward_origin', None)
    if origin is not None:
        otype = getattr(origin, 'type', '')
        if otype == 'user':
            sender = getattr(origin, 'sender_user', None)
            if sender:
                return ('id', sender.id)
        elif otype == 'hidden_user':
            name = (getattr(origin, 'sender_name', '') or '').strip()
            if name:
                return ('name', name)
        return None  # forwarded from a group/channel — not a client DM
    # Legacy Bot API fields (pre-7.0 clients)
    fwd_from = getattr(message, 'forward_from', None)
    if fwd_from is not None:
        return ('id', fwd_from.id)
    fwd_name = (getattr(message, 'forward_sender_name', None) or '').strip()
    if fwd_name:
        return ('name', fwd_name)
    return None


# ── Bot on/off actions ───────────────────────────────────────────────────────

def _set_bot(tg_id: int, enabled: bool):
    """Set ai_enabled on the client's active case (creating user/case if needed)."""
    from core.models import TgUser, Case
    user, _ = TgUser.objects.get_or_create(telegram_id=tg_id, defaults={'language_code': ''})
    case = Case.objects.filter(user=user, status='active').order_by('-updated_at').first()
    if not case:
        case = Case.objects.create(user=user, service='general', status='active')
    if case.ai_enabled != enabled:
        case.ai_enabled = enabled
        case.save(update_fields=['ai_enabled'])
    return user, case


def _take_over(tg_id: int, admin):
    """Stop the bot and assign the client's case to this consultant."""
    from core.models import AdminAssignment, Notification
    user, case = _set_bot(tg_id, False)
    if case.assigned_to_id != admin.pk:
        case.assigned_to = admin
        case.save(update_fields=['assigned_to'])
    AdminAssignment.objects.get_or_create(admin=admin, user=user)
    Notification.objects.create(
        admin_user=admin,
        title=f'You took over case #{case.pk}',
        message=f'Client: {user}\nThe bot is stopped — the chat is yours.',
        link=f'/admin/cases/{case.pk}',
    )
    return user, case


# ── Menu rendering ───────────────────────────────────────────────────────────

def _status_text(tg_id: int) -> tuple:
    """Build the status text; returns (text, bot_on)."""
    user = _get_user(tg_id)
    case = _get_active_case(user)
    lines = []
    if user:
        name = ' '.join(p for p in [user.first_name, user.last_name] if p) or '—'
        uname = f' (@{user.username})' if user.username else ''
        lines.append(f'👤 {name}{uname}')
    else:
        lines.append('👤 Unknown client (has not written yet)')
    lines.append(f'🆔 {tg_id}')
    if case:
        lines.append(f'📋 Case #{case.pk} — {case.get_service_display()} ({case.status})')
        lines.append(f'🙋 Assigned: {case.assigned_to.username if case.assigned_to_id else "—"}')
        bot_on = case.ai_enabled
    else:
        lines.append('📋 No active case')
        bot_on = True
    lines.append('')
    if bot_on:
        lines.append('🤖 Bot: ON ✅ — replies automatically')
    else:
        lines.append('🤖 Bot: OFF ⏸ — silent; consultant chats manually')
    return '\n'.join(lines), bot_on


def _menu_keyboard(tg_id: int, bot_on: bool) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    if bot_on:
        kb.add(types.InlineKeyboardButton('⏸ Stop bot', callback_data=f'ctl_stop_{tg_id}'))
    else:
        kb.add(types.InlineKeyboardButton('▶️ Resume bot', callback_data=f'ctl_start_{tg_id}'))
    kb.add(
        types.InlineKeyboardButton('🙋 Take over', callback_data=f'ctl_take_{tg_id}'),
        types.InlineKeyboardButton('🔄 Refresh', callback_data=f'ctl_info_{tg_id}'),
    )
    return kb


def _send_menu(chat_id: int, tg_id: int) -> None:
    text, bot_on = _status_text(tg_id)
    bot.send_message(chat_id, text, reply_markup=_menu_keyboard(tg_id, bot_on))


def _user_button_label(user) -> str:
    name = ' '.join(p for p in [user.first_name, user.last_name] if p) or '(no name)'
    uname = f' @{user.username}' if user.username else ''
    return f'{name}{uname} · {user.telegram_id}'


def _send_candidates(chat_id: int, query: str, matches: list) -> None:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for u in matches:
        kb.add(types.InlineKeyboardButton(
            _user_button_label(u), callback_data=f'ctl_pick_{u.telegram_id}',
        ))
    bot.send_message(chat_id, f'Clients matching "{query}" — pick one:', reply_markup=kb)


def _resolve_and_show(chat_id: int, kind: str, value) -> None:
    """Shared by forwarded messages and text lookups."""
    if kind == 'id':
        _send_menu(chat_id, int(value))
        return
    matches = _search_clients(str(value))
    if not matches:
        bot.send_message(
            chat_id,
            f'❓ No client found matching "{value}".\n'
            'The sender may hide their account — send their @username or '
            'numeric Telegram ID instead.',
        )
    elif len(matches) == 1:
        _send_menu(chat_id, matches[0].telegram_id)
    else:
        _send_candidates(chat_id, str(value), matches)


# ── /start ───────────────────────────────────────────────────────────────────

_INSTRUCTIONS = (
    '🎛 Brightway Consultant Control\n\n'
    'To control the bot in a client chat:\n'
    '1️⃣ Forward any message from the client chat here\n'
    '   (or send the client\'s @username / Telegram ID)\n'
    '2️⃣ Use the menu:\n'
    '   ⏸ Stop bot — bot goes silent, you chat manually\n'
    '   🙋 Take over — stop the bot and assign the case to you\n'
    '   ▶️ Resume bot — turn the bot back on\n\n'
    'Stopping works even before the client writes — the bot will stay silent.'
)


@bot.message_handler(commands=['start'])
def handle_start(message: types.Message) -> None:
    admin = _get_admin(message.from_user.id)
    if admin:
        bot.send_message(
            message.chat.id,
            f'👋 Welcome, {admin.display_name or admin.username}!\n\n' + _INSTRUCTIONS,
        )
    else:
        bot.send_message(
            message.chat.id,
            '👋 This bot lets Brightway consultants stop/resume the client bot.\n\n'
            'To link your account: open your Profile page in the admin panel, '
            'click Generate Code, then send the 5-digit code here.',
        )


# ── 5-digit pairing code (same mechanism as the notification bot) ────────────

@bot.message_handler(func=lambda m: m.text and m.text.strip().isdigit()
                     and len(m.text.strip()) == 5
                     and _extract_forward_target(m) is None)
def handle_code(message: types.Message) -> None:
    from core.models import AdminUser

    code = message.text.strip()
    chat_id = message.chat.id

    try:
        admin = AdminUser.objects.get(notification_code=code)
    except AdminUser.DoesNotExist:
        bot.send_message(chat_id, '❌ Invalid code. Please check and try again.')
        return

    if admin.notification_code_expires and admin.notification_code_expires < datetime.now():
        bot.send_message(chat_id, '⏰ This code has expired. Please generate a new one from your profile.')
        admin.notification_code = None
        admin.notification_code_expires = None
        admin.save(update_fields=['notification_code', 'notification_code_expires'])
        return

    # Unlink whichever account previously used this Telegram chat
    previous = AdminUser.objects.filter(telegram_chat_id=chat_id).exclude(pk=admin.pk).first()
    if previous:
        previous.telegram_chat_id = None
        previous.save(update_fields=['telegram_chat_id'])
        logger.info('Unlinked previous admin %s from chat_id %d', previous.username, chat_id)

    admin.telegram_chat_id = chat_id
    admin.notification_code = None
    admin.notification_code_expires = None
    admin.save(update_fields=['telegram_chat_id', 'notification_code', 'notification_code_expires'])

    bot.send_message(
        chat_id,
        f'✅ Linked to {admin.display_name or admin.username} ({admin.role}).\n\n' + _INSTRUCTIONS,
    )
    logger.info('Control bot: linked admin %s (pk=%d) to chat_id %d', admin.username, admin.pk, chat_id)


# ── Forwarded messages → identify client ─────────────────────────────────────

_FORWARD_CONTENT = ['text', 'photo', 'document', 'voice', 'audio', 'video',
                    'video_note', 'sticker', 'contact', 'location', 'animation']


@bot.message_handler(func=lambda m: _extract_forward_target(m) is not None,
                     content_types=_FORWARD_CONTENT)
def handle_forwarded(message: types.Message) -> None:
    if not _require_admin(message):
        return
    target = _extract_forward_target(message)
    if not target:
        bot.send_message(
            message.chat.id,
            '❓ Could not identify the client from that forward.\n'
            'Send their @username or numeric Telegram ID instead.',
        )
        return
    kind, value = target
    _resolve_and_show(message.chat.id, kind, value)


# ── Text lookup (@username / Telegram ID / name) ─────────────────────────────

@bot.message_handler(content_types=['text'])
def handle_text(message: types.Message) -> None:
    text = (message.text or '').strip()
    if not text or text.startswith('/'):
        return
    if not _require_admin(message):
        return
    if text.isdigit():
        _send_menu(message.chat.id, int(text))
        return
    _resolve_and_show(message.chat.id, 'name', text)


# ── Inline menu callbacks ────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith('ctl_'))
def handle_callback(call: types.CallbackQuery) -> None:
    admin = _get_admin(call.from_user.id)
    if not admin:
        bot.answer_callback_query(call.id, '⛔ Not authorised', show_alert=True)
        return

    try:
        action, tg_raw = call.data[4:].split('_', 1)
        tg_id = int(tg_raw)
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id)
        return

    note = ''
    if action == 'stop':
        _set_bot(tg_id, False)
        note = '⏸ Bot stopped for this chat'
        logger.info('Admin %s stopped bot for client %s', admin.username, tg_id)
    elif action == 'start':
        _set_bot(tg_id, True)
        note = '▶️ Bot resumed for this chat'
        logger.info('Admin %s resumed bot for client %s', admin.username, tg_id)
    elif action == 'take':
        _take_over(tg_id, admin)
        note = '🙋 Bot stopped; case assigned to you'
        logger.info('Admin %s took over client %s', admin.username, tg_id)
    elif action in ('info', 'pick'):
        pass
    else:
        bot.answer_callback_query(call.id)
        return

    text, bot_on = _status_text(tg_id)
    try:
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=_menu_keyboard(tg_id, bot_on),
        )
    except Exception as e:
        if 'message is not modified' not in str(e).lower():
            logger.warning('Could not edit menu message: %s', e)
            _send_menu(call.message.chat.id, tg_id)
    bot.answer_callback_query(call.id, note or None)


# ── Entry point ──────────────────────────────────────────────────────────────

def _setup_commands() -> None:
    try:
        bot.set_my_commands([telebot.types.BotCommand('start', 'Show instructions')])
    except Exception as e:
        logger.error('Failed to set bot commands: %s', e)


def run() -> None:
    logger.info('Starting Brightway Consultant Control Bot…')
    me = bot.get_me()
    logger.info('Control bot started: @%s', me.username)
    print(f'Control bot started: @{me.username}')
    _setup_commands()
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == '__main__':
    run()
