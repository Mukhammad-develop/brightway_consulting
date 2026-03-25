"""
AI Services for Brightway Consulting Telegram bot.

Handles service detection, system prompts, AI interactions, voice transcription,
and profile extraction using OpenAI APIs (GPT-4o-mini and Whisper-1) and
Muxlisa AI STT for Uzbek voice messages.
"""

import os
import re
import sys
import time
import json
import logging
import subprocess
import tempfile
import requests as _requests
from pathlib import Path
from functools import wraps

# Bootstrap Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bwc.settings')

import django
django.setup()

from django.conf import settings
from .messages import t, get_service_name

logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = PROJECT_ROOT / 'uploads'

# OpenAI client (lazy initialized)
_openai_client = None

# AI Usage tracking
_ai_usage = {
    'api_calls_today': 0,
    'total_tokens_today': 0,
    'errors_today': 0,
    'last_reset': None,
    'response_times': [],
}

# Rate limiting
_rate_limit = {
    'calls_per_minute': 60,
    'last_calls': [],  # timestamps of recent calls
}

# Marker in AI response when info collection is complete and user should be assigned to a consultant
READY_FOR_CONSULTANT_MARKER = '[READY_FOR_CONSULTANT]'


# ============== OpenAI Client Management ==============

def get_openai_client():
    """Get or create OpenAI client with lazy initialization."""
    global _openai_client
    
    if _openai_client is None:
        import openai
        api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("OpenAI API key not configured")
            return None
        _openai_client = openai.OpenAI(api_key=api_key)
    
    return _openai_client


def _check_rate_limit():
    """Check if we're within rate limits. Returns True if OK to proceed."""
    now = time.time()
    # Remove calls older than 60 seconds
    _rate_limit['last_calls'] = [t for t in _rate_limit['last_calls'] if now - t < 60]
    
    if len(_rate_limit['last_calls']) >= _rate_limit['calls_per_minute']:
        return False
    
    _rate_limit['last_calls'].append(now)
    return True


def _track_usage(tokens=0, error=False, response_time=0):
    """Track AI API usage for statistics."""
    from datetime import datetime, date
    
    today = date.today()
    if _ai_usage['last_reset'] != today:
        _ai_usage['api_calls_today'] = 0
        _ai_usage['total_tokens_today'] = 0
        _ai_usage['errors_today'] = 0
        _ai_usage['response_times'] = []
        _ai_usage['last_reset'] = today
    
    _ai_usage['api_calls_today'] += 1
    _ai_usage['total_tokens_today'] += tokens
    if error:
        _ai_usage['errors_today'] += 1
    if response_time:
        _ai_usage['response_times'].append(response_time)
        # Keep only last 100 response times
        if len(_ai_usage['response_times']) > 100:
            _ai_usage['response_times'] = _ai_usage['response_times'][-100:]


def get_ai_usage_stats():
    """Get AI usage statistics for the admin panel."""
    response_times = _ai_usage['response_times']
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    return {
        'api_calls_today': _ai_usage['api_calls_today'],
        'total_tokens_today': _ai_usage['total_tokens_today'],
        'errors_today': _ai_usage['errors_today'],
        'avg_response_time': round(avg_response_time, 2),
        'error_rate': round(_ai_usage['errors_today'] / max(_ai_usage['api_calls_today'], 1) * 100, 1),
    }


# ============== Service Detection (AI only) ==============

def ai_detect_service(text: str, conversation_history: list = None) -> str:
    """
    Use AI to detect which service the user needs from their message.
    
    Args:
        text: User message text
        conversation_history: Optional conversation context
        
    Returns:
        Service slug or None (general)
    """
    if not (text and text.strip()):
        return None
    
    client = get_openai_client()
    if not client:
        return None
    
    # Prefer dynamic classifier built from DB services (so admin changes take effect)
    system_prompt = None
    try:
        from core.models import ServiceDefinition, AiSettings
        services = list(ServiceDefinition.objects.filter(is_active=True).order_by('display_order', 'name'))

        # Optional override prompt from DB (highest priority)
        s = AiSettings.objects.order_by('-updated_at').first()
        override = (getattr(s, 'service_classifier_prompt', '') or '').strip() if s else ''
        if override:
            system_prompt = override
        elif services:
            lines = []
            lines.append("You are a service classifier for Brightway Consulting.")
            lines.append("Based on the user's message, choose exactly ONE service slug from the list below.")
            lines.append("Respond with ONLY the slug (one word). No extra text.")
            lines.append("")
            lines.append("SERVICES:")
            for svc in services:
                kw = (svc.get_keywords_list() or [])
                kw_preview = ", ".join(kw[:20])
                label = (svc.name or svc.slug)
                if kw_preview:
                    lines.append(f'- "{svc.slug}" — {label}. Keywords: {kw_preview}')
                else:
                    lines.append(f'- "{svc.slug}" — {label}.')
            lines.append('- "general" — general inquiry / unclear / not matching any service above.')
            lines.append("")
            lines.append("Rules:")
            lines.append("- The user may write in English, Russian, or Uzbek.")
            lines.append("- If unsure, respond with general.")
            system_prompt = "\n".join(lines)
    except Exception:
        system_prompt = None

    if not system_prompt:
        # Fallback hardcoded classifier (safe default)
        system_prompt = """You are a service classifier for a UK consulting firm.
Based on the user message, determine which service they need:
- "student" - Student visa, university applications, educational guidance
- "paye" - PAYE tax refund, employed tax returns, P45/P60
- "schengen" - Schengen visa, Evisa, Sharecode, European/Schengen travel
- "self" - Self-employment tax, UTR number, freelancer tax
- "company" - Company accounting, VAT, payroll, limited company services
- "general" - General inquiry or unclear

The user may write in English, Russian, or Uzbek. Examples: "мне нужна помощь по визе", "помощ по визе", "виза" -> student or schengen (visa). "налог", "возврат налога", "tax refund" -> paye. "бухгалтерия", "accounting" -> company. When in doubt between student and schengen for "visa", prefer "schengen" unless they mention university/student.

Respond with ONLY the service slug (student, paye, schengen, self, company, or general).
"""
    
    messages = [{'role': 'system', 'content': system_prompt}]
    
    # Add conversation context if available
    if conversation_history:
        for msg in conversation_history[-5:]:  # Last 5 messages for context
            content = msg.get('content', '')
            if content and not content.startswith('[FILE:'):
                messages.append({
                    'role': msg.get('role', 'user'),
                    'content': content[:200]  # Truncate long messages
                })
    
    messages.append({'role': 'user', 'content': f"Classify this message: {text}"})
    
    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=messages,
            max_tokens=20,
            temperature=0.1
        )
        response_time = time.time() - start_time
        _track_usage(response.usage.total_tokens if response.usage else 0, response_time=response_time)
        
        result = response.choices[0].message.content.strip().lower()
        # Normalize: take first word in case model added extra text
        result = (result.split()[0] if result else '').rstrip('.,;:')

        # Validate response
        valid_services = ['student', 'paye', 'schengen', 'self', 'company', 'general']
        out = result if result in valid_services and result != 'general' else None
        print(f"[SVC] ai_detect_service: text={text[:60]!r} -> raw={result!r} -> return={out!r}")
        logger.info(f"AI detected service: {result} for text: {text[:50]}... -> return {out}")
        if result in valid_services:
            return out
        return None

    except Exception as e:
        print(f"[SVC] ai_detect_service: FAILED text={text[:60]!r} error={e}")
        logger.error(f"AI service detection error: {e}")
        _track_usage(error=True)
        return None


def detect_reply_lang(text: str):
    """
    Detect reply language from user message using AI so we can force the same language in the reply.
    Returns 'ru', 'uz', 'en', or None (use profile language) on empty input or API failure.
    """
    snippet = (text or '')[:80].replace('\n', ' ')
    if not text or not isinstance(text, str):
        print(f"[LANG] detect_reply_lang: no text")
        logger.info("[LANG] detect_reply_lang: no text")
        return None
    t = text.strip()
    if not t or t == '[Sticker]' or t.startswith('[FILE:'):
        print(f"[LANG] detect_reply_lang: skip (sticker/file/empty)")
        logger.info("[LANG] detect_reply_lang: skip (sticker/file/empty)")
        return None

    client = get_openai_client()
    if not client:
        print(f"[LANG] detect_reply_lang: no OpenAI client")
        logger.info("[LANG] detect_reply_lang: no OpenAI client")
        return None
    if not _check_rate_limit():
        print(f"[LANG] detect_reply_lang: rate limit")
        logger.info("[LANG] detect_reply_lang: rate limit")
        return None

    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': 'You detect the language of the user message. Reply with exactly one word: ru (Russian), uz (Uzbek), or en (English). Uzbek can be written in Latin or Cyrillic script; do not assume Cyrillic is always Russian. No other text.'},
                {'role': 'user', 'content': t[:1000]}
            ],
            max_tokens=5,
            temperature=0,
            timeout=10
        )
        raw = (response.choices[0].message.content or '').strip().lower()
        if response.usage:
            _track_usage(response.usage.total_tokens)
        code = (raw.split()[0] if raw else '').rstrip('.,;:')
        result = code if code in ('ru', 'uz', 'en') else None
        print(f"[LANG] detect_reply_lang: input={snippet!r} -> raw={raw!r} code={code!r} -> result={result}")
        logger.info(f"[LANG] detect_reply_lang: input={snippet!r} -> raw={raw!r} code={code!r} -> result={result}")
        return result
    except Exception as e:
        print(f"[LANG] detect_reply_lang: FAILED input={snippet!r} error={e}")
        logger.warning(f"Language detection failed: {e}")
        _track_usage(error=True)
        return None


# ============== System Prompts ==============

def build_system_prompt(service: str, lang: str = 'en') -> str:
    """
    Build the system prompt for AI based on service and language.
    
    Args:
        service: Service slug
        lang: Language code
        
    Returns:
        Complete system prompt string
    """
    from core.models import ServiceDefinition, AiSettings
    
    lang_map = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}
    target_lang = lang_map.get(lang, 'English')
    
    # Try to get service definition from database
    svc_def = None
    try:
        svc_def = ServiceDefinition.objects.filter(slug=service, is_active=True).first()
    except Exception as e:
        logger.error(f"Error loading service definition: {e}")
    
    ai_settings = None
    try:
        ai_settings = AiSettings.objects.order_by('-updated_at').first() or AiSettings.objects.get(pk=1)
    except Exception:
        ai_settings = None

    if svc_def and (svc_def.ai_system_prompt or '').strip():
        base_prompt = (svc_def.ai_system_prompt or '').strip()
        if not svc_def.ai_strict_flow:
            collect_items = svc_def.get_collect_items()
            if collect_items:
                base_prompt += "\n\nInformation to collect:\n" + "\n".join(f"- {item}" for item in collect_items)

            documents = svc_def.get_documents_list()
            if documents:
                base_prompt += "\n\nDocuments to request:\n" + "\n".join(f"- {doc}" for doc in documents)
    else:
        # No per-service prompt configured: use global general prompt from DB
        base_prompt = ((getattr(ai_settings, 'general_system_prompt', '') or '').strip() if ai_settings else '').strip()
    
    if service and service != 'general':
        behavior = ((getattr(ai_settings, 'collect_and_assign_behavior', '') or '').strip() if ai_settings else '').strip()
        if behavior:
            base_prompt = base_prompt.rstrip() + "\n\n" + behavior

    tone = ((getattr(ai_settings, 'tone_rules', '') or '').strip() if ai_settings else '').strip()
    anti = ((getattr(ai_settings, 'anti_bot_patterns', '') or '').strip() if ai_settings else '').strip()
    examples = ((getattr(ai_settings, 'style_examples', '') or '').strip() if ai_settings else '').strip()
    natural = ((getattr(ai_settings, 'natural_language_rules', '') or '').strip() if ai_settings else '').strip()
    common = ((getattr(ai_settings, 'common_rules', '') or '').strip() if ai_settings else '').strip()

    parts = [base_prompt]
    for block in (tone, anti, examples, natural, common):
        if block:
            parts.append(block)
    parts.append(f"This turn, you MUST reply ONLY in {target_lang}.")
    full_prompt = "\n\n".join([p for p in parts if (p or '').strip()])
    
    return full_prompt


def _build_hardcoded_prompt(service: str) -> str:
    """
    Deprecated: kept only for backward compatibility in older imports.
    Prompts must come from DB (ServiceDefinition + AiSettings).
    """
    return ""


# ============== AI Chat Functions ==============

def get_ai_response(message: str, conversation_history: list = None, service: str = None, lang: str = 'en', max_tokens: int = 800) -> str:
    """
    Get AI response for a user message.
    
    Args:
        message: User's message text
        conversation_history: List of previous messages
        service: Service slug for context
        lang: Language code
        max_tokens: Maximum response tokens
        
    Returns:
        AI response text or None on error
    """
    if not _check_rate_limit():
        logger.warning("Rate limit exceeded for AI calls")
        return None
    
    client = get_openai_client()
    if not client:
        return None

    msg_snippet = (message or '')[:80].replace('\n', ' ')
    print(f"[AI] get_ai_response: message={msg_snippet!r} service={service!r} profile_lang={lang!r}")
    logger.info(f"[AI] get_ai_response: message={msg_snippet!r} service={service!r} profile_lang={lang!r}")

    # Reply in the same language as the user's message (overrides profile when detectable)
    effective_lang = detect_reply_lang(message) or lang
    inject_dont_ask = bool(service and service != 'general')
    print(f"[AI] get_ai_response: effective_lang={effective_lang!r} inject_dont_ask={inject_dont_ask}")
    logger.info(f"[AI] get_ai_response: effective_lang={effective_lang!r} inject_dont_ask={inject_dont_ask}")

    # Build system prompt
    system_prompt = build_system_prompt(service or 'general', effective_lang)
    # When we already know the service, tell the model not to ask again
    if inject_dont_ask:
        system_prompt += "\n\nThe user has already stated they need this service. Do NOT ask what service they need. Start by acknowledging and asking the first question or document for this service."
        print(f"[AI] get_ai_response: appended 'don't ask again' line")
        logger.info("[AI] get_ai_response: appended don't ask again line")

    # Log that target language is in prompt (sanity check)
    if f"reply ONLY in " in system_prompt:
        logger.info("[AI] get_ai_response: system prompt contains 'reply ONLY in' (target lang)")
    else:
        print(f"[AI] get_ai_response: WARNING system prompt may not contain 'reply ONLY in'")
        logger.warning("[AI] get_ai_response: system prompt may not contain 'reply ONLY in'")

    # Prepare messages
    messages = [{'role': 'system', 'content': system_prompt}]
    
    # Add full conversation thread (ChatGPT-style) so the model knows what was already collected; cap at 500 for context limit safety
    if conversation_history:
        for msg in conversation_history[-500:]:
            role = msg.get('role', 'user')
            # Map non-standard roles to assistant
            if role not in ['user', 'assistant', 'system']:
                role = 'assistant'
            content = msg.get('content', '')
            if content:
                messages.append({'role': role, 'content': content})
    
    # Add current message if not already in history
    if message and (not conversation_history or conversation_history[-1].get('content') != message):
        messages.append({'role': 'user', 'content': message})
    
    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
            timeout=30
        )
        response_time = time.time() - start_time
        
        tokens = response.usage.total_tokens if response.usage else 0
        _track_usage(tokens, response_time=response_time)
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        _track_usage(error=True)
        return None


def _is_substantive_text(content: str) -> bool:
    """True if content is real text we should reply to, not a sticker or file placeholder."""
    if not content or not content.strip():
        return False
    c = content.strip()
    if c == '[Sticker]':
        return False
    if c.startswith('[FILE:'):
        return False
    return True


def ask_ai(conversation: list, service: str, lang: str = 'en', max_tokens: int = 800) -> str:
    """
    Call OpenAI API to get AI response.
    Legacy function - wraps get_ai_response for backwards compatibility.
    
    Args:
        conversation: List of conversation messages
        service: Service slug
        lang: Language code
        max_tokens: Maximum response tokens
        
    Returns:
        AI response text or None on error
    """
    # Last user message
    last_message = None
    for msg in reversed(conversation):
        if msg.get('role') == 'user':
            last_message = msg.get('content', '')
            break

    # If the last message is only [Sticker], prefer the most recent substantive text from the user
    # (e.g. user sent "Shengen visa keragidi" and a sticker in the same minute; we reply to the text)
    if last_message and last_message.strip() == '[Sticker]':
        for msg in reversed(conversation[:-1]):  # exclude the [Sticker] message
            if msg.get('role') == 'user' and _is_substantive_text(msg.get('content', '')):
                last_message = msg.get('content', '')
                break

    last_snippet = (last_message or '')[:80].replace('\n', ' ')
    print(f"[AI] ask_ai: conv_len={len(conversation or [])} last_message={last_snippet!r} service={service!r} lang={lang!r}")
    logger.info(f"[AI] ask_ai: conv_len={len(conversation or [])} last_message={last_snippet!r} service={service!r} lang={lang!r}")

    return get_ai_response(
        message=last_message or '',
        conversation_history=conversation[:-1] if conversation else None,
        service=service,
        lang=lang,
        max_tokens=max_tokens
    )


# ============== Voice Transcription ==============

def convert_audio(input_path: str, output_path: str = None) -> str:
    """
    Convert audio file to WAV format using ffmpeg.
    
    Args:
        input_path: Path to input audio file
        output_path: Optional path for output file (auto-generated if None)
        
    Returns:
        Path to converted file or None on error
    """
    input_path = Path(input_path)
    
    if not input_path.exists():
        logger.error(f"Audio file not found: {input_path}")
        return None
    
    if output_path is None:
        output_path = input_path.with_suffix('.wav')
    else:
        output_path = Path(output_path)
    
    try:
        # Run ffmpeg to convert audio
        cmd = [
            'ffmpeg', '-y',  # Overwrite output
            '-i', str(input_path),
            '-acodec', 'pcm_s16le',  # PCM 16-bit
            '-ar', '16000',  # 16kHz sample rate
            '-ac', '1',  # Mono
            str(output_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60
        )
        
        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr.decode()}")
            return None
        
        if output_path.exists():
            logger.info(f"Audio converted: {input_path} -> {output_path}")
            return str(output_path)
        
        return None
        
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg conversion timeout")
        return None
    except FileNotFoundError:
        logger.error("ffmpeg not found - please install ffmpeg")
        return None
    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        return None


def _transcribe_via_muxlisa(file_path: Path) -> str:
    """
    Transcribe an audio file using Muxlisa AI (Uzbek STT).
    Always converts to WAV first so the API receives a clean format.
    Returns transcribed text or None on error.
    """
    api_key = getattr(settings, 'MUXLISA_API_KEY', '') or os.getenv('MUXLISA_API_KEY', '')
    if not api_key:
        logger.error("MUXLISA_API_KEY not set — cannot transcribe Uzbek audio")
        return None

    temp_file = None
    wav_path = file_path

    # Always send WAV to Muxlisa for reliable results
    if file_path.suffix.lower() != '.wav':
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_file.close()
        converted = convert_audio(str(file_path), temp_file.name)
        if not converted:
            logger.error(f"Muxlisa: failed to convert {file_path.suffix} to WAV")
            return None
        wav_path = Path(converted)

    try:
        start_time = time.time()
        with open(wav_path, 'rb') as f:
            resp = _requests.post(
                'https://service.muxlisa.uz/api/v2/stt',
                headers={'x-api-key': api_key},
                files={'audio': (wav_path.name, f, 'audio/wav')},
                timeout=60,
            )
        elapsed = time.time() - start_time

        if resp.status_code != 200:
            logger.error(f"Muxlisa API error {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        # Muxlisa returns {"result": "...", ...} or plain text
        if isinstance(data, dict):
            text = data.get('result') or data.get('text') or data.get('transcription') or ''
        else:
            text = str(data)

        text = text.strip()
        logger.info(f"Muxlisa STT ({elapsed:.2f}s): {text[:50]}...")
        return text or None

    except Exception as e:
        logger.error(f"Muxlisa transcription error: {e}")
        return None

    finally:
        if temp_file and Path(temp_file.name).exists():
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass


def _transcribe_via_whisper(file_path: Path, lang_code: str = '') -> str:
    """
    Transcribe audio using OpenAI Whisper-1.
    Returns transcribed text or None on error.
    """
    client = get_openai_client()
    if not client:
        return None

    supported_formats = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}
    file_ext = file_path.suffix.lower()

    temp_file = None
    work_path = file_path
    if file_ext in {'.ogg', '.oga', '.opus'}:
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_file.close()
        converted = convert_audio(str(file_path), temp_file.name)
        if not converted:
            logger.error(f"Whisper: failed to convert {file_ext} to WAV")
            return None
        work_path = Path(converted)
    elif file_ext not in supported_formats:
        logger.error(f"Whisper: unsupported audio format: {file_ext}")
        return None

    try:
        start_time = time.time()
        with open(work_path, 'rb') as audio_file:
            kwargs = {'model': 'whisper-1', 'file': audio_file}
            lang_map = {'en': 'en', 'ru': 'ru'}
            whisper_lang = lang_map.get(lang_code)
            if whisper_lang:
                kwargs['language'] = whisper_lang
            response = client.audio.transcriptions.create(**kwargs)
        response_time = time.time() - start_time
        _track_usage(response_time=response_time)
        transcription = response.text if hasattr(response, 'text') else str(response)
        logger.info(f"Whisper STT ({response_time:.2f}s): {transcription[:60]}...")
        return transcription or None
    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        _track_usage(error=True)
        return None
    finally:
        if temp_file and Path(temp_file.name).exists():
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass


def _looks_sensible(text: str) -> bool:
    """
    Minimal sanity check: transcription must have at least 2 words and
    not be pure punctuation/numbers.
    """
    if not text or not text.strip():
        return False
    words = [w for w in text.strip().split() if any(c.isalpha() for c in w)]
    return len(words) >= 2


def transcribe_voice(file_path: str, language_hint: str = None) -> str:
    """
    Transcribe voice/audio.

    Always tries Muxlisa first (catches Uzbek regardless of chat language
    setting — most users of this service are Uzbek speakers even when their
    chat language is English or Russian).  Falls back to Whisper with
    auto-detection if Muxlisa returns nothing or gibberish.

    Returns transcribed text, or None if all attempts fail (callers should
    then ask the user to type).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        logger.error(f"Audio file not found: {file_path}")
        return None

    lang_code = (language_hint or '')[:2].lower()

    # Muxlisa first — always, regardless of chat language
    muxlisa_result = _transcribe_via_muxlisa(file_path)
    if muxlisa_result and _looks_sensible(muxlisa_result):
        logger.info(f"[STT] Muxlisa accepted: {muxlisa_result[:60]!r}")
        return muxlisa_result
    if muxlisa_result:
        logger.info(f"[STT] Muxlisa result failed sanity check ({muxlisa_result[:60]!r}), trying Whisper")
    else:
        logger.info("[STT] Muxlisa returned nothing, trying Whisper")

    # Whisper fallback — no forced language hint so it auto-detects
    whisper_result = _transcribe_via_whisper(file_path, lang_code)
    if whisper_result and _looks_sensible(whisper_result):
        logger.info(f"[STT] Whisper accepted: {whisper_result[:60]!r}")
        return whisper_result
    if whisper_result:
        logger.info(f"[STT] Whisper result failed sanity check ({whisper_result[:60]!r})")
    else:
        logger.info("[STT] Whisper returned nothing")

    logger.warning("[STT] All transcription attempts failed — asking user to type")
    return None


def transcribe_document(doc_id: int) -> str:
    """
    Transcribe a voice document from the database.
    
    Args:
        doc_id: Document database ID
        
    Returns:
        Transcribed text or None on error
    """
    from core.models import Document
    
    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        logger.error(f"Document {doc_id} not found")
        return None
    
    # Get file path
    file_id = doc.telegram_file_id
    if file_id.startswith('local:'):
        filename = file_id[6:]  # Remove "local:" prefix
        file_path = UPLOADS_DIR / filename
    else:
        # Remote file - would need to download first
        logger.error("Remote file transcription not implemented yet")
        return None
    
    # Get language hint from user
    language_hint = None
    if doc.case and doc.case.user:
        language_hint = doc.case.user.language_code
    
    # Transcribe
    text = transcribe_voice(str(file_path), language_hint)
    
    if text:
        # Save transcription to document
        doc.transcription = text
        doc.save(update_fields=['transcription'])
    
    return text


# ============== Document Naming ==============

def suggest_document_name(conversation: list, media_type: str, user_telegram_id: int, ext: str = '') -> str:
    """
    Use AI to suggest a short filename label for an uploaded file from conversation context.
    Returns a label like "birth_certificate" or "passport" (no extension), or empty on failure.
    """
    client = get_openai_client()
    if not client or not conversation:
        return ''
    conv_text = "\n".join([
        f"{m.get('role', 'user')}: {(m.get('content') or '')[:200]}"
        for m in conversation[-15:]
        if m.get('content') and not (m.get('content') or '').strip().startswith('[FILE:')
    ])
    if not conv_text.strip():
        return ''
    prompt = f"""The user just sent a {media_type} file. From the conversation, what document did they say they are sending?
Reply with ONLY a short snake_case label (e.g. birth_certificate, passport, id_front, receipt, p60, bank_statement). No path, no extension, no other text. Use exactly what the user said they would send. If you cannot tell, reply: unknown
Conversation:
{conv_text[:1500]}"""
    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=25,
            temperature=0.2
        )
        raw = (response.choices[0].message.content or '').strip().split('\n')[0].strip()
        label = re.sub(r'[^\w\-]', '_', raw)[:50].strip('_').lower().replace(' ', '_')
        return label if label and label != 'unknown' else ''
    except Exception as e:
        logger.debug(f"Suggest document name error: {e}")
        return ''


def parse_filename_from_response(response_text: str):
    """
    If the AI ended with a line FILENAME: label, return (response_without_that_line, label).
    Otherwise return (response_text, None).
    """
    if not response_text or 'FILENAME:' not in response_text:
        return (response_text, None)
    lines = response_text.strip().split('\n')
    out_lines = []
    label = None
    for line in lines:
        s = line.strip()
        if s.upper().startswith('FILENAME:'):
            label = s[9:].strip()
            label = re.sub(r'[^\w\-]', '_', label)[:50].strip('_')
            continue
        out_lines.append(line)
    cleaned = '\n'.join(out_lines).strip()
    return (cleaned, label or None)


# ============== Profile Extraction ==============

def extract_profile_info(conversation_history: list) -> dict:
    """
    Extract user profile information from conversation history using AI.
    
    Args:
        conversation_history: List of conversation messages
        
    Returns:
        Dictionary with extracted profile data
    """
    client = get_openai_client()
    if not client:
        return {}
    
    if not conversation_history:
        return {}
    
    # Build conversation text
    conv_text = "\n".join([
        f"{msg.get('role', 'user')}: {msg.get('content', '')}"
        for msg in conversation_history[-80:]  # Last 80 messages
        if msg.get('content') and not msg.get('content', '').startswith('[FILE:')
    ])
    
    if not conv_text:
        return {}
    
    system_prompt = """Analyze this conversation and extract any useful information about the user that would help a consultant (demographics, contact, immigration, employment, preferences, situation, etc.).

Return ONLY a valid JSON object with two keys:
1) "extracted": an object with snake_case keys and values (e.g. gender, age, full_name, nationality, email, phone, occupation, visa_status, country_of_residence, service_interest, budget, urgency). Include only keys for which you found clear information. Omit keys with null or unknown values.
2) "pinned": an array of 1 to 5 objects, each with "label" and "value". Pick the most important facts for a consultant to see at a glance (e.g. visa status, service need, urgency, gender, key constraint). Use short human-readable labels (e.g. "Visa status", "Service", "Urgency"). Example: [{"label": "Visa status", "value": "Student"}, {"label": "Urgency", "value": "By September"}].

Extraction examples (not a fixed list): full_name, gender, age, nationality, email, phone, occupation, visa_status, country_of_residence, service_interest, budget, urgency, family_status, education, employer, notes. Normalize values to be short and readable. Be conservative: only include information that is clearly stated or strongly implied. Do not make up or guess."""
    
    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': conv_text}
            ],
            max_tokens=800,
            temperature=0.1
        )
        response_time = time.time() - start_time
        tokens = response.usage.total_tokens if response.usage else 0
        _track_usage(tokens, response_time=response_time)
        
        response_text = response.choices[0].message.content
        
        # Try to parse JSON from response
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]
        
        data = json.loads(response_text.strip())
        # Support both new format {extracted, pinned} and legacy flat object
        if isinstance(data, dict) and 'extracted' in data:
            return data
        if isinstance(data, dict):
            return {'extracted': data, 'pinned': []}
        return {'extracted': {}, 'pinned': []}
        
    except json.JSONDecodeError as e:
        logger.error(f"Profile extraction JSON error: {e}")
        return {'extracted': {}, 'pinned': []}
    except Exception as e:
        logger.error(f"Profile extraction error: {e}")
        _track_usage(error=True)
        return {'extracted': {}, 'pinned': []}


def update_user_profile(user_db_id: int, force: bool = False) -> dict:
    """
    Update user's AI profile from their conversation history.
    
    Args:
        user_db_id: TgUser database ID
        force: Force update even if recently updated
        
    Returns:
        Updated profile data dictionary
    """
    from core.models import TgUser, Case, UserAiProfile
    from datetime import datetime, timedelta
    
    try:
        user = TgUser.objects.get(pk=user_db_id)
    except TgUser.DoesNotExist:
        return {}
    
    # Check if we should update
    ai_profile, created = UserAiProfile.objects.get_or_create(user=user)
    
    if not force and not created and ai_profile.updated_at:
        # Throttle: skip if updated in the last 2 minutes (analyze after every message, but limit API calls)
        elapsed = (datetime.now() - ai_profile.updated_at).total_seconds()
        if elapsed < 120:
            try:
                return json.loads(ai_profile.extracted_data or '{}')
            except Exception:
                pass
    
    # Collect all conversation messages
    all_messages = []
    for case in user.cases.all():
        conv = case.get_conversation()
        all_messages.extend(conv)
    
    if not all_messages:
        return {}
    
    # Extract profile info (returns {extracted: {...}, pinned: [...]})
    result = extract_profile_info(all_messages)
    new_data = result.get('extracted') or {}
    new_pinned = result.get('pinned') or []
    
    if new_data or new_pinned:
        try:
            existing_data = json.loads(ai_profile.extracted_data or '{}')
        except Exception:
            existing_data = {}
        
        for key, value in new_data.items():
            if value is not None and (not isinstance(value, str) or value.strip()):
                existing_data[key] = value if not isinstance(value, str) else value.strip()
        
        ai_profile.extracted_data = json.dumps(existing_data)
        # Save pinned: replace with AI-selected pinned items (only valid entries)
        pinned_list = []
        for item in new_pinned:
            if isinstance(item, dict) and item.get('label') and item.get('value'):
                pinned_list.append({
                    'label': str(item['label']).strip(),
                    'value': str(item['value']).strip()
                })
        ai_profile.pinned_data = json.dumps(pinned_list[:10])  # cap at 10
        ai_profile.save()
        
        user.set_profile_data(existing_data)
        
        logger.info(f"Updated AI profile for user {user_db_id}")
        return existing_data
    
    return {}


def extract_user_profile(user_db_id: int) -> dict:
    """
    Extract user profile information from conversation history using AI.
    Legacy function - wraps update_user_profile for backwards compatibility.
    
    Args:
        user_db_id: TgUser database ID
        
    Returns:
        Dictionary with extracted profile data
    """
    return update_user_profile(user_db_id, force=True)


# ============== Report AI Conclusions ==============

def generate_ai_conclusions(report_data: dict, report_type: str = 'general') -> str:
    """
    Generate AI-driven business insights for a report.
    
    Args:
        report_data: Dictionary with report statistics
        report_type: Type of report (daily, weekly, monthly, quarterly)
        
    Returns:
        AI-generated conclusions text
    """
    client = get_openai_client()
    if not client:
        return _generate_template_conclusion(report_data, report_type)
    
    # Build analysis prompt
    prompt = f"""Analyze the following business statistics for Brightway Consulting, a UK-based firm that handles tax and immigration services.

Report Type: {report_type.capitalize()}
Period: {report_data.get('period_start', 'N/A')} to {report_data.get('period_end', 'N/A')}

Statistics:
- New Users: {report_data.get('new_users', 0)}
- New Cases: {report_data.get('new_cases', 0)}
- Completed Cases: {report_data.get('completed_cases', 0)}
- Active Cases: {report_data.get('active_cases', 0)}
- Paid Cases: {report_data.get('paid_cases', 0)}
- Total Revenue: £{report_data.get('total_revenue', 0):.2f}
- Documents Uploaded: {report_data.get('docs_uploaded', 0)}

Cases by Service:
{json.dumps(report_data.get('by_service', {}), indent=2)}

Cases by Status:
{json.dumps(report_data.get('by_status', {}), indent=2)}

Please provide a 2-3 paragraph business analysis including:
1. Key performance highlights and notable trends
2. Areas of strength and potential concerns
3. Actionable recommendations for improvement

Be specific with numbers and percentages where relevant.
Keep the tone professional and constructive."""

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    'role': 'system',
                    'content': 'You are a business analyst providing insights for a UK consulting firm specializing in tax and immigration services. Be concise, specific, and actionable.'
                },
                {'role': 'user', 'content': prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )
        response_time = time.time() - start_time
        tokens = response.usage.total_tokens if response.usage else 0
        _track_usage(tokens, response_time=response_time)
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"AI conclusions generation error: {e}")
        _track_usage(error=True)
        return _generate_template_conclusion(report_data, report_type) + f"\n\n*(AI analysis unavailable)*"


def _generate_template_conclusion(report_data: dict, report_type: str) -> str:
    """Generate a template conclusion when AI is unavailable."""
    return f"""## {report_type.capitalize()} Business Summary

**Performance Overview:**
During this period, we registered {report_data.get('new_users', 0)} new users and opened {report_data.get('new_cases', 0)} new cases. The team completed {report_data.get('completed_cases', 0)} cases, with {report_data.get('active_cases', 0)} currently active.

**Financial Highlights:**
We recorded {report_data.get('paid_cases', 0)} paid cases with total revenue of £{report_data.get('total_revenue', 0):.2f}. Document processing remained steady with {report_data.get('docs_uploaded', 0)} files uploaded.

**Recommendations:**
Continue monitoring case completion rates and follow up on pending payments to optimize cash flow."""


# ============== Service Steps ==============

def get_service_steps(service: str) -> list:
    """
    Get the steps for a service workflow.
    
    Args:
        service: Service slug
        
    Returns:
        List of ServiceStep objects
    """
    from core.models import ServiceDefinition, ServiceStep
    
    try:
        svc_def = ServiceDefinition.objects.filter(slug=service, is_active=True).first()
        if svc_def:
            return list(svc_def.steps.all().order_by('step_number'))
    except Exception as e:
        logger.error(f"Error loading service steps: {e}")
    
    return []


# ============== Test AI Prompt ==============

def test_ai_prompt(system_prompt: str, user_message: str) -> str:
    """
    Test an AI system prompt with a sample user message.
    Used by the services management page.
    
    Args:
        system_prompt: The system prompt to test
        user_message: Sample user message
        
    Returns:
        AI response or error message
    """
    client = get_openai_client()
    if not client:
        return "Error: OpenAI API key not configured"
    
    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message}
            ],
            max_tokens=500,
            temperature=0.3,
            timeout=30
        )
        response_time = time.time() - start_time
        tokens = response.usage.total_tokens if response.usage else 0
        _track_usage(tokens, response_time=response_time)
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Test prompt error: {e}")
        _track_usage(error=True)
        return f"Error: {str(e)}"


# ============== Cache Management ==============

# ============== Conversation Management Helpers ==============

def should_update_profile(message_count: int) -> bool:
    """Check if we should trigger profile extraction (after every user message; throttled inside update_user_profile)."""
    return message_count > 0


def get_fallback_response(lang: str = 'en') -> str:
    """Get a fallback response when AI fails."""
    fallbacks = {
        'en': "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment, or contact us directly through our website.",
        'ru': "Извините, у меня возникли проблемы с обработкой вашего запроса. Пожалуйста, попробуйте снова через минуту или свяжитесь с нами напрямую через наш сайт.",
        'uz': "Kechirasiz, so'rovingizni qayta ishlashda muammo yuz berdi. Iltimos, bir daqiqadan keyin qayta urinib ko'ring yoki veb-saytimiz orqali biz bilan bog'laning."
    }
    return fallbacks.get(lang, fallbacks['en'])
