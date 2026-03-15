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
    READY_FOR_CONSULTANT_MARKER,
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


# ============== Handler Registration ==============

def register_handlers(client: TelegramClient, account_index: int):
    """Register event handlers for a client."""
    
    @client.on(events.NewMessage(pattern='/start', incoming=True))
    async def handle_start(event):
        """Handle /start command."""
        if not event.is_private:
            return
        
        try:
            sender = await event.get_sender()
            
            # Create/update user in database
            user, _ = await run_sync(lambda: _get_or_create_user(
                sender.id, sender.first_name, sender.username
            ))
            
            # Set linked account
            await run_sync(lambda: _set_linked_account(sender.id, account_index))
            
            # Get language
            lang = user.language_code if user else 'en'
            
            # Send welcome with language buttons
            await event.respond(
                t(lang, 'welcome'),
                buttons=get_language_buttons()
            )
            
            logger.info(f"[Account {account_index}] /start from {sender.id}")
            
        except Exception as e:
            logger.error(f"Error in /start handler: {e}")
    
    @client.on(events.NewMessage(pattern='/help', incoming=True))
    async def handle_help(event):
        """Handle /help command."""
        if not event.is_private:
            return
        
        try:
            sender = await event.get_sender()
            user, _ = await run_sync(lambda: _get_or_create_user(sender.id))
            lang = user.language_code if user else 'en'
            
            await event.respond(t(lang, 'help'))
            
        except Exception as e:
            logger.error(f"Error in /help handler: {e}")
    
    @client.on(events.NewMessage(pattern='/mycase', incoming=True))
    async def handle_mycase(event):
        """Handle /mycase command."""
        from core.models import Case, Document
        
        if not event.is_private:
            return
        
        try:
            sender = await event.get_sender()
            user, _ = await run_sync(lambda: _get_or_create_user(sender.id))
            lang = user.language_code if user else 'en'
            
            # Get active case
            def get_case_info():
                case = Case.objects.filter(user=user, status='active').first()
                if not case:
                    return None
                doc_count = Document.objects.filter(case=case).count()
                return {
                    'service': case.service,
                    'status': case.status,
                    'payment': case.payment_status,
                    'doc_count': doc_count,
                    'created': case.created_at.strftime('%Y-%m-%d')
                }
            
            case_info = await run_sync(get_case_info)
            
            if not case_info:
                await event.respond(t(lang, 'case_none'))
            else:
                await event.respond(t(lang, 'case_info', **case_info))
            
        except Exception as e:
            logger.error(f"Error in /mycase handler: {e}")
    
    @client.on(events.CallbackQuery(pattern=b'lang_'))
    async def handle_language_callback(event):
        """Handle language selection callback."""
        from core.models import TgUser
        
        try:
            lang_code = event.data.decode().replace('lang_', '')
            sender_id = event.sender_id
            
            # Update user language
            def update_lang():
                TgUser.objects.filter(telegram_id=sender_id).update(language_code=lang_code)
            
            await run_sync(update_lang)
            
            # Edit message with intro
            intro = t(lang_code, 'intro')
            await event.edit(f"{t(lang_code, 'language_changed')}\n\n{intro}")
            await event.answer()
            
            logger.info(f"[Account {account_index}] User {sender_id} changed lang to {lang_code}")
            
        except Exception as e:
            logger.error(f"Error in language callback: {e}")
    
    @client.on(events.NewMessage(incoming=True))
    async def handle_text_message(event):
        """Handle text messages."""
        # Skip commands and non-private messages
        if not event.is_private or event.text.startswith('/') or event.media:
            return
        
        try:
            sender = await event.get_sender()
            text = event.text.strip()
            
            # If we don't have this user yet, check Telegram chat history first
            user_exists = await run_sync(lambda: __user_exists_by_telegram_id(sender.id))
            if not user_exists:
                # Only import if there was real prior chat (≥3 messages). With 1–2 messages it's usually the first contact message (e.g. "Привет") and we must not treat as prior chat or AI will be off from the start.
                try:
                    hist = await client.get_messages(sender.id, limit=3)
                    if hist and len(hist) >= 3:
                        # Prior chat exists: import it, create user+case with ai_enabled=False, analyze with AI
                        count, err = await fetch_and_save_chat(client, str(sender.id), limit=3000, import_req_id=None)
                        if not err:
                            await run_sync(lambda: _set_linked_account(sender.id, account_index))
                            # Append current message to the new case (it wasn't in the fetched history yet)
                            def add_current_message():
                                from core.models import TgUser, Case
                                u = TgUser.objects.get(telegram_id=sender.id)
                                c = Case.objects.filter(user=u, status='active').order_by('-updated_at').first()
                                if c:
                                    c.add_message('user', text)
                            await run_sync(add_current_message)
                            logger.info(f"[Account {account_index}] New contact {sender.id} had prior chat; imported {count} messages, AI off")
                        # No reply; consultant will handle
                        return
                except Exception as e:
                    logger.debug(f"History check for {sender.id}: {e}")
                # No prior chat: treat as really new user (AI on)
            
            # Get or create user
            user, user_created = await run_sync(lambda: _get_or_create_user(
                sender.id, sender.first_name, sender.username
            ))
            
            # Set linked account
            await run_sync(lambda: _set_linked_account(sender.id, account_index))
            
            # Fetch Telegram profile (photo, bio, username) when user is new
            if user_created:
                try:
                    await fetch_telegram_profile_to_db(client, sender.id)
                except Exception as e:
                    logger.debug(f"Profile fetch for new user: {e}")
            
            lang = user.language_code if user else 'en'
            
            # Detect service with AI (Django ORM — must run in thread from async context)
            detected = await run_sync(lambda: ai_detect_service(text))
            
            # Get or create case (do not add user message yet — we may send opening first)
            case = await run_sync(lambda: _get_or_open_case(user, detected or 'general'))
            conv = case.get_conversation()
            is_first_message = len(conv) == 0
            # New user (no prior messages / no imported chat): send only the opening; AI replies when they answer
            if is_first_message:
                from bot.messages import OPENING_MESSAGE
                await run_sync(lambda: _add_message_to_case(case.pk, 'assistant', OPENING_MESSAGE))
                await event.respond(OPENING_MESSAGE)
            await run_sync(lambda: _add_message_to_case(case.pk, 'user', text))

            # After first message we only sent the opening — no AI reply until user replies to it
            if is_first_message:
                logger.info(f"[Account {account_index}] First message from {sender.id}: sent opening only")
                return

            # If AI is turned off for this case, no reply (consultant will reply later)
            if not getattr(case, 'ai_enabled', True):
                return

            # Show typing while AI is generating (Telegram typing lasts ~5s, repeat every 4s)
            async def typing_loop():
                while True:
                    await client(functions.messages.SetTypingRequest(peer=event.chat_id, action=SendMessageTypingAction()))
                    await asyncio.sleep(4)

            get_ai_response_sync = lambda: ask_ai(case.get_conversation(), case.service, lang)
            typing_task = asyncio.create_task(typing_loop())
            try:
                reply = await run_sync(get_ai_response_sync)
            finally:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

            if reply:
                # Strip consultant-assignment marker and auto-disable AI when info collected
                to_store = reply.replace(READY_FOR_CONSULTANT_MARKER, '').strip()
                to_send = to_store
                if READY_FOR_CONSULTANT_MARKER in reply:
                    def assign_and_disable_ai():
                        from core.models import Case
                        from bot.bot import try_assign_case_to_consultant
                        c = Case.objects.get(pk=case.pk)
                        conv = c.get_conversation()
                        # Only turn off AI when conversation is long enough (avoid first-reply mistake)
                        if len(conv) >= 4:
                            try_assign_case_to_consultant(c, user)
                            c.ai_enabled = False
                            c.save(update_fields=['ai_enabled'])
                    await run_sync(assign_and_disable_ai)
                # Save and send response
                await run_sync(lambda: _add_message_to_case(case.pk, 'assistant', to_send))
                await event.respond(to_send)
                # Run profile extraction after every user message (throttled inside update_user_profile)
                if user and should_update_profile(len(case.get_conversation())):
                    try:
                        await run_sync(lambda: update_user_profile(user.pk, force=False))
                    except Exception as e:
                        logger.debug(f"Profile update skipped or failed: {e}")
            else:
                await event.respond(t(lang, 'ai_error'))
            
            logger.info(f"[Account {account_index}] Message from {sender.id}: {text[:50]}...")
            
        except Exception as e:
            logger.error(f"Error handling text message: {e}")
    
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.media))
    async def handle_media(event):
        """Handle media messages (photos, documents, voice, stickers)."""
        if not event.is_private or (event.text and event.text.startswith('/')):
            return
        
        try:
            sender = await event.get_sender()
            
            # If new user, check for prior chat (same as text handler): need ≥3 messages to avoid treating first contact as prior chat
            user_exists = await run_sync(lambda: __user_exists_by_telegram_id(sender.id))
            if not user_exists:
                try:
                    hist = await client.get_messages(sender.id, limit=3)
                    if hist and len(hist) >= 3:
                        count, err = await fetch_and_save_chat(client, str(sender.id), limit=3000, import_req_id=None)
                        if not err:
                            await run_sync(lambda: _set_linked_account(sender.id, account_index))
                            label = _first_media_label(event.media)
                            def add_first_media():
                                from core.models import TgUser, Case
                                u = TgUser.objects.get(telegram_id=sender.id)
                                c = Case.objects.filter(user=u, status='active').order_by('-updated_at').first()
                                if c:
                                    c.add_message('user', label)
                            await run_sync(add_first_media)
                            logger.info(f"[Account {account_index}] New contact {sender.id} sent media first; imported {count} messages")
                        return
                except Exception as e:
                    logger.debug(f"History check for {sender.id}: {e}")
            
            user, _ = await run_sync(lambda: _get_or_create_user(
                sender.id, sender.first_name, sender.username
            ))
            await run_sync(lambda: _set_linked_account(sender.id, account_index))
            
            lang = user.language_code if user else 'en'
            case = await run_sync(lambda: _get_or_open_case(user, 'general'))
            conv = await run_sync(lambda: case.get_conversation())
            
            # First message (any media): send opening only, no AI, no download
            if len(conv) == 0:
                from bot.messages import OPENING_MESSAGE
                await run_sync(lambda: _add_message_to_case(case.pk, 'assistant', OPENING_MESSAGE))
                await event.respond(OPENING_MESSAGE)
                label = _first_media_label(event.media)
                await run_sync(lambda: _add_message_to_case(case.pk, 'user', label))
                logger.info(f"[Account {account_index}] First message from {sender.id} was media ({label}): sent opening only")
                return
            
            # Download media
            unique_id = str(uuid4())[:8]
            
            if isinstance(event.media, MessageMediaPhoto):
                # Photo
                ext = '.jpg'
                filename = f"{unique_id}{ext}"
                media_type = 'photo'
                msg_key = 'photo_received'
            elif isinstance(event.media, MessageMediaDocument):
                # Document, voice, or video
                doc = event.media.document
                mime = doc.mime_type or ''
                ext = '.bin'
                for attr in doc.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        ext = os.path.splitext(attr.file_name)[1] or '.bin'
                        break
                if mime.startswith('audio/') or any(getattr(attr, 'voice', False) for attr in (doc.attributes or [])):
                    ext = ext if ext != '.bin' else '.ogg'
                    media_type = 'voice'
                    msg_key = 'voice_received'
                elif mime.startswith('video/') or ext.lower() in ('.mp4', '.mov', '.avi', '.webm', '.mkv', '.m4v'):
                    media_type = 'video'
                    msg_key = 'doc_received'
                else:
                    media_type = 'document'
                    msg_key = 'doc_received'
                filename = f"{unique_id}{ext}"
            else:
                return
            
            # Download file
            filepath = UPLOADS_DIR / filename
            await client.download_media(event.media, filepath)
            
            # Add to conversation first so suggest_document_name has context
            await run_sync(lambda: _add_message_to_case(
                case.pk, 'user', f"[FILE:{unique_id}:{filename}:{media_type}]"
            ))
            # Suggest display name and create document record (refetch case so conversation includes the file message)
            def create_doc_with_name():
                from core.models import Case
                c = Case.objects.get(pk=case.pk)
                conv = c.get_conversation()
                suggested = suggest_document_name(conv, media_type, sender.id, ext)
                display = f"{suggested}_{sender.id}{ext}" if suggested else f"{media_type}_{sender.id}{ext}"
                return _create_document(
                    case.pk, filename, os.path.splitext(filename)[1].lstrip('.') or 'unknown',
                    unique_id, media_type, display_name=display
                )
            doc = await run_sync(create_doc_with_name)

            # Acknowledge
            await event.respond(t(lang, msg_key))

            # Show typing while AI is generating
            async def typing_loop_media():
                while True:
                    await client(functions.messages.SetTypingRequest(peer=event.chat_id, action=SendMessageTypingAction()))
                    await asyncio.sleep(4)

            def get_ai_and_maybe_rename():
                conv = case.get_conversation()
                reply = ask_ai(conv, case.service, lang)
                if not reply:
                    return None, None
                cleaned, filename_label = parse_filename_from_response(reply)
                cleaned = cleaned.strip()
                if filename_label and doc:
                    doc.display_name = f"{filename_label}_{sender.id}{ext}"
                    doc.save(update_fields=['display_name'])
                return cleaned, None

            typing_task = asyncio.create_task(typing_loop_media())
            try:
                reply, _ = await run_sync(get_ai_and_maybe_rename)
            finally:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass
            if reply:
                await run_sync(lambda: _add_message_to_case(case.pk, 'assistant', reply))
                await event.respond(reply)
            
            logger.info(f"[Account {account_index}] Media from {sender.id}: {filename}")
            
        except Exception as e:
            logger.error(f"Error handling media: {e}")


# ============== Queue Processing ==============

async def send_queue_loop(clients: list):
    """Process pending send queue."""
    from core.models import PendingSend
    
    while True:
        try:
            await asyncio.sleep(3)
            
            for idx, client in enumerate(clients):
                if not client:
                    continue
                
                # Get pending messages for this account
                def get_pending():
                    return list(PendingSend.objects.filter(
                        sent=False,
                        account_index=idx
                    )[:10])
                
                pending = await run_sync(get_pending)
                
                for msg in pending:
                    try:
                        # Send message
                        await client.send_message(int(msg.user_tg_id), msg.message)
                        
                        # Mark as sent
                        def mark_sent():
                            msg.sent = True
                            msg.sent_at = datetime.now()
                            msg.save(update_fields=['sent', 'sent_at'])
                        
                        await run_sync(mark_sent)
                        logger.info(f"Sent pending message to {msg.user_tg_id}")
                        
                    except Exception as e:
                        logger.error(f"Error sending message to {msg.user_tg_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error in send queue loop: {e}")


async def import_queue_loop(client: TelegramClient):
    """Process import requests."""
    from core.models import ImportRequest
    
    while True:
        try:
            await asyncio.sleep(5)
            
            # Get pending imports
            def get_pending():
                return list(ImportRequest.objects.filter(status='pending')[:5])
            
            pending = await run_sync(get_pending)
            
            for req in pending:
                try:
                    # Mark as processing
                    def mark_processing():
                        req.status = 'processing'
                        req.save(update_fields=['status'])
                    
                    await run_sync(mark_processing)
                    
                    # Process import
                    await process_import(client, req.pk, req.user_tg_id)
                    
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
    If there was any prior chat (len(conversation) > 0), set ai_enabled=False. Run profile extraction.
    Returns (message_count, error_str). If import_req_id is set, update that ImportRequest.
    """
    from core.models import TgUser, Case, ImportRequest
    
    try:
        peer = int(user_tg_id) if user_tg_id.isdigit() else user_tg_id
        messages = await client.get_messages(peer, limit=limit)
        messages = list(reversed(messages))
        
        conversation = []
        for msg in messages:
            if not msg.text and not msg.media:
                continue
            role = _telegram_message_role(msg)
            content = msg.text or "[media attachment]"
            conversation.append({
                'role': role,
                'content': content,
                'timestamp': msg.date.isoformat() if msg.date else datetime.now().isoformat()
            })
        
        def save_import():
            try:
                tg_id = int(user_tg_id)
            except ValueError:
                return 0, "Invalid Telegram ID"
            
            user, _ = TgUser.objects.get_or_create(
                telegram_id=tg_id,
                defaults={'language_code': 'en'}
            )
            # Re-import: replace conversation on existing active case so we don't create duplicates and can fix bad data
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
    try:
        count, error = await fetch_and_save_chat(client, user_tg_id, limit=3000, import_req_id=req_id)
        if error:
            from core.models import ImportRequest
            req = ImportRequest.objects.get(pk=req_id)
            req.status = 'error'
            req.error_msg = error
            req.save()
            raise Exception(error)
        logger.info(f"Imported {count} messages for {user_tg_id}")
    except Exception as e:
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
    if PHONE_2 and len(PHONE_2) > 5:  # must look like a phone (e.g. +44...)
        client2 = TelegramClient(
            str(SESSIONS_DIR / 'userbot2'),
            int(API_ID),
            API_HASH
        )
    
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
            asyncio.create_task(import_queue_loop(client1)),
        ]
        
        logger.info("Userbot running...")
        
        # Run until disconnected
        await client1.run_until_disconnected()
        
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
    
    phone = PHONE if account == 1 else PHONE_2
    session_name = 'userbot' if account == 1 else 'userbot2'
    
    if not phone:
        print(f"Error: TG_PHONE{'_2' if account == 2 else ''} must be configured in .env")
        return
    
    async def auth():
        client = TelegramClient(
            str(SESSIONS_DIR / session_name),
            int(API_ID),
            API_HASH
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
