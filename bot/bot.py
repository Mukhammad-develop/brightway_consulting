#!/usr/bin/env python3
"""
Telegram Bot for Brightway Consulting.

Uses pyTelegramBotAPI (telebot) for handling Telegram bot interactions.
Features:
- Multi-language support (EN, RU, UZ)
- AI-powered responses using GPT-4o-mini
- Voice transcription using Whisper-1
- Document handling and case management
"""

import os
import sys
import logging
import uuid
import threading
import time
from pathlib import Path
from datetime import datetime

# Bootstrap Django
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bwc.settings')

import django
django.setup()

import telebot
from telebot import types
from django.conf import settings

from .messages import t, get_all_languages, LANG_CALLBACKS, get_service_name
from .services import (
    detect_service, ai_detect_service, ask_ai, get_ai_response,
    transcribe_voice, update_user_profile, should_update_profile,
    get_fallback_response, READY_FOR_CONSULTANT_MARKER,
    suggest_document_name, parse_filename_from_response,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / 'bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize bot
BOT_TOKEN = getattr(settings, 'BOT_TOKEN', None) or os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.warning("BOT_TOKEN not configured - bot will not be available")
    bot = None
    
    # Create dummy bot class for decorator compatibility when no token
    class DummyBot:
        def message_handler(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        
        def callback_query_handler(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
    
    bot = DummyBot()
    _BOT_AVAILABLE = False
else:
    bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')
    _BOT_AVAILABLE = True

# Uploads directory
UPLOADS_DIR = PROJECT_ROOT / 'uploads'
UPLOADS_DIR.mkdir(exist_ok=True)

# Conversation state management (in-memory cache)
_conversation_state = {}  # {user_tg_id: {'service': str, 'step': int, 'last_activity': datetime}}


# ============== Helper Functions ==============

def get_or_create_user(tg_user: types.User):
    """Get or create TgUser from Telegram user object."""
    from core.models import TgUser
    
    try:
        user, created = TgUser.objects.get_or_create(
            telegram_id=tg_user.id,
            defaults={
                'username': tg_user.username,
                'first_name': tg_user.first_name,
                'last_name': tg_user.last_name,
                'language_code': (tg_user.language_code or 'en')[:2],
                'is_bot': tg_user.is_bot,
            }
        )
        
        if not created:
            # Update user info
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            if tg_user.language_code:
                # Only update if user hasn't set preference
                if user.language_code not in ['en', 'ru', 'uz']:
                    user.language_code = tg_user.language_code[:2]
            user.save(update_fields=['username', 'first_name', 'last_name', 'language_code'])
        
        return user
    except Exception as e:
        logger.error(f"Error creating/updating user: {e}")
        return None


def get_or_open_case(user, service='general'):
    """Get active case or create new one."""
    from core.models import Case
    
    # Try to get existing active case for this service
    case = Case.objects.filter(
        user=user,
        service=service,
        status='active'
    ).first()
    
    if not case:
        # Try any active case
        case = Case.objects.filter(user=user, status='active').first()
    
    if not case:
        # Create new case
        case = Case.objects.create(
            user=user,
            service=service,
            status='active',
            payment_status='pending'
        )
        logger.info(f"Created new case #{case.pk} for user {user.telegram_id}")
    
    return case


def get_user_language(user):
    """Get user's preferred language."""
    if user and user.language_code:
        lang = user.language_code[:2].lower()
        if lang in ['en', 'ru', 'uz']:
            return lang
    return 'en'


def create_language_keyboard():
    """Create inline keyboard for language selection."""
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    
    for lang in get_all_languages():
        keyboard.add(types.InlineKeyboardButton(
            f"{lang['flag']} {lang['name']}",
            callback_data=f"lang_{lang['code']}"
        ))
    
    return keyboard


def create_service_keyboard(lang='en'):
    """Create inline keyboard for service selection."""
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    services = [
        ('student', '🎓'),
        ('paye', '💰'),
        ('self', '📊'),
        ('company', '🏢'),
    ]
    
    for service, emoji in services:
        name = get_service_name(service, lang)
        keyboard.add(types.InlineKeyboardButton(
            f"{emoji} {name}",
            callback_data=f"service_{service}"
        ))
    
    return keyboard


def get_conversation_state(user_tg_id: int) -> dict:
    """Get conversation state for a user."""
    state = _conversation_state.get(user_tg_id, {})
    # Clean up old states (older than 1 hour)
    if state.get('last_activity'):
        if (datetime.now() - state['last_activity']).seconds > 3600:
            _conversation_state.pop(user_tg_id, None)
            return {}
    return state


def update_conversation_state(user_tg_id: int, service: str = None, step: int = None):
    """Update conversation state for a user."""
    if user_tg_id not in _conversation_state:
        _conversation_state[user_tg_id] = {}
    
    _conversation_state[user_tg_id]['last_activity'] = datetime.now()
    if service is not None:
        _conversation_state[user_tg_id]['service'] = service
    if step is not None:
        _conversation_state[user_tg_id]['step'] = step


def _typing_loop(chat_id, stop_event, interval=4):
    """Run typing action every interval seconds until stop_event is set."""
    while not stop_event.wait(interval):
        try:
            bot.send_chat_action(chat_id, 'typing')
        except Exception:
            break


def try_assign_case_to_consultant(case, user):
    """
    Assign case to a consultant when AI has finished collecting information.
    Sets case.assigned_to and ensures AdminAssignment exists for the user.
    """
    from django.db.models import Count
    from core.models import AdminUser, AdminAssignment
    consultant = (
        AdminUser.objects.filter(role='consultant', is_active=True)
        .annotate(assigned_count=Count('assigned_cases'))
        .order_by('assigned_count')
        .first()
    )
    if not consultant:
        consultant = AdminUser.objects.filter(is_active=True).order_by('role').first()
    if consultant:
        case.assigned_to = consultant
        case.save(update_fields=['assigned_to'])
        AdminAssignment.objects.get_or_create(admin=consultant, user=user)
        logger.info(f"Case #{case.pk} assigned to consultant {consultant.username}")


def process_ai_response(user, case, text: str, lang: str, send_reply: bool = True):
    """
    Process user message and get AI response with error handling.
    When send_reply=False, only stores the user message (and optionally opening) — no AI call, no return value sent.
    When AI is disabled for the case, only stores the user message and returns None (no reply sent).
    When AI signals [READY_FOR_CONSULTANT], assigns case to a consultant and turns AI off for this case.
    Returns (response_str, filename_label or None). If AI suggested FILENAME: label, filename_label is set.
    """
    # Add user message to conversation
    case.add_message('user', text)

    # If AI is turned off for this case, do not call AI; no reply sent
    if not getattr(case, 'ai_enabled', True):
        return (None, None)

    if not send_reply:
        return (None, None)

    # Get AI response
    conversation = case.get_conversation()
    ai_response = ask_ai(conversation, case.service, lang)

    if ai_response:
        # Strip consultant-assignment marker
        to_store = ai_response.replace(READY_FOR_CONSULTANT_MARKER, '').strip()
        # Parse and strip FILENAME: line so assistant can suggest file names
        to_store, filename_label = parse_filename_from_response(to_store)
        to_store = to_store.strip()
        to_send = to_store
        case.add_message('assistant', to_send)

        if READY_FOR_CONSULTANT_MARKER in ai_response:
            try:
                try_assign_case_to_consultant(case, user)
            except Exception as e:
                logger.error(f"Failed to assign case to consultant: {e}")
            # Auto-disable AI for this case until it is closed
            case.ai_enabled = False
            case.save(update_fields=['ai_enabled'])

        # Check if we should update user profile
        message_count = len(conversation)
        if should_update_profile(message_count):
            try:
                update_user_profile(user.pk, force=False)
            except Exception as e:
                logger.error(f"Background profile update error: {e}")
        
        return (to_send, filename_label)
    else:
        return (get_fallback_response(lang), None)


# ============== Command Handlers ==============

@bot.message_handler(commands=['start'])
def handle_start(message):
    """Handle /start command."""
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred. Please try again.")
            return
        
        lang = get_user_language(user)
        
        # Reset conversation state
        _conversation_state.pop(message.from_user.id, None)
        
        # Send welcome message with language selection
        welcome_text = t(lang, 'welcome')
        keyboard = create_language_keyboard()
        
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=keyboard
        )
        
        logger.info(f"/start from user {user.telegram_id}")
        
    except Exception as e:
        logger.error(f"Error in /start handler: {e}")
        bot.reply_to(message, "Sorry, an error occurred. Please try again.")


@bot.message_handler(commands=['help'])
def handle_help(message):
    """Handle /help command."""
    try:
        user = get_or_create_user(message.from_user)
        lang = get_user_language(user) if user else 'en'
        
        help_text = t(lang, 'help')
        bot.send_message(message.chat.id, help_text)
        
    except Exception as e:
        logger.error(f"Error in /help handler: {e}")


@bot.message_handler(commands=['language'])
def handle_language(message):
    """Handle /language command."""
    try:
        user = get_or_create_user(message.from_user)
        lang = get_user_language(user) if user else 'en'
        
        keyboard = create_language_keyboard()
        bot.send_message(
            message.chat.id,
            t(lang, 'select_language'),
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in /language handler: {e}")


@bot.message_handler(commands=['mycase', 'case'])
def handle_mycase(message):
    """Handle /mycase or /case command."""
    from core.models import Case, Document
    
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred.")
            return
        
        lang = get_user_language(user)
        
        # Get active case
        case = Case.objects.filter(user=user, status='active').first()
        
        if not case:
            bot.send_message(message.chat.id, t(lang, 'case_none'))
            return
        
        # Count documents
        doc_count = Document.objects.filter(case=case).count()
        
        # Format case info
        case_info = t(lang, 'case_info',
            service=get_service_name(case.service, lang),
            status=case.status.title(),
            payment=case.payment_status.title(),
            doc_count=doc_count,
            created=case.created_at.strftime('%Y-%m-%d')
        )
        
        bot.send_message(message.chat.id, case_info)
        
    except Exception as e:
        logger.error(f"Error in /mycase handler: {e}")


@bot.message_handler(commands=['newcase'])
def handle_newcase(message):
    """Handle /newcase command - start a new consultation."""
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred.")
            return
        
        lang = get_user_language(user)
        
        # Reset conversation state
        _conversation_state.pop(message.from_user.id, None)
        
        # Show service selection
        keyboard = create_service_keyboard(lang)
        bot.send_message(
            message.chat.id,
            t(lang, 'select_service'),
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in /newcase handler: {e}")


# ============== Callback Query Handlers ==============

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def handle_language_callback(call):
    """Handle language selection callback."""
    from core.models import TgUser
    
    try:
        lang_code = LANG_CALLBACKS.get(call.data, 'en')
        
        # Update user language
        user = get_or_create_user(call.from_user)
        if user:
            user.language_code = lang_code
            user.save(update_fields=['language_code'])
        
        # Acknowledge and update message
        bot.answer_callback_query(call.id)
        
        # Send intro message in new language
        intro_text = t(lang_code, 'intro')
        bot.edit_message_text(
            f"{t(lang_code, 'language_changed')}\n\n{intro_text}",
            call.message.chat.id,
            call.message.message_id
        )
        
        logger.info(f"User {call.from_user.id} changed language to {lang_code}")
        
    except Exception as e:
        logger.error(f"Error in language callback: {e}")
        bot.answer_callback_query(call.id, "Error occurred")


@bot.callback_query_handler(func=lambda call: call.data.startswith('service_'))
def handle_service_callback(call):
    """Handle service selection callback."""
    from core.models import Case
    
    try:
        service = call.data.replace('service_', '')
        
        user = get_or_create_user(call.from_user)
        if not user:
            bot.answer_callback_query(call.id, "Error occurred")
            return
        
        lang = get_user_language(user)
        
        # Create new case for this service
        case = Case.objects.create(
            user=user,
            service=service,
            status='active',
            payment_status='pending'
        )
        
        # Update conversation state
        update_conversation_state(call.from_user.id, service=service, step=0)
        
        bot.answer_callback_query(call.id)
        
        # Update message and prompt user
        service_name = get_service_name(service, lang)
        bot.edit_message_text(
            f"✅ {service_name}\n\n{t(lang, 'new_case_started')}",
            call.message.chat.id,
            call.message.message_id
        )
        
        logger.info(f"User {user.telegram_id} started new {service} case")
        
    except Exception as e:
        logger.error(f"Error in service callback: {e}")
        bot.answer_callback_query(call.id, "Error occurred")


# ============== Message Handlers ==============

@bot.message_handler(content_types=['text'])
def handle_text_message(message):
    """Handle regular text messages."""
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred.")
            return
        
        lang = get_user_language(user)
        text = message.text.strip()
        
        # Get conversation state
        state = get_conversation_state(message.from_user.id)
        current_service = state.get('service')
        
        # Detect service from message if not already in a service flow
        if not current_service:
            # Try keyword detection first (fast)
            detected_service = detect_service(text)
            
            # If no keyword match and message is substantial, try AI detection
            if not detected_service and len(text) > 20:
                detected_service = ai_detect_service(text)
            
            current_service = detected_service or 'general'
        
        # Update conversation state
        update_conversation_state(message.from_user.id, service=current_service)
        
        # Get or create case
        case = get_or_open_case(user, current_service)
        
        # Update case service if it changed
        if case.service == 'general' and current_service != 'general':
            case.service = current_service
            case.save(update_fields=['service'])
        
        # New user (no prior messages): send only the opening message; AI replies when they answer that
        from bot.messages import OPENING_MESSAGE
        conv = case.get_conversation()
        if len(conv) == 0:
            case.add_message('assistant', OPENING_MESSAGE)
            bot.send_message(message.chat.id, OPENING_MESSAGE)
            # Store user's first message; no AI reply yet — they get AI after replying to the opening
            process_ai_response(user, case, text, lang, send_reply=False)
            logger.info(f"First message from {user.telegram_id}: sent opening only")
            return
        
        # Show typing while AI is generating (typing action lasts ~5s, so repeat every 4s)
        stop_typing = threading.Event()
        typing_thread = threading.Thread(
            target=_typing_loop,
            args=(message.chat.id, stop_typing),
            daemon=True
        )
        typing_thread.start()
        try:
            response, _ = process_ai_response(user, case, text, lang)
        finally:
            stop_typing.set()
        
        # Send response only if AI replied
        if response:
            bot.send_message(message.chat.id, response)
        
        logger.info(f"Message from {user.telegram_id}: {text[:50]}...")
        
    except Exception as e:
        logger.error(f"Error handling text message: {e}")
        bot.reply_to(message, "Sorry, an error occurred. Please try again.")


@bot.message_handler(content_types=['sticker'])
def handle_sticker(message):
    """Handle stickers: first message gets opening only; later messages get AI reply."""
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred.")
            return
        lang = get_user_language(user)
        case = get_or_open_case(user, 'general')
        conv = case.get_conversation()
        if len(conv) == 0:
            from bot.messages import OPENING_MESSAGE
            case.add_message('assistant', OPENING_MESSAGE)
            bot.send_message(message.chat.id, OPENING_MESSAGE)
            case.add_message('user', '[Sticker]')
            logger.info(f"First message from {user.telegram_id} was sticker: sent opening only")
            return
        # Not first message: add sticker to conversation and get AI response
        stop_typing = threading.Event()
        typing_thread = threading.Thread(target=_typing_loop, args=(message.chat.id, stop_typing), daemon=True)
        typing_thread.start()
        try:
            response, _ = process_ai_response(user, case, '[Sticker]', lang)
        finally:
            stop_typing.set()
        if response:
            bot.send_message(message.chat.id, response)
    except Exception as e:
        logger.error(f"Error handling sticker: {e}")


@bot.message_handler(content_types=['voice', 'audio'])
def handle_voice_message(message):
    """Handle voice/audio messages with transcription."""
    from core.models import Document
    
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred.")
            return
        
        lang = get_user_language(user)
        case = get_or_open_case(user, 'general')
        conv = case.get_conversation()
        if len(conv) == 0:
            from bot.messages import OPENING_MESSAGE
            case.add_message('assistant', OPENING_MESSAGE)
            bot.send_message(message.chat.id, OPENING_MESSAGE)
            case.add_message('user', '[Voice]')
            logger.info(f"First message from {user.telegram_id} was voice: sent opening only")
            return
        
        # Get file info
        if message.voice:
            file_info = bot.get_file(message.voice.file_id)
            file_id = message.voice.file_id
            file_unique_id = message.voice.file_unique_id
            ext = '.ogg'
        else:
            file_info = bot.get_file(message.audio.file_id)
            file_id = message.audio.file_id
            file_unique_id = message.audio.file_unique_id
            ext = os.path.splitext(message.audio.file_name or '.mp3')[1] or '.mp3'
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{unique_id}{ext}"
        filepath = UPLOADS_DIR / filename
        
        # Download and save file
        downloaded = bot.download_file(file_info.file_path)
        with open(filepath, 'wb') as f:
            f.write(downloaded)
        
        # Create document record
        doc = Document.objects.create(
            case=case,
            file_path=filename,
            file_type='voice',
            telegram_file_id=f"local:{filename}",
            file_unique_id=file_unique_id,
            media_type='voice'
        )
        # Suggest display name from conversation
        case.add_message('user', f"[FILE:{unique_id}:{filename}:voice]")
        conv = case.get_conversation()
        suggested = suggest_document_name(conv, 'voice', user.telegram_id, ext)
        doc.display_name = f"{suggested}_{user.telegram_id}{ext}" if suggested else f"voice_{user.telegram_id}{ext}"
        doc.save(update_fields=['display_name'])
        
        # Send processing indicator
        bot.send_chat_action(message.chat.id, 'typing')
        processing_msg = bot.send_message(message.chat.id, t(lang, 'processing'))
        
        # Transcribe the voice message
        transcription = transcribe_voice(str(filepath), lang)
        
        if transcription:
            # Save transcription to document
            doc.transcription = transcription
            doc.save(update_fields=['transcription'])
            
            # Add transcription as user message
            case.add_message('user', f"[Voice message]: {transcription}")
            
            # Delete processing message
            try:
                bot.delete_message(message.chat.id, processing_msg.message_id)
            except:
                pass
            
            # Send transcription confirmation
            bot.send_message(
                message.chat.id,
                f"🎤 _{transcription}_\n\n" + t(lang, 'voice_received'),
                parse_mode='Markdown'
            )
            
            # Process transcription as regular message and get AI response (typing while AI runs)
            stop_typing = threading.Event()
            typing_thread = threading.Thread(target=_typing_loop, args=(message.chat.id, stop_typing), daemon=True)
            typing_thread.start()
            try:
                response, filename_label = process_ai_response(user, case, transcription, lang)
            finally:
                stop_typing.set()
            if filename_label:
                doc.display_name = f"{filename_label}_{user.telegram_id}{ext}"
                doc.save(update_fields=['display_name'])
            if response:
                bot.send_message(message.chat.id, response)
            
        else:
            # Transcription failed
            try:
                bot.delete_message(message.chat.id, processing_msg.message_id)
            except:
                pass
            
            bot.send_message(message.chat.id, t(lang, 'voice_received'))
        
        logger.info(f"Voice message from {user.telegram_id}: {filename}")
        
    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        bot.reply_to(message, "Sorry, an error occurred processing your voice message.")


@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handle document uploads."""
    from core.models import Document
    
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred.")
            return
        
        lang = get_user_language(user)
        state = get_conversation_state(message.from_user.id)
        current_service = state.get('service', 'general')
        case = get_or_open_case(user, current_service)
        conv = case.get_conversation()
        if len(conv) == 0:
            from bot.messages import OPENING_MESSAGE
            case.add_message('assistant', OPENING_MESSAGE)
            bot.send_message(message.chat.id, OPENING_MESSAGE)
            case.add_message('user', '[Media]')
            logger.info(f"First message from {user.telegram_id} was document: sent opening only")
            return
        
        # Get file info
        doc = message.document
        file_info = bot.get_file(doc.file_id)
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        original_name = doc.file_name or 'document'
        ext = os.path.splitext(original_name)[1] or ''
        filename = f"{unique_id}{ext}"
        filepath = UPLOADS_DIR / filename
        
        # Download and save file
        downloaded = bot.download_file(file_info.file_path)
        with open(filepath, 'wb') as f:
            f.write(downloaded)
        
        # Determine file type
        file_type = ext.lstrip('.').lower() or 'unknown'
        
        # Check if it's audio or video
        audio_extensions = {'.ogg', '.oga', '.mp3', '.m4a', '.wav', '.opus', '.webm'}
        video_extensions = {'.mp4', '.mov', '.avi', '.webm', '.mkv', '.m4v'}
        mime = getattr(doc, 'mime_type', None) or ''
        if ext.lower() in audio_extensions or mime.startswith('audio/'):
            media_type = 'voice'
        elif ext.lower() in video_extensions or mime.startswith('video/'):
            media_type = 'video'
        else:
            media_type = 'document'
        
        # Create document record
        doc_record = Document.objects.create(
            case=case,
            file_path=filename,
            file_type=file_type,
            telegram_file_id=f"local:{filename}",
            file_unique_id=doc.file_unique_id,
            media_type=media_type,
            description=original_name
        )
        # Suggest display name from conversation
        case.add_message('user', f"[FILE:{unique_id}:{original_name}:{media_type}]")
        conv = case.get_conversation()
        suggested = suggest_document_name(conv, media_type, user.telegram_id, ext)
        doc_record.display_name = f"{suggested}_{user.telegram_id}{ext}" if suggested else f"{media_type}_{user.telegram_id}{ext}"
        doc_record.save(update_fields=['display_name'])
        
        # Acknowledge receipt
        bot.send_message(message.chat.id, t(lang, 'doc_received'))
        
        # If it's an audio file, offer to transcribe
        if media_type == 'voice':
            bot.send_chat_action(message.chat.id, 'typing')
            transcription = transcribe_voice(str(filepath), lang)
            if transcription:
                doc_record.transcription = transcription
                doc_record.save(update_fields=['transcription'])
                case.add_message('user', f"[Audio file transcription]: {transcription}")
                bot.send_message(message.chat.id, f"🎤 Transcription:\n_{transcription}_", parse_mode='Markdown')
        
        # Get AI response about the document (typing while AI runs)
        stop_typing = threading.Event()
        typing_thread = threading.Thread(target=_typing_loop, args=(message.chat.id, stop_typing), daemon=True)
        typing_thread.start()
        try:
            response, filename_label = process_ai_response(user, case, f"[Uploaded document: {original_name}]", lang)
        finally:
            stop_typing.set()
        if response:
            bot.send_message(message.chat.id, response)
        if filename_label:
            doc_record.display_name = f"{filename_label}_{user.telegram_id}{ext}"
            doc_record.save(update_fields=['display_name'])
        
        logger.info(f"Document from {user.telegram_id}: {original_name}")
        
    except Exception as e:
        logger.error(f"Error handling document: {e}")
        bot.reply_to(message, "Sorry, an error occurred processing your document.")


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """Handle photo uploads."""
    from core.models import Document
    
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred.")
            return
        
        lang = get_user_language(user)
        state = get_conversation_state(message.from_user.id)
        current_service = state.get('service', 'general')
        case = get_or_open_case(user, current_service)
        conv = case.get_conversation()
        if len(conv) == 0:
            from bot.messages import OPENING_MESSAGE
            case.add_message('assistant', OPENING_MESSAGE)
            bot.send_message(message.chat.id, OPENING_MESSAGE)
            case.add_message('user', '[Photo]')
            logger.info(f"First message from {user.telegram_id} was photo: sent opening only")
            return
        
        # Get largest photo
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{unique_id}.jpg"
        filepath = UPLOADS_DIR / filename
        
        # Download and save file
        downloaded = bot.download_file(file_info.file_path)
        with open(filepath, 'wb') as f:
            f.write(downloaded)
        
        # Create document record
        doc = Document.objects.create(
            case=case,
            file_path=filename,
            file_type='jpg',
            telegram_file_id=f"local:{filename}",
            file_unique_id=photo.file_unique_id,
            media_type='photo'
        )
        # Add to conversation and suggest display name
        case.add_message('user', f"[FILE:{unique_id}:{filename}:photo]")
        conv = case.get_conversation()
        suggested = suggest_document_name(conv, 'photo', user.telegram_id, '.jpg')
        doc.display_name = f"{suggested}_{user.telegram_id}.jpg" if suggested else f"photo_{user.telegram_id}.jpg"
        doc.save(update_fields=['display_name'])
        
        # Acknowledge receipt
        bot.send_message(message.chat.id, t(lang, 'photo_received'))
        
        # Get AI response (typing while AI runs)
        stop_typing = threading.Event()
        typing_thread = threading.Thread(target=_typing_loop, args=(message.chat.id, stop_typing), daemon=True)
        typing_thread.start()
        try:
            response, filename_label = process_ai_response(user, case, "[User uploaded a photo]", lang)
        finally:
            stop_typing.set()
        if filename_label:
            doc.display_name = f"{filename_label}_{user.telegram_id}.jpg"
            doc.save(update_fields=['display_name'])
        if response:
            bot.send_message(message.chat.id, response)
        
        logger.info(f"Photo from {user.telegram_id}")
        
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        bot.reply_to(message, "Sorry, an error occurred processing your photo.")


@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    """Handle shared contact."""
    from core.models import TgUser
    
    try:
        user = get_or_create_user(message.from_user)
        if not user:
            bot.reply_to(message, "Sorry, an error occurred.")
            return
        
        lang = get_user_language(user)
        
        # Update user phone if contact is their own
        if message.contact.user_id == message.from_user.id:
            user.phone = message.contact.phone_number
            user.save(update_fields=['phone'])
            
            # Also add to current case conversation
            case = get_or_open_case(user, 'general')
            case.add_message('user', f"[Shared phone number: {message.contact.phone_number}]")
        
        bot.send_message(message.chat.id, t(lang, 'contact_received'))
        
        logger.info(f"Contact shared by {user.telegram_id}")
        
    except Exception as e:
        logger.error(f"Error handling contact: {e}")


# ============== Bot Functions for Admin Panel ==============

def send_message_to_user(tg_id: int, text: str, sender_name: str = 'Admin') -> bool:
    """
    Send a message to a user via the bot.
    Used by admin panel for replying to users.
    
    Args:
        tg_id: Telegram user ID
        text: Message text
        sender_name: Name of the admin sending the message
        
    Returns:
        True if successful, False otherwise
    """
    if not _BOT_AVAILABLE:
        logger.error("Bot not initialized")
        return False
    
    try:
        bot.send_message(tg_id, text)
        logger.info(f"Admin message sent to {tg_id} by {sender_name}")
        return True
    except Exception as e:
        logger.error(f"Error sending admin message to {tg_id}: {e}")
        return False


def get_bot_info() -> dict:
    """Get bot information."""
    if not _BOT_AVAILABLE:
        return {'ok': False, 'error': 'Bot not initialized'}
    
    try:
        me = bot.get_me()
        return {
            'ok': True,
            'id': me.id,
            'username': me.username,
            'first_name': me.first_name
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ============== Main Entry Point ==============

def run_bot():
    """Start the bot in polling mode."""
    if not _BOT_AVAILABLE:
        logger.error("Cannot start bot: BOT_TOKEN not configured")
        print("ERROR: BOT_TOKEN not configured in .env file")
        return
    
    logger.info("Starting Brightway Consulting Telegram Bot...")
    
    try:
        # Get bot info
        me = bot.get_me()
        logger.info(f"Bot started: @{me.username}")
        print(f"Bot started: @{me.username}")
        
        # Start polling
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise


if __name__ == '__main__':
    run_bot()
