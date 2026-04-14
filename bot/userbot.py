#!/usr/bin/env python3
"""
Telegram Userbot for Brightway Consulting.

Uses Telethon library for:
- Sending messages on behalf of the business
- Importing chat history from existing conversations
- Processing pending send queue
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

# Bootstrap Django
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bwc.settings')

import django
django.setup()

from django.conf import settings
from telethon import TelegramClient, events, Button
from telethon.tl import functions
from telethon.tl.types import (
    Message, MessageMediaPhoto, MessageMediaDocument, SendMessageTypingAction,
    DocumentAttributeSticker,
)

from .messages import t, get_all_languages, LANG_CALLBACKS
from .services import (
    ai_detect_service, ask_ai, update_user_profile, should_update_profile,
    suggest_document_name, parse_filename_from_response,
    transcribe_voice, is_ai_master_enabled, wants_consultant_now,
    group_is_relevant, group_dm_invite_message, group_answer_question,
    READY_FOR_CONSULTANT_MARKER,
)
from .simple_flow import (
    STEP_INIT, STEP_SUBJECT, STEP_SERVICE, STEP_COLLECTING, STEP_CONFIRM_CONSULTANT, STEP_DONE,
    get_state, set_state, clear_state,
    get_active_subjects, get_services_for_subject,
    db_get_or_create_user, db_get_or_open_case, db_link_case_to_service,
    db_flush_pending_messages, db_finalise_case,
    detect_lang, ai_match_subject, ai_match_service,
    is_done_message, wants_consultant, is_confirm_yes, is_confirm_no,
    build_greeting, build_greeting_universal, build_service_list, build_collect_prompt,
    build_not_understood, build_no_services, build_ack, build_already_submitted,
    build_consultant_confirm, build_consultant_declined,
    ai_contextual_reply, ai_answer_question,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / 'userbot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

_KNOWN_LANGS = {'en', 'ru', 'uz'}


def _lang_from_sender(sender, state: dict) -> str:
    """
    Resolve the best language to use for a user.
    Priority: 1) already stored in conversation state  2) Telegram lang_code
    Falls back to None so the caller can decide to show a universal greeting.
    """
    stored = state.get('lang')
    if stored in _KNOWN_LANGS:
        return stored
    tg_lang = (getattr(sender, 'lang_code', None) or '').lower()[:2]
    if tg_lang in _KNOWN_LANGS:
        return tg_lang
    return None  # unknown — caller should use universal greeting


# Directories
SESSIONS_DIR = PROJECT_ROOT / 'sessions'
SESSIONS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = PROJECT_ROOT / 'uploads'
UPLOADS_DIR.mkdir(exist_ok=True)
PROFILES_DIR = UPLOADS_DIR / 'profiles'
PROFILES_DIR.mkdir(exist_ok=True)

# Telegram API credentials (strip; treat empty or comment-only as unset)
def _phone_val(name: str):
    v = getattr(settings, name, None) or os.getenv(name)
    v = (v or '').strip()
    if not v or v.startswith('#'):
        return None
    return v

API_ID = getattr(settings, 'TG_API_ID', None) or os.getenv('TG_API_ID')
API_HASH = getattr(settings, 'TG_API_HASH', None) or os.getenv('TG_API_HASH')
PHONE = _phone_val('TG_PHONE')

API_ID_2 = getattr(settings, 'TG_API_ID_2', None) or os.getenv('TG_API_ID_2')
API_HASH_2 = getattr(settings, 'TG_API_HASH_2', None) or os.getenv('TG_API_HASH_2')
PHONE_2 = _phone_val('TG_PHONE_2')

# Thread pool for sync ORM operations
executor = ThreadPoolExecutor(max_workers=4)

# Active clients list
ACTIVE_CLIENTS = []


# ============== Helper Functions ==============

async def run_sync(func):
    """Run a synchronous function in the executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, func)


def __user_exists_by_telegram_id(tg_id: int) -> bool:
    """Check if a user with this Telegram ID exists (sync, for executor)."""
    from core.models import TgUser
    return TgUser.objects.filter(telegram_id=tg_id).exists()


def _get_or_create_user(tg_id: int, first_name: str = None, username: str = None):
    """Get or create TgUser (sync function for executor). Returns (user, created)."""
    from core.models import TgUser
    
    user, created = TgUser.objects.get_or_create(
        telegram_id=tg_id,
        defaults={
            'first_name': first_name,
            'username': username,
            'language_code': 'en'
        }
    )
    return user, created


def _set_linked_account(tg_id: int, account_index: int):
    """Set linked account for user."""
    from core.models import TgUser
    TgUser.objects.filter(telegram_id=tg_id).update(linked_account=account_index)


def _check_ai_disabled(tg_id: int) -> bool:
    """Return True if the user's active case has ai_enabled=False (consultant mode)."""
    from core.models import Case, TgUser
    try:
        user = TgUser.objects.get(telegram_id=tg_id)
        case = Case.objects.filter(user=user, status='active').order_by('-updated_at').first()
        return bool(case and not case.ai_enabled)
    except Exception:
        return False


def _get_or_open_case(user, service='general'):
    """Get active case or create new one."""
    from core.models import Case
    
    case = Case.objects.filter(
        user=user,
        status='active'
    ).first()
    
    if not case:
        case = Case.objects.create(
            user=user,
            service=service,
            status='active',
            payment_status='pending'
        )
    
    return case


def _first_media_label(media) -> str:
    """Return a short label for the first message when it's media (sticker, photo, etc.)."""
    if media is None:
        return "[Media]"
    if isinstance(media, MessageMediaPhoto):
        return "[Photo]"
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        attrs = getattr(doc, 'attributes', []) or []
        if any(isinstance(a, DocumentAttributeSticker) for a in attrs):
            return "[Sticker]"
        mime = (doc.mime_type or '').lower()
        if mime.startswith('audio/') or any(getattr(a, 'voice', False) for a in attrs):
            return "[Voice]"
        if mime.startswith('video/'):
            return "[Video]"
        return "[Media]"
    return "[Media]"


def _telegram_message_role(msg) -> str:
    """
    Map Telethon message direction to conversation role. Single source of truth to prevent swapped attribution.
    - msg.out True  = we (userbot) sent it → 'assistant'
    - msg.out False = they (client) sent it → 'user'
    """
    return 'assistant' if getattr(msg, 'out', False) else 'user'


def _add_message_to_case(case_id: int, role: str, content: str, sender: str = None):
    """Add message to case conversation."""
    from core.models import Case
    
    case = Case.objects.get(pk=case_id)
    case.add_message(role, content, sender)


async def fetch_telegram_profile_to_db(client: TelegramClient, peer) -> bool:
    """
    Fetch Telegram profile (photo, bio, first_name, last_name, username) for the given peer
    and update TgUser in DB. Creates profiles dir and downloads photo to uploads/profiles/{tg_id}.jpg.
    Returns True if user was updated.
    """
    from core.models import TgUser
    from telethon.tl.functions.users import GetFullUserRequest

    try:
        entity = await client.get_entity(peer)
        if not entity or getattr(entity, 'id', None) is None:
            return False
        tg_id = entity.id
        # Get full user for bio (about)
        try:
            full = await client(GetFullUserRequest(entity))
            bio = (getattr(full.full_user, 'about', None) or '').strip() or None
        except Exception:
            bio = None
        first_name = getattr(entity, 'first_name', None) or None
        last_name = getattr(entity, 'last_name', None) or None
        username = getattr(entity, 'username', None) or None

        # Download profile photo
        profile_photo_path = None
        try:
            path = PROFILES_DIR / f"{tg_id}.jpg"
            result = await client.download_profile_photo(entity, file=str(path))
            if result:
                profile_photo_path = f"profiles/{tg_id}.jpg"
        except Exception as e:
            logger.debug(f"Profile photo download for {tg_id}: {e}")

        def update_user():
            try:
                user = TgUser.objects.get(telegram_id=tg_id)
            except TgUser.DoesNotExist:
                return False
            updated = False
            if first_name is not None and user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if last_name is not None and user.last_name != last_name:
                user.last_name = last_name
                updated = True
            if username is not None and user.username != username:
                user.username = username
                updated = True
            if bio is not None and user.bio != bio:
                user.bio = bio
                updated = True
            if profile_photo_path is not None and user.profile_photo_path != profile_photo_path:
                user.profile_photo_path = profile_photo_path
                updated = True
            if updated:
                user.save()
            return True

        return await run_sync(update_user)
    except Exception as e:
        logger.debug(f"fetch_telegram_profile_to_db: {e}")
        return False


def _create_document(case_id: int, filename: str, file_type: str,
                     unique_id: str, media_type: str = 'document', display_name: str = None):
    """Create document record. Returns the created Document."""
    from core.models import Case, Document

    case = Case.objects.get(pk=case_id)
    doc = Document.objects.create(
        case=case,
        file_path=filename,
        display_name=display_name,
        file_type=file_type,
        telegram_file_id=f"local:{filename}",
        file_unique_id=unique_id,
        media_type=media_type
    )
    return doc


# ============== Language Buttons ==============

def get_language_buttons():
    """Get inline buttons for language selection."""
    return [
        [
            Button.inline("🇬🇧 English", b"lang_en"),
            Button.inline("🇺🇿 O'zbek", b"lang_uz"),
            Button.inline("🇷🇺 Русский", b"lang_ru"),
        ]
    ]


# ============== Simplified-flow Userbot Helpers ==============

def _subject_buttons(subjects: list) -> list | None:
    """Build Telethon inline button rows for the subject list (one per row)."""
    if not subjects:
        return None
    return [[Button.inline(f'{s.icon_emoji} {s.name}',
                           f'simple_subject_{s.pk}'.encode())]
            for s in subjects]


def _service_buttons(services: list) -> list | None:
    """Build Telethon inline button rows for the service list (one per row)."""
    if not services:
        return None
    return [[Button.inline(f'{svc.icon_emoji} {svc.name}',
                           f'simple_service_{svc.pk}'.encode())]
            for svc in services]


async def _typing_loop_ub(client: TelegramClient, chat_id: int):
    """Continuously send typing action until cancelled."""
    try:
        while True:
            await client(functions.messages.SetTypingRequest(
                peer=chat_id, action=SendMessageTypingAction()
            ))
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def _ub_handle_subject_selected(client: TelegramClient, chat_id: int,
                                       uid: int, subject_id: int) -> None:
    """Show services for the chosen subject."""
    from core.models import Subject
    lang = get_state(uid).get('lang', 'en')
    try:
        subject = await run_sync(lambda: Subject.objects.get(pk=subject_id, is_active=True))
    except Exception:
        await client.send_message(chat_id, build_not_understood(lang))
        return
    services = await run_sync(lambda: get_services_for_subject(subject_id))
    if not services:
        await client.send_message(chat_id, build_no_services(lang))
        return
    text = build_service_list(lang, subject, services)
    buttons = _service_buttons(services)
    await client.send_message(chat_id, text, buttons=buttons or None)
    # Buffer service list so it appears in admin panel once the case is created
    pending = get_state(uid).get('pending_msgs', [])
    pending.append(('assistant', text))
    set_state(uid, step=STEP_SERVICE, subject_id=subject_id, pending_msgs=pending)


async def _ub_handle_service_selected(client: TelegramClient, chat_id: int,
                                       uid: int, sender, service_id: int) -> None:
    """Open/link a case and show the required items list."""
    from core.models import ServiceDefinition
    state = get_state(uid)
    lang = state.get('lang', 'en')
    try:
        svc_def = await run_sync(lambda: ServiceDefinition.objects.get(pk=service_id, is_active=True))
    except Exception:
        await client.send_message(chat_id, build_not_understood(lang))
        return
    db_user, _ = await run_sync(lambda: db_get_or_create_user(sender.id, sender.first_name,
                                                               getattr(sender, 'username', None)))
    case = await run_sync(lambda: db_get_or_open_case(db_user, svc_def.slug))
    await run_sync(lambda: db_link_case_to_service(case, svc_def, state.get('subject_id')))
    # Flush any user messages buffered before the case existed
    await run_sync(lambda: db_flush_pending_messages(case, uid))
    items = await run_sync(lambda: svc_def.get_collect_items() or svc_def.get_documents_list() or [])
    prompt = build_collect_prompt(lang, svc_def, items)
    await client.send_message(chat_id, prompt)
    await run_sync(lambda: case.add_message('assistant', prompt))
    set_state(uid, step=STEP_COLLECTING, service_id=service_id,
              case_id=case.pk, items_to_collect=items)


async def _ub_handle_collecting(client: TelegramClient, chat_id: int,
                                 uid: int, sender, text: str = None,
                                 file_label: str = None) -> None:
    """Accept text/file during collecting step; finalise on 'done'."""
    state = get_state(uid)
    lang = state.get('lang', 'en')
    case_id = state.get('case_id')

    if not case_id:
        clear_state(uid)
        subjects = await run_sync(get_active_subjects)
        await client.send_message(chat_id, build_greeting(lang, subjects),
                                  buttons=_subject_buttons(subjects) or None)
        set_state(uid, step=STEP_SUBJECT, lang=lang)
        return

    from core.models import Case
    try:
        case = await run_sync(lambda: Case.objects.get(pk=case_id))
    except Exception:
        clear_state(uid)
        return

    if text and await run_sync(lambda: is_done_message(text, lang)):
        final_msg = await run_sync(
            lambda: db_finalise_case(uid, sender.id, sender.first_name,
                                     getattr(sender, 'username', None), lang)
        )
        await client.send_message(chat_id, final_msg)
        return

    if text:
        await run_sync(lambda: case.add_message('user', text))
        # Check if the user is asking a clarifying question; if so, answer it
        svc_def = None
        svc_id = state.get('service_id')
        if svc_id:
            try:
                from core.models import ServiceDefinition
                svc_def = await run_sync(lambda: ServiceDefinition.objects.get(pk=svc_id))
            except Exception:
                pass
        ai_reply = await run_sync(lambda: ai_answer_question(text, svc_def, lang))
        if ai_reply:
            await run_sync(lambda: case.add_message('assistant', ai_reply))
            await client.send_message(chat_id, ai_reply)
        else:
            await client.send_message(chat_id, build_ack(lang))
    elif file_label:
        await run_sync(lambda: case.add_message('user', f'[{file_label}]'))
        await client.send_message(chat_id, build_ack(lang))


# ============== Handler Registration ==============

def register_handlers(client: TelegramClient, account_index: int):
    """Register event handlers for a client (simplified flow)."""
    _register_group_handlers(client, account_index)

    # ── /start ─────────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern='/start', incoming=True))
    async def handle_start(event):
        if not event.is_private:
            return
        try:
            sender = await event.get_sender()
            uid = sender.id
            await run_sync(lambda: _get_or_create_user(sender.id, sender.first_name, sender.username))
            await run_sync(lambda: _set_linked_account(sender.id, account_index))
            clear_state(uid)
            subjects = await run_sync(get_active_subjects)
            lang_fallback = 'en'
            lang = lang_fallback
            text = build_greeting(lang, subjects)
            buttons = _subject_buttons(subjects)
            await event.respond(text, buttons=buttons or None)
            set_state(uid, step=STEP_SUBJECT, lang=lang)
            logger.info(f"[Account {account_index}] /start (simple) from {sender.id}")
        except Exception as e:
            logger.error(f"Error in /start handler: {e}")

    # ── /help ──────────────────────────────────────────────────────────────────

    @client.on(events.NewMessage(pattern='/help', incoming=True))
    async def handle_help(event):
        if not event.is_private:
            return
        try:
            sender = await event.get_sender()
            user, _ = await run_sync(lambda: _get_or_create_user(sender.id))
            lang = user.language_code if user else 'en'
            await event.respond(t(lang, 'help'))
        except Exception as e:
            logger.error(f"Error in /help handler: {e}")

    # ── Subject inline button callback ────────────────────────────────────────

    @client.on(events.CallbackQuery(pattern=b'simple_subject_'))
    async def cb_subject(event):
        try:
            data = event.data.decode()
            subject_id = int(data.split('_')[-1])
            uid = event.sender_id
            await event.answer()
            await _ub_handle_subject_selected(client, event.chat_id, uid, subject_id)
        except Exception as e:
            logger.error(f"cb_subject error: {e}")

    # ── Service inline button callback ────────────────────────────────────────

    @client.on(events.CallbackQuery(pattern=b'simple_service_'))
    async def cb_service(event):
        try:
            data = event.data.decode()
            service_id = int(data.split('_')[-1])
            uid = event.sender_id
            sender = await event.get_sender()
            await event.answer()
            await _ub_handle_service_selected(client, event.chat_id, uid, sender, service_id)
        except Exception as e:
            logger.error(f"cb_service error: {e}")

    # ── Language callback (kept for compatibility) ─────────────────────────────

    @client.on(events.CallbackQuery(pattern=b'lang_'))
    async def handle_language_callback(event):
        from core.models import TgUser
        try:
            lang_code = event.data.decode().replace('lang_', '')
            sender_id = event.sender_id
            await run_sync(lambda: TgUser.objects.filter(telegram_id=sender_id).update(language_code=lang_code))
            set_state(sender_id, lang=lang_code)
            await event.edit(f"{t(lang_code, 'language_changed')}\n\n{t(lang_code, 'intro')}")
            await event.answer()
        except Exception as e:
            logger.error(f"Error in language callback: {e}")

    # ── Text messages ──────────────────────────────────────────────────────────

    @client.on(events.NewMessage(incoming=True))
    async def handle_text_message(event):
        if not event.is_private or not event.text or event.text.startswith('/') or event.media:
            return
        try:
            sender = await event.get_sender()
            uid = sender.id
            text = event.text.strip()

            # ── History detection ──────────────────────────────────────────────
            # If this user is not in our DB yet, check if there's an existing
            # Telegram conversation (≥3 messages). If yes, import the history
            # and let the consultant handle — do NOT reply with the simplified flow.
            user_existed = await run_sync(lambda: __user_exists_by_telegram_id(sender.id))
            if not user_existed:
                try:
                    hist = await client.get_messages(sender.id, limit=3)
                    if hist and len(hist) >= 3:
                        count, err = await fetch_and_save_chat(
                            client, str(sender.id), limit=3000, import_req_id=None
                        )
                        if not err:
                            await run_sync(lambda: _set_linked_account(sender.id, account_index))
                        logger.info(
                            '[Account %s] Existing history (%d msgs) for %s — imported, consultant handles',
                            account_index, count, sender.id,
                        )
                        return  # stay silent; consultant handles this chat
                except Exception as hist_err:
                    logger.debug('History detection error for %s: %s', sender.id, hist_err)

            # Ensure user exists; set linked account
            user, user_created = await run_sync(lambda: _get_or_create_user(
                sender.id, sender.first_name, sender.username
            ))
            await run_sync(lambda: _set_linked_account(sender.id, account_index))
            if user_created:
                try:
                    await fetch_telegram_profile_to_db(client, sender.id)
                except Exception:
                    pass

            # ── AI-disabled check ─────────────────────────────────────────────
            # If a consultant has taken over (ai_enabled=False on the case),
            # stay completely silent so the consultant can chat freely.
            if await run_sync(lambda: _check_ai_disabled(sender.id)):
                logger.debug('[Account %s] AI disabled for %s — skipping', account_index, sender.id)
                return

            state = get_state(uid)
            step = state.get('step', STEP_INIT)

            typing_task = asyncio.create_task(_typing_loop_ub(client, event.chat_id))
            try:
                # Only re-detect language on meaningful text; skip short/numeric
                # inputs (e.g. "1", "2") to avoid overwriting the stored language.
                stored_lang = state.get('lang', 'en')
                if len(text) > 3 and not text.isdigit():
                    lang = await run_sync(lambda: detect_lang(text, stored_lang))
                    set_state(uid, lang=lang)
                else:
                    lang = stored_lang

                # ── Consultant connect request (any active step) ───────────────
                if step not in (STEP_DONE, STEP_CONFIRM_CONSULTANT):
                    if await run_sync(lambda: wants_consultant(text, lang)):
                        set_state(uid, step=STEP_CONFIRM_CONSULTANT, prev_step=step)
                        await event.respond(build_consultant_confirm(lang))
                        return

                # ── Consultant confirmation ───────────────────────────────────
                if step == STEP_CONFIRM_CONSULTANT:
                    if is_confirm_yes(text):
                        final_msg = await run_sync(
                            lambda: db_finalise_case(uid, sender.id, sender.first_name,
                                                     getattr(sender, 'username', None), lang)
                        )
                        await event.respond(final_msg)
                    elif is_confirm_no(text):
                        prev = state.get('prev_step', STEP_COLLECTING)
                        set_state(uid, step=prev)
                        await event.respond(build_consultant_declined(lang))
                    else:
                        await event.respond(build_consultant_confirm(lang))
                    return

                if step in (STEP_INIT, ''):
                    # Buffer user's opening message AND bot greeting so full conversation is saved
                    pending = state.get('pending_msgs', [])
                    pending.append(('user', text))
                    subjects = await run_sync(get_active_subjects)
                    msg = build_greeting(lang, subjects)
                    pending.append(('assistant', msg))
                    buttons = _subject_buttons(subjects)
                    await event.respond(msg, buttons=buttons or None)
                    set_state(uid, step=STEP_SUBJECT, lang=lang, pending_msgs=pending)

                elif step == STEP_SUBJECT:
                    # Buffer this message too (user may type their subject name)
                    pending = state.get('pending_msgs', [])
                    pending.append(('user', text))
                    set_state(uid, pending_msgs=pending)
                    subjects = await run_sync(get_active_subjects)
                    matched_id = None
                    if text.isdigit():
                        idx = int(text) - 1
                        if 0 <= idx < len(subjects):
                            matched_id = subjects[idx].pk
                    if matched_id is None:
                        matched_id = await run_sync(lambda: ai_match_subject(text, subjects, lang))
                    if matched_id:
                        await _ub_handle_subject_selected(client, event.chat_id, uid, matched_id)
                    else:
                        options = [f'{s.icon_emoji} {s.get_name(lang)}' for s in subjects]
                        reply = await run_sync(lambda: ai_contextual_reply(text, options, STEP_SUBJECT, lang))
                        await event.respond(reply)

                elif step == STEP_SERVICE:
                    subject_id = state.get('subject_id')
                    services = await run_sync(lambda: get_services_for_subject(subject_id) if subject_id else [])
                    matched_id = None
                    if text.isdigit():
                        idx = int(text) - 1
                        if 0 <= idx < len(services):
                            matched_id = services[idx].pk
                    if matched_id is None:
                        matched_id = await run_sync(lambda: ai_match_service(text, services, lang))
                    if matched_id:
                        await _ub_handle_service_selected(client, event.chat_id, uid, sender, matched_id)
                    else:
                        options = [f'{svc.icon_emoji} {svc.name}' for svc in services]
                        reply = await run_sync(lambda: ai_contextual_reply(text, options, STEP_SERVICE, lang))
                        await event.respond(reply)

                elif step == STEP_COLLECTING:
                    await _ub_handle_collecting(client, event.chat_id, uid, sender, text=text)

                elif step == STEP_DONE:
                    await event.respond(build_already_submitted(lang))

            finally:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

            logger.info(f"[Account {account_index}] Simple text from {sender.id}: {text[:50]}")
        except Exception as e:
            logger.error(f"Error handling text message: {e}")

    # ── Media messages ─────────────────────────────────────────────────────────

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.media))
    async def handle_media(event):
        if not event.is_private or (event.text and event.text.startswith('/')):
            return
        try:
            sender = await event.get_sender()
            uid = sender.id

            # ── History detection (same logic as text handler) ─────────────────
            user_existed = await run_sync(lambda: __user_exists_by_telegram_id(sender.id))
            if not user_existed:
                try:
                    hist = await client.get_messages(sender.id, limit=3)
                    if hist and len(hist) >= 3:
                        count, err = await fetch_and_save_chat(
                            client, str(sender.id), limit=3000, import_req_id=None
                        )
                        if not err:
                            await run_sync(lambda: _set_linked_account(sender.id, account_index))
                        logger.info(
                            '[Account %s] Existing history for %s (media) — imported, consultant handles',
                            account_index, sender.id,
                        )
                        return
                except Exception as hist_err:
                    logger.debug('History detection error (media) for %s: %s', sender.id, hist_err)

            await run_sync(lambda: _get_or_create_user(sender.id, sender.first_name, sender.username))
            await run_sync(lambda: _set_linked_account(sender.id, account_index))

            # ── AI-disabled check ─────────────────────────────────────────────
            if await run_sync(lambda: _check_ai_disabled(sender.id)):
                logger.debug('[Account %s] AI disabled for %s (media) — skipping', account_index, sender.id)
                return

            state = get_state(uid)
            step = state.get('step', STEP_INIT)
            lang = _lang_from_sender(sender, state)
            lang_for_state = lang or 'en'

            if step != STEP_COLLECTING:
                subjects = await run_sync(get_active_subjects)
                msg = build_greeting(lang, subjects) if lang else build_greeting_universal(subjects)
                buttons = _subject_buttons(subjects)
                await event.respond(msg, buttons=buttons or None)
                # Buffer the sticker/media label + bot greeting so they flush into the case later
                if getattr(event, 'sticker', None):
                    media_label = '[Sticker]'
                elif getattr(event, 'photo', None):
                    media_label = '[Photo]'
                else:
                    media_label = '[Media]'
                pending = state.get('pending_msgs', [])
                pending.append(('user', media_label))
                pending.append(('assistant', msg))
                set_state(uid, step=STEP_SUBJECT, lang=lang_for_state, pending_msgs=pending)
                return

            case_id = state.get('case_id')
            if not case_id:
                clear_state(uid)
                subjects = await run_sync(get_active_subjects)
                msg = build_greeting(lang, subjects) if lang else build_greeting_universal(subjects)
                await event.respond(msg, buttons=_subject_buttons(subjects) or None)
                set_state(uid, step=STEP_SUBJECT, lang=lang_for_state)
                return

            # Determine media type and filename
            unique_id = str(uuid4())[:8]
            if isinstance(event.media, MessageMediaPhoto):
                ext = '.jpg'
                filename = f'{unique_id}{ext}'
                media_type = 'photo'
            elif isinstance(event.media, MessageMediaDocument):
                doc_tl = event.media.document
                mime = doc_tl.mime_type or ''
                ext = '.bin'
                for attr in (doc_tl.attributes or []):
                    if hasattr(attr, 'file_name') and attr.file_name:
                        ext = os.path.splitext(attr.file_name)[1] or '.bin'
                        break
                if mime.startswith('audio/') or any(getattr(a, 'voice', False) for a in (doc_tl.attributes or [])):
                    ext = ext if ext != '.bin' else '.ogg'
                    media_type = 'voice'
                elif mime.startswith('video/') or ext.lower() in ('.mp4', '.mov', '.avi', '.webm', '.mkv', '.m4v'):
                    media_type = 'video'
                else:
                    media_type = 'document'
                filename = f'{unique_id}{ext}'
            else:
                return

            filepath = UPLOADS_DIR / filename
            await client.download_media(event.media, filepath)

            # Persist Document record
            def _save_doc():
                from core.models import Case
                c = Case.objects.get(pk=case_id)
                return _create_document(
                    case_id, filename, ext.lstrip('.') or 'unknown',
                    unique_id, media_type,
                    display_name=f'{media_type}_{sender.id}{ext}',
                )
            doc_record = await run_sync(_save_doc)

            # .ogg voice note → transcribe and treat as text
            if media_type == 'voice' and ext.lower() == '.ogg':
                transcription = await run_sync(lambda: transcribe_voice(str(filepath), lang))
                if transcription:
                    def _save_transcription():
                        doc_record.transcription = transcription
                        doc_record.save(update_fields=['transcription'])
                        from core.models import Case
                        Case.objects.get(pk=case_id).add_message(
                            'user', f'[Voice note transcription]: {transcription}'
                        )
                    await run_sync(_save_transcription)
                    await _ub_handle_collecting(client, event.chat_id, uid, sender, text=transcription)
                    return

            # All other files
            await _ub_handle_collecting(
                client, event.chat_id, uid, sender,
                file_label=f'FILE:{unique_id}:{filename}:{media_type}',
            )
            logger.info(f"[Account {account_index}] Media from {sender.id}: {filename}")
        except Exception as e:
            logger.error(f"Error handling media: {e}")


# ============== Group Chat Monitoring ==============

def _register_group_handlers(client, account_index):
    """Register handlers for monitored group chats on a client."""

    @client.on(events.NewMessage(incoming=True))
    async def handle_group_message(event):
        # Only handle group/supergroup messages
        if not event.is_group:
            return

        chat_id = event.chat_id

        # Check if this group is tracked
        def get_group():
            from core.models import GroupChat
            return GroupChat.objects.filter(group_id=chat_id, is_active=True).first()

        group = await run_sync(get_group)
        if not group:
            return

        sender = await event.get_sender()
        if not sender or getattr(sender, 'bot', False):
            return

        user_id = sender.id
        lang = group.language
        text = (event.text or '').strip()

        try:
            # ---- Case 1: Someone replied to one of our messages ----
            if event.reply_to_msg_id:
                def check_bot_message():
                    from core.models import GroupBotMessage
                    return GroupBotMessage.objects.filter(
                        group=group, message_id=event.reply_to_msg_id
                    ).first()

                bot_msg = await run_sync(check_bot_message)
                if bot_msg:
                    original_user = bot_msg.triggered_by_user_id
                    if original_user and user_id == original_user:
                        # Original user replied → cancel their cooldown
                        def cancel_cooldown():
                            from core.models import GroupCooldown
                            GroupCooldown.objects.filter(group=group, user_tg_id=user_id).delete()
                        await run_sync(cancel_cooldown)
                        logger.info(f"[Group {chat_id}] User {user_id} replied → cooldown lifted")
                        return
                    else:
                        # Someone else replied → answer briefly + DM redirect
                        if not text:
                            return
                        reply_text = await run_sync(
                            lambda: group_answer_question(text, group.behavior_prompt, lang)
                        )
                        if reply_text:
                            sent = await event.reply(reply_text)
                            def save_bot_msg_reply():
                                from core.models import GroupBotMessage
                                GroupBotMessage.objects.get_or_create(
                                    group=group, message_id=sent.id,
                                    defaults={'triggered_by_user_id': user_id}
                                )
                            await run_sync(save_bot_msg_reply)
                            logger.info(f"[Group {chat_id}] Answered follow-up from {user_id}")
                        return

            # ---- Case 2: Regular message — check cooldown ----
            def check_cooldown():
                from core.models import GroupCooldown
                from datetime import datetime as _dt
                cd = GroupCooldown.objects.filter(group=group, user_tg_id=user_id).first()
                if cd:
                    expires = cd.expires_at.replace(tzinfo=None) if cd.expires_at.tzinfo else cd.expires_at
                    if _dt.now() < expires:
                        return True  # still in cooldown
                    cd.delete()
                return False

            in_cooldown = await run_sync(check_cooldown)
            if in_cooldown:
                return

            if not text:
                return

            # ---- Case 3: Detect if message is about our services ----
            is_relevant = await run_sync(
                lambda: group_is_relevant(text, group.behavior_prompt)
            )
            if not is_relevant:
                return

            # ---- Respond with DM invitation ----
            invite = group_dm_invite_message(lang)
            sent = await event.reply(invite)

            # Track bot message + set cooldown
            def save_cooldown_and_msg():
                from core.models import GroupBotMessage, GroupCooldown
                from datetime import datetime as _dt, timedelta
                GroupBotMessage.objects.get_or_create(
                    group=group, message_id=sent.id,
                    defaults={'triggered_by_user_id': user_id}
                )
                expires = _dt.now() + timedelta(hours=group.cooldown_hours)
                GroupCooldown.objects.update_or_create(
                    group=group, user_tg_id=user_id,
                    defaults={'expires_at': expires}
                )

            await run_sync(save_cooldown_and_msg)
            logger.info(f"[Group {chat_id}] Invited {user_id} to DM, cooldown {group.cooldown_hours}h")

        except Exception as e:
            logger.error(f"[Group {chat_id}] Error in group handler: {e}")


# ============== Queue Processing ==============

async def send_queue_loop(clients: list):
    """Process pending send queue (text and voice messages)."""
    from core.models import PendingSend

    while True:
        try:
            await asyncio.sleep(3)

            for idx, client in enumerate(clients):
                if not client:
                    continue

                def get_pending():
                    return list(PendingSend.objects.filter(
                        sent=False,
                        account_index=idx
                    )[:10])

                pending = await run_sync(get_pending)

                for msg in pending:
                    try:
                        if msg.send_type == PendingSend.SEND_TYPE_VOICE and msg.voice_file:
                            await _send_voice_pending(client, msg)
                        else:
                            await client.send_message(int(msg.user_tg_id), msg.message)

                        def mark_sent():
                            msg.sent = True
                            msg.sent_at = datetime.now()
                            msg.save(update_fields=['sent', 'sent_at'])

                        await run_sync(mark_sent)
                        logger.info(f"Sent pending {'voice' if msg.send_type == 'voice' else 'text'} to {msg.user_tg_id}")

                    except Exception as e:
                        logger.error(f"Error sending to {msg.user_tg_id}: {e}")

        except Exception as e:
            logger.error(f"Error in send queue loop: {e}")


async def _send_voice_pending(client: TelegramClient, msg):
    """Send a voice note stored in PendingSend.voice_file to the Telegram user."""
    import os
    import subprocess
    import tempfile
    from telethon.tl.types import DocumentAttributeAudio

    voice_path = msg.voice_file.path  # absolute path on disk

    # Convert to OGG/Opus if needed (browsers may record as webm/opus or wav)
    final_path = voice_path
    needs_cleanup = False
    ext = os.path.splitext(voice_path)[1].lower()

    if ext not in ('.ogg', '.oga'):
        tmp = tempfile.NamedTemporaryFile(suffix='.ogg', delete=False)
        tmp.close()
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', voice_path, '-c:a', 'libopus', '-b:a', '64k', tmp.name],
                capture_output=True, timeout=30, check=True,
            )
            final_path = tmp.name
            needs_cleanup = True
        except Exception as e:
            logger.warning(f"ffmpeg conversion failed for voice, sending as-is: {e}")
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    try:
        await client.send_file(
            int(msg.user_tg_id),
            file=final_path,
            voice_note=True,  # marks as voice message in Telegram
            attributes=[
                DocumentAttributeAudio(
                    duration=0,
                    voice=True,
                    title=None,
                    performer=None,
                    waveform=None,
                )
            ],
        )
    finally:
        if needs_cleanup and os.path.exists(final_path):
            os.unlink(final_path)


async def import_queue_loop(clients: list):
    """Process import requests using the first available client."""
    from core.models import ImportRequest

    while True:
        try:
            await asyncio.sleep(5)

            # Pick first connected client
            active_client = next((c for c in clients if c is not None), None)
            if active_client is None:
                continue

            def get_pending():
                return list(ImportRequest.objects.filter(status='pending')[:5])

            pending = await run_sync(get_pending)

            for req in pending:
                try:
                    def mark_processing():
                        req.status = 'processing'
                        req.save(update_fields=['status'])

                    await run_sync(mark_processing)

                    await process_import(active_client, req.pk, req.user_tg_id)

                except Exception as e:
                    logger.error(f"Error processing import {req.pk}: {e}")

                    def mark_error():
                        req.status = 'error'
                        req.error_msg = str(e)
                        req.save(update_fields=['status', 'error_msg'])

                    await run_sync(mark_error)

        except Exception as e:
            logger.error(f"Error in import queue loop: {e}")


async def fetch_and_save_chat(client: TelegramClient, user_tg_id: str, limit: int = 3000, import_req_id: int = None):
    """
    Fetch chat history with peer, save to DB: get_or_create user, create case with conversation.
    Downloads voice and photo attachments so they appear as playable media in the panel.
    If there was any prior chat (len(conversation) > 0), set ai_enabled=False. Run profile extraction.
    Returns (message_count, error_str). If import_req_id is set, update that ImportRequest.
    """
    from core.models import TgUser, Case, ImportRequest
    import uuid as _uuid
    import os as _os
    from django.conf import settings as _settings

    try:
        peer = int(user_tg_id) if user_tg_id.isdigit() else user_tg_id
        messages = await client.get_messages(peer, limit=limit)
        messages = list(reversed(messages))

        media_root = getattr(_settings, 'MEDIA_ROOT', 'uploads')
        _os.makedirs(media_root, exist_ok=True)

        # Each entry: (role, content, timestamp, doc_info_or_None)
        # doc_info = {'uid': str, 'filename': str, 'media_type': str} when media was downloaded
        raw_entries = []

        for msg in messages:
            if not msg.text and not msg.media:
                continue
            role = _telegram_message_role(msg)
            ts = msg.date.isoformat() if msg.date else datetime.now().isoformat()

            if msg.text:
                raw_entries.append((role, msg.text, ts, None))
                continue

            # Media message — try to classify and download
            media = msg.media
            media_type = None
            try:
                from telethon.tl.types import (
                    MessageMediaPhoto, MessageMediaDocument,
                    DocumentAttributeAudio, DocumentAttributeSticker,
                )
                if isinstance(media, MessageMediaPhoto):
                    media_type = 'photo'
                elif isinstance(media, MessageMediaDocument) and media.document:
                    attrs = media.document.attributes or []
                    if any(isinstance(a, DocumentAttributeSticker) for a in attrs):
                        media_type = 'sticker'
                    elif any(isinstance(a, DocumentAttributeAudio) and getattr(a, 'voice', False) for a in attrs):
                        media_type = 'voice'
                    elif any(isinstance(a, DocumentAttributeAudio) for a in attrs):
                        media_type = 'audio'
                    else:
                        media_type = 'document'
            except Exception:
                media_type = 'document'

            if media_type == 'sticker':
                raw_entries.append((role, '[Sticker]', ts, None))
                continue

            # Download voice and photo files; skip other media to keep import fast
            if media_type in ('voice', 'photo'):
                try:
                    ext = '.ogg' if media_type == 'voice' else '.jpg'
                    uid = _uuid.uuid4().hex
                    filename = f"import_{media_type}_{uid}{ext}"
                    dest = _os.path.join(media_root, filename)
                    await client.download_media(msg, file=dest)
                    raw_entries.append((role, f'[FILE:{uid}:{filename}:{media_type}]', ts,
                                        {'uid': uid, 'filename': filename, 'media_type': media_type}))
                    continue
                except Exception as e:
                    logger.warning(f"Could not download {media_type} during import: {e}")

            label = {'photo': '[Photo]', 'audio': '[Audio]', 'document': '[Document]'}.get(media_type, '[Attachment]')
            raw_entries.append((role, label, ts, None))

        conversation = [
            {'role': r, 'content': c, 'timestamp': t}
            for r, c, t, _ in raw_entries
        ]
        downloaded_docs = [(r, c, t, d) for r, c, t, d in raw_entries if d]
        
        def save_import():
            from core.models import Document as _Document
            try:
                tg_id = int(user_tg_id)
            except ValueError:
                return 0, "Invalid Telegram ID"

            user, _ = TgUser.objects.get_or_create(
                telegram_id=tg_id,
                defaults={'language_code': 'en'}
            )
            # Re-import: replace conversation on existing active case
            existing = Case.objects.filter(user=user, status='active').order_by('-updated_at').first()
            if existing:
                existing.conversation_history = json.dumps(conversation)
                existing.ai_enabled = False
                existing.save(update_fields=['conversation_history', 'ai_enabled', 'updated_at'])
                case = existing
            else:
                case = Case.objects.create(
                    user=user,
                    service='general',
                    status='active',
                    conversation_history=json.dumps(conversation),
                    ai_enabled=False
                )

            # Create Document records for downloaded media so panel can serve them
            existing_uids = set(
                _Document.objects.filter(case=case, file_unique_id__isnull=False)
                .values_list('file_unique_id', flat=True)
            )
            for _, _, _, doc_info in downloaded_docs:
                if doc_info['uid'] in existing_uids:
                    continue
                _Document.objects.create(
                    case=case,
                    file_path=doc_info['filename'],
                    display_name=doc_info['filename'],
                    telegram_file_id=f"local:{doc_info['filename']}",
                    file_unique_id=doc_info['uid'],
                    media_type=doc_info['media_type'],
                )

            if import_req_id:
                req = ImportRequest.objects.get(pk=import_req_id)
                req.status = 'done'
                req.message_count = len(conversation)
                req.completed_at = datetime.now()
                req.save()
            # Analyze chat with AI (profile extraction)
            try:
                from bot.services import update_user_profile
                update_user_profile(user.pk, force=True)
            except Exception as e:
                logger.debug(f"Profile extraction after import: {e}")
            return len(conversation), None
        
        count, error = await run_sync(save_import)
        if error:
            return count, error
        # Fetch Telegram profile (photo, bio, username, name) for the user
        try:
            await fetch_telegram_profile_to_db(client, peer)
        except Exception as e:
            logger.debug(f"Profile fetch after import: {e}")
        return count, None
    except Exception as e:
        logger.error(f"fetch_and_save_chat error: {e}")
        return 0, str(e)


async def process_import(client: TelegramClient, req_id: int, user_tg_id: str):
    """Process a single import request (from panel Add User or Import Chat queue)."""
    from core.models import ImportRequest

    def _mark_error(msg: str):
        try:
            req = ImportRequest.objects.get(pk=req_id)
            req.status = 'error'
            req.error_msg = msg[:500]
            req.save(update_fields=['status', 'error_msg'])
        except Exception as ex:
            logger.warning(f"Could not mark import {req_id} as error: {ex}")

    try:
        count, error = await fetch_and_save_chat(client, user_tg_id, limit=3000, import_req_id=req_id)
        if error:
            await run_sync(lambda: _mark_error(error))
            raise Exception(error)
        logger.info(f"Imported {count} messages for {user_tg_id}")
    except Exception as e:
        err_msg = str(e)
        # Entity-not-found: the account hasn't seen this user. Mark as error but don't crash the loop.
        if 'Could not find the input entity' in err_msg or 'PeerUser' in err_msg:
            logger.warning(
                f"process_import: Telegram entity not found for {user_tg_id}. "
                f"The userbot account needs to have chatted with this user first. Marking as error."
            )
            await run_sync(lambda: _mark_error(
                f"Telegram entity not found: the userbot account has not interacted with user {user_tg_id} yet. "
                f"Ask them to send a message first, then retry Fix Chat."
            ))
            return  # don't re-raise; let the queue continue to next pending import
        logger.error(f"Import error for {user_tg_id}: {e}")
        raise


# ============== Chat Import Function ==============

async def import_chat(client: TelegramClient, user_tg_id: str, limit: int = 100) -> dict:
    """
    Import chat history with a specific user.
    
    Args:
        client: Telethon client
        user_tg_id: Telegram user ID or username
        limit: Maximum messages to import
        
    Returns:
        Dictionary with status and message count
    """
    from core.models import TgUser, Case
    
    try:
        # Get messages
        peer = int(user_tg_id) if user_tg_id.isdigit() else user_tg_id
        messages = await client.get_messages(peer, limit=limit)
        
        # Reverse to chronological order
        messages = list(reversed(messages))
        
        # Build conversation (same role rule as fetch_and_save_chat)
        conversation = []
        for msg in messages:
            if not msg.text:
                continue
            role = _telegram_message_role(msg)
            conversation.append({
                'role': role,
                'content': msg.text,
                'timestamp': msg.date.isoformat() if msg.date else datetime.now().isoformat()
            })
        
        # Save: replace existing active case conversation for re-import, else create new case
        def save():
            tg_id = int(user_tg_id) if user_tg_id.isdigit() else 0
            if not tg_id:
                return {'ok': False, 'error': 'Invalid Telegram ID'}
            
            user, _ = TgUser.objects.get_or_create(
                telegram_id=tg_id,
                defaults={'language_code': 'en'}
            )
            existing = Case.objects.filter(user=user, status='active').order_by('-updated_at').first()
            if existing:
                existing.conversation_history = json.dumps(conversation)
                existing.save(update_fields=['conversation_history', 'updated_at'])
            else:
                Case.objects.create(
                    user=user,
                    service='general',
                    status='active',
                    conversation_history=json.dumps(conversation)
                )
            return {'ok': True, 'count': len(conversation)}
        
        result = await run_sync(save)
        return result
        
    except Exception as e:
        logger.error(f"Chat import error: {e}")
        return {'ok': False, 'error': str(e)}


# ============== Main Entry Point ==============

def _session_file_exists(session_name: str) -> bool:
    """Check if a Telethon session file exists (e.g. userbot.session)."""
    base = SESSIONS_DIR / session_name
    return (base.with_suffix('.session')).exists()


async def main():
    """Main entry point for userbot."""
    global ACTIVE_CLIENTS
    tasks = []
    
    if not API_ID or not API_HASH:
        logger.error("TG_API_ID and TG_API_HASH must be configured in .env")
        return
    
    if not PHONE or not str(PHONE).strip():
        logger.error("TG_PHONE must be set in .env for account 1")
        return
    
    if not _session_file_exists('userbot'):
        logger.error(
            "Session not found. Authenticate account 1 first:  python manage.py run_userbot --auth  (then enter code sent to %s)",
            PHONE,
        )
        return
    
    logger.info("Starting Brightway Consulting Userbot...")
    
    # Create clients
    client1 = TelegramClient(
        str(SESSIONS_DIR / 'userbot'),
        int(API_ID),
        API_HASH
    )
    
    client2 = None
    if PHONE_2 and len(PHONE_2) > 5 and API_ID_2 and API_HASH_2:
        client2 = TelegramClient(
            str(SESSIONS_DIR / 'userbot2'),
            int(API_ID_2),
            API_HASH_2
        )
    elif PHONE_2 and len(PHONE_2) > 5:
        logger.error("Account 2 phone is set but TG_API_ID_2 / TG_API_HASH_2 are missing in .env — skipping account 2")
    
    try:
        # Connect client 1 (uses existing session)
        await client1.start(phone=PHONE)
        ACTIVE_CLIENTS.append(client1)
        register_handlers(client1, 0)
        logger.info("Client 1 connected")
        
        # Connect client 2 if configured
        if client2 and PHONE_2:
            if _session_file_exists('userbot2'):
                try:
                    await client2.start(phone=PHONE_2)
                    register_handlers(client2, 1)
                    ACTIVE_CLIENTS.append(client2)
                    logger.info("Client 2 connected")
                except Exception as e2:
                    logger.error("Client 2 failed: %s - continuing with account 1 only", e2)
                    ACTIVE_CLIENTS.append(None)
            else:
                logger.warning("Account 2 not authenticated. Run: python manage.py run_userbot --auth2")
                ACTIVE_CLIENTS.append(None)
        else:
            ACTIVE_CLIENTS.append(None)
            logger.info("Client 2 not configured - skipping")
        
        # Start background tasks
        tasks = [
            asyncio.create_task(send_queue_loop(ACTIVE_CLIENTS)),
            asyncio.create_task(import_queue_loop(ACTIVE_CLIENTS)),
        ]

        logger.info("Userbot running...")

        # Run all connected clients concurrently; stop when all disconnect
        run_tasks = [
            asyncio.create_task(c.run_until_disconnected())
            for c in ACTIVE_CLIENTS if c is not None
        ]
        await asyncio.gather(*run_tasks)
        
    except Exception as e:
        logger.error("Userbot error: %s", e)
        if "session" in str(e).lower() or "connect" in str(e).lower():
            logger.error("Try authenticating first:  python manage.py run_userbot --auth")
    finally:
        for task in tasks:
            task.cancel()


def authenticate(account: int = 1):
    """Authenticate a userbot account."""
    import asyncio
    
    if not API_ID or not API_HASH:
        print("Error: TG_API_ID and TG_API_HASH must be configured in .env")
        return
    
    if account == 1:
        phone = PHONE
        session_name = 'userbot'
        api_id = API_ID
        api_hash = API_HASH
    else:
        phone = PHONE_2
        session_name = 'userbot2'
        api_id = API_ID_2
        api_hash = API_HASH_2

    if not phone:
        print(f"Error: TG_PHONE{'_2' if account == 2 else ''} must be configured in .env")
        return

    if not api_id or not api_hash:
        print(f"Error: TG_API_ID{'_2' if account == 2 else ''} and TG_API_HASH{'_2' if account == 2 else ''} must be configured in .env")
        return

    async def auth():
        client = TelegramClient(
            str(SESSIONS_DIR / session_name),
            int(api_id),
            api_hash
        )
        
        await client.start(phone=phone)
        me = await client.get_me()
        print(f"Authenticated as: {me.first_name} (@{me.username})")
        await client.disconnect()
    
    asyncio.run(auth())


def run_userbot():
    """Run the userbot."""
    asyncio.run(main())


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Brightway Consulting Userbot')
    parser.add_argument('--auth', action='store_true', help='Authenticate account 1')
    parser.add_argument('--auth2', action='store_true', help='Authenticate account 2')
    args = parser.parse_args()
    
    if args.auth:
        authenticate(1)
    elif args.auth2:
        authenticate(2)
    else:
        run_userbot()
