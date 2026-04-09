#!/usr/bin/env python3
"""
Simplified Telegram Bot for Brightway Consulting (simpled branch).

Handles the pyTelegramBotAPI (bot-token) transport for the simplified
5-step structured conversation flow.  All shared logic lives in
bot/simple_flow.py; this file is only the telebot-specific glue.

Run with:
    python manage.py run_bot --simple
"""

import os
import sys
import uuid
import logging
import threading
from pathlib import Path

# ── Bootstrap Django ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bwc.settings')

import django
django.setup()

import telebot
from telebot import types
from django.conf import settings

from .services import transcribe_voice
from .simple_flow import (
    STEP_INIT, STEP_SUBJECT, STEP_SERVICE, STEP_COLLECTING, STEP_CONFIRM_CONSULTANT, STEP_DONE,
    get_state, set_state, clear_state,
    get_active_subjects, get_services_for_subject,
    db_get_or_create_user, db_get_or_open_case, db_link_case_to_service,
    db_try_assign_consultant, db_notify_consultant, db_finalise_case,
    detect_lang, ai_match_subject, ai_match_service,
    is_done_message, generate_final_message, wants_consultant, is_confirm_yes, is_confirm_no,
    build_greeting, build_service_list, build_collect_prompt,
    build_not_understood, build_no_services, build_ack, build_already_submitted,
    build_consultant_confirm, build_consultant_declined,
    ai_contextual_reply, ai_answer_question,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / 'simple_bot.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Bot init ──────────────────────────────────────────────────────────────────
BOT_TOKEN = getattr(settings, 'BOT_TOKEN', None) or os.getenv('BOT_TOKEN')
UPLOADS_DIR = PROJECT_ROOT / 'uploads'
UPLOADS_DIR.mkdir(exist_ok=True)

if not BOT_TOKEN:
    logger.warning('BOT_TOKEN not configured — simple bot will not start')

    class _DummyBot:
        def message_handler(self, *a, **kw):
            return lambda f: f
        def callback_query_handler(self, *a, **kw):
            return lambda f: f

    bot = _DummyBot()
    _BOT_AVAILABLE = False
else:
    bot = telebot.TeleBot(BOT_TOKEN)
    _BOT_AVAILABLE = True


# ── Inline keyboard builders ──────────────────────────────────────────────────

def _subject_keyboard(subjects: list) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for s in subjects:
        kb.add(types.InlineKeyboardButton(
            f'{s.icon_emoji} {s.name}',
            callback_data=f'simple_subject_{s.pk}',
        ))
    return kb


def _service_keyboard(services: list) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for svc in services:
        kb.add(types.InlineKeyboardButton(
            f'{svc.icon_emoji} {svc.name}',
            callback_data=f'simple_service_{svc.pk}',
        ))
    return kb


# ── Typing indicator ──────────────────────────────────────────────────────────

def _typing_loop(chat_id: int, stop_event: threading.Event, interval: int = 4) -> None:
    while not stop_event.wait(interval):
        try:
            bot.send_chat_action(chat_id, 'typing')
        except Exception:
            break


# ── Flow actions ──────────────────────────────────────────────────────────────

def _send_subject_selection(chat_id: int, uid: int, lang: str) -> None:
    subjects = get_active_subjects()
    if not subjects:
        bot.send_message(chat_id, 'No subject categories configured yet. Please contact us directly.')
        return
    text = build_greeting(lang, subjects)
    bot.send_message(chat_id, text, reply_markup=_subject_keyboard(subjects))
    set_state(uid, step=STEP_SUBJECT, lang=lang)


def _handle_subject_selected(chat_id: int, uid: int, subject_id: int) -> None:
    from core.models import Subject
    lang = get_state(uid).get('lang', 'en')
    try:
        subject = Subject.objects.get(pk=subject_id, is_active=True)
    except Subject.DoesNotExist:
        bot.send_message(chat_id, build_not_understood(lang))
        return
    services = get_services_for_subject(subject_id)
    if not services:
        bot.send_message(chat_id, build_no_services(lang))
        return
    bot.send_message(chat_id, build_service_list(lang, subject, services),
                     reply_markup=_service_keyboard(services))
    set_state(uid, step=STEP_SERVICE, subject_id=subject_id)


def _handle_service_selected(chat_id: int, uid: int, tg_user: types.User, service_id: int) -> None:
    from core.models import ServiceDefinition
    state = get_state(uid)
    lang = state.get('lang', 'en')
    try:
        svc_def = ServiceDefinition.objects.get(pk=service_id, is_active=True)
    except ServiceDefinition.DoesNotExist:
        bot.send_message(chat_id, build_not_understood(lang))
        return
    db_user, _ = db_get_or_create_user(tg_user.id, tg_user.first_name, tg_user.username)
    case = db_get_or_open_case(db_user, svc_def.slug)
    db_link_case_to_service(case, svc_def, state.get('subject_id'))
    items = svc_def.get_collect_items() or svc_def.get_documents_list() or []
    prompt = build_collect_prompt(lang, svc_def, items)
    bot.send_message(chat_id, prompt)
    case.add_message('assistant', prompt)
    set_state(uid, step=STEP_COLLECTING, service_id=service_id, case_id=case.pk, items_to_collect=items)


def _handle_collecting(chat_id: int, uid: int, tg_user: types.User,
                        text: str = None, file_label: str = None) -> None:
    state = get_state(uid)
    lang = state.get('lang', 'en')
    case_id = state.get('case_id')
    if not case_id:
        clear_state(uid)
        _send_subject_selection(chat_id, uid, lang)
        return
    from core.models import Case
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        clear_state(uid)
        _send_subject_selection(chat_id, uid, lang)
        return
    if text and is_done_message(text, lang):
        final_msg = db_finalise_case(uid, tg_user.id, tg_user.first_name, tg_user.username, lang)
        bot.send_message(chat_id, final_msg)
        return
    if text:
        case.add_message('user', text)
        # Answer clarifying questions; acknowledge data submissions
        svc_def = None
        svc_id = state.get('service_id')
        if svc_id:
            try:
                from core.models import ServiceDefinition
                svc_def = ServiceDefinition.objects.get(pk=svc_id)
            except Exception:
                pass
        ai_reply = ai_answer_question(text, svc_def, lang)
        if ai_reply:
            case.add_message('assistant', ai_reply)
            bot.send_message(chat_id, ai_reply)
        else:
            bot.send_message(chat_id, build_ack(lang))
    elif file_label:
        case.add_message('user', f'[{file_label}]')
        bot.send_message(chat_id, build_ack(lang))


# ── /start ─────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['start'])
def handle_start(message: types.Message) -> None:
    uid = message.from_user.id
    clear_state(uid)
    tg_lang = (getattr(message.from_user, 'language_code', None) or 'en')[:2].lower()
    lang = tg_lang if tg_lang in ('en', 'ru', 'uz') else 'en'
    _send_subject_selection(message.chat.id, uid, lang)


# ── Text messages ──────────────────────────────────────────────────────────────

@bot.message_handler(content_types=['text'])
def handle_text(message: types.Message) -> None:
    uid = message.from_user.id
    text = message.text.strip()
    state = get_state(uid)
    step = state.get('step', STEP_INIT)

    stop_ev = threading.Event()
    typing_t = threading.Thread(target=_typing_loop, args=(message.chat.id, stop_ev), daemon=True)
    typing_t.start()
    try:
        stored_lang = state.get('lang', 'en')
        # Only re-detect on meaningful text; skip short/numeric inputs like "1", "2"
        if len(text) > 3 and not text.isdigit():
            detected = detect_lang(text, fallback=stored_lang)
            set_state(uid, lang=detected)
            lang = detected
        else:
            lang = stored_lang

        # ── Consultant connect request (any active step) ──────────────────
        if step not in (STEP_DONE, STEP_CONFIRM_CONSULTANT):
            if wants_consultant(text, lang):
                set_state(uid, step=STEP_CONFIRM_CONSULTANT, prev_step=step)
                bot.send_message(message.chat.id, build_consultant_confirm(lang))
                return

        # ── Consultant confirmation ───────────────────────────────────────
        if step == STEP_CONFIRM_CONSULTANT:
            if is_confirm_yes(text):
                final_msg = db_finalise_case(uid, message.from_user.id, message.from_user.first_name,
                                             message.from_user.username, lang)
                bot.send_message(message.chat.id, final_msg)
            elif is_confirm_no(text):
                prev = state.get('prev_step', STEP_COLLECTING)
                set_state(uid, step=prev)
                bot.send_message(message.chat.id, build_consultant_declined(lang))
            else:
                bot.send_message(message.chat.id, build_consultant_confirm(lang))
            return

        if step in (STEP_INIT, ''):
            _send_subject_selection(message.chat.id, uid, lang)

        elif step == STEP_SUBJECT:
            subjects = get_active_subjects()
            if text.isdigit():
                idx = int(text) - 1
                if 0 <= idx < len(subjects):
                    _handle_subject_selected(message.chat.id, uid, subjects[idx].pk)
                    return
            matched_id = ai_match_subject(text, subjects, lang)
            if matched_id:
                _handle_subject_selected(message.chat.id, uid, matched_id)
            else:
                options = [f'{s.icon_emoji} {s.get_name(lang)}' for s in subjects]
                bot.send_message(message.chat.id, ai_contextual_reply(text, options, STEP_SUBJECT, lang))

        elif step == STEP_SERVICE:
            subject_id = state.get('subject_id')
            services = get_services_for_subject(subject_id) if subject_id else []
            if text.isdigit():
                idx = int(text) - 1
                if 0 <= idx < len(services):
                    _handle_service_selected(message.chat.id, uid, message.from_user, services[idx].pk)
                    return
            matched_id = ai_match_service(text, services, lang)
            if matched_id:
                _handle_service_selected(message.chat.id, uid, message.from_user, matched_id)
            else:
                options = [f'{svc.icon_emoji} {svc.name}' for svc in services]
                bot.send_message(message.chat.id, ai_contextual_reply(text, options, STEP_SERVICE, lang))

        elif step == STEP_COLLECTING:
            _handle_collecting(message.chat.id, uid, message.from_user, text=text)

        elif step == STEP_DONE:
            bot.send_message(message.chat.id, build_already_submitted(lang))

    finally:
        stop_ev.set()


# ── Photos ─────────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=['photo'])
def handle_photo(message: types.Message) -> None:
    from core.models import Document
    uid = message.from_user.id
    state = get_state(uid)
    lang = state.get('lang', 'en')
    if state.get('step') != STEP_COLLECTING:
        _send_subject_selection(message.chat.id, uid, lang)
        return
    case_id = state.get('case_id')
    if not case_id:
        clear_state(uid)
        _send_subject_selection(message.chat.id, uid, lang)
        return
    from core.models import Case
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return
    photo = message.photo[-1]
    fi = bot.get_file(photo.file_id)
    uid_str = str(uuid.uuid4())[:8]
    filename = f'{uid_str}.jpg'
    with open(UPLOADS_DIR / filename, 'wb') as f:
        f.write(bot.download_file(fi.file_path))
    Document.objects.create(
        case=case, file_path=filename, file_type='jpg',
        telegram_file_id=f'local:{filename}', file_unique_id=photo.file_unique_id,
        media_type='photo', display_name=f'photo_{message.from_user.id}.jpg',
    )
    _handle_collecting(message.chat.id, uid, message.from_user,
                       file_label=f'FILE:{uid_str}:{filename}:photo')


# ── Documents ──────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=['document'])
def handle_document(message: types.Message) -> None:
    from core.models import Document, Case
    uid = message.from_user.id
    state = get_state(uid)
    lang = state.get('lang', 'en')
    if state.get('step') != STEP_COLLECTING:
        _send_subject_selection(message.chat.id, uid, lang)
        return
    case_id = state.get('case_id')
    if not case_id:
        clear_state(uid)
        _send_subject_selection(message.chat.id, uid, lang)
        return
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return
    doc = message.document
    uid_str = str(uuid.uuid4())[:8]
    original = doc.file_name or 'document'
    ext = os.path.splitext(original)[1] or ''
    filename = f'{uid_str}{ext}'
    filepath = UPLOADS_DIR / filename
    fi = bot.get_file(doc.file_id)
    with open(filepath, 'wb') as f:
        f.write(bot.download_file(fi.file_path))
    audio_exts = {'.ogg', '.oga', '.mp3', '.m4a', '.wav', '.opus', '.webm'}
    mime = getattr(doc, 'mime_type', '') or ''
    media_type = 'voice' if (ext.lower() in audio_exts or mime.startswith('audio/')) else 'document'
    doc_record = Document.objects.create(
        case=case, file_path=filename, file_type=ext.lstrip('.').lower() or 'unknown',
        telegram_file_id=f'local:{filename}', file_unique_id=doc.file_unique_id,
        media_type=media_type, description=original,
        display_name=f'{media_type}_{message.from_user.id}{ext}',
    )
    # .ogg voice notes → transcribe, treat as text
    if media_type == 'voice' and ext.lower() == '.ogg':
        bot.send_chat_action(message.chat.id, 'typing')
        transcription = transcribe_voice(str(filepath), lang)
        if transcription:
            doc_record.transcription = transcription
            doc_record.save(update_fields=['transcription'])
            case.add_message('user', f'[Voice note transcription]: {transcription}')
            _handle_collecting(message.chat.id, uid, message.from_user, text=transcription)
            return
    _handle_collecting(message.chat.id, uid, message.from_user,
                       file_label=f'FILE:{uid_str}:{original}:{media_type}')


# ── Voice messages ─────────────────────────────────────────────────────────────

@bot.message_handler(content_types=['voice', 'audio'])
def handle_voice(message: types.Message) -> None:
    from core.models import Document, Case
    uid = message.from_user.id
    state = get_state(uid)
    lang = state.get('lang', 'en')
    if state.get('step') != STEP_COLLECTING:
        _send_subject_selection(message.chat.id, uid, lang)
        return
    case_id = state.get('case_id')
    if not case_id:
        clear_state(uid)
        _send_subject_selection(message.chat.id, uid, lang)
        return
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return
    is_voice = bool(message.voice)
    tg_file = message.voice if is_voice else message.audio
    ext = '.ogg' if is_voice else (os.path.splitext(getattr(tg_file, 'file_name', '') or '.mp3')[1] or '.mp3')
    uid_str = str(uuid.uuid4())[:8]
    filename = f'{uid_str}{ext}'
    filepath = UPLOADS_DIR / filename
    fi = bot.get_file(tg_file.file_id)
    with open(filepath, 'wb') as f:
        f.write(bot.download_file(fi.file_path))
    doc_record = Document.objects.create(
        case=case, file_path=filename, file_type='voice',
        telegram_file_id=f'local:{filename}', file_unique_id=tg_file.file_unique_id,
        media_type='voice', display_name=f'voice_{message.from_user.id}{ext}',
    )
    if is_voice or ext.lower() == '.ogg':
        bot.send_chat_action(message.chat.id, 'typing')
        transcription = transcribe_voice(str(filepath), lang)
        if transcription:
            doc_record.transcription = transcription
            doc_record.save(update_fields=['transcription'])
            case.add_message('user', f'[Voice note]: {transcription}')
            _handle_collecting(message.chat.id, uid, message.from_user, text=transcription)
            return
    _handle_collecting(message.chat.id, uid, message.from_user,
                       file_label=f'FILE:{uid_str}:{filename}:voice')


# ── Callback queries ──────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data.startswith('simple_subject_'))
def cb_subject(call: types.CallbackQuery) -> None:
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    try:
        subject_id = int(call.data.split('_')[-1])
    except ValueError:
        return
    _handle_subject_selected(call.message.chat.id, uid, subject_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('simple_service_'))
def cb_service(call: types.CallbackQuery) -> None:
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    try:
        service_id = int(call.data.split('_')[-1])
    except ValueError:
        return
    _handle_service_selected(call.message.chat.id, uid, call.from_user, service_id)


# ── Admin panel integration ────────────────────────────────────────────────────

def send_message_to_user(tg_id: int, text: str, sender_name: str = 'Admin') -> bool:
    if not _BOT_AVAILABLE:
        return False
    try:
        bot.send_message(tg_id, text)
        return True
    except Exception as e:
        logger.error('Error sending admin message to %s: %s', tg_id, e)
        return False


def get_bot_info() -> dict:
    if not _BOT_AVAILABLE:
        return {'ok': False, 'error': 'Bot not initialized'}
    try:
        me = bot.get_me()
        return {'ok': True, 'id': me.id, 'username': me.username, 'first_name': me.first_name}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ── Entry point ────────────────────────────────────────────────────────────────

def run_bot() -> None:
    if not _BOT_AVAILABLE:
        logger.error('Cannot start simple bot: BOT_TOKEN not configured')
        return
    logger.info('Starting Brightway Consulting Simple Bot…')
    me = bot.get_me()
    logger.info('Simple bot started: @%s', me.username)
    print(f'Simple bot started: @{me.username}')
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == '__main__':
    run_bot()
