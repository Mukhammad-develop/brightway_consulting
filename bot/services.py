"""
AI Services for Brightway Consulting Telegram bot.

Handles service detection, system prompts, AI interactions, voice transcription,
and profile extraction using OpenAI APIs (GPT-4o-mini and Whisper-1).
"""

import os
import re
import sys
import time
import json
import logging
import subprocess
import tempfile
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

# Hardcoded service info (fallback)
SERVICE_INFO = {
    'student': {
        'collect_items': ['Full name', 'Passport number', 'Date of birth', 'University name', 'Course details', 'CAS number'],
        'documents': ['Passport scan', 'University acceptance letter', 'Financial documents', 'English test results']
    },
    'paye': {
        'collect_items': ['Full name', 'National Insurance number', 'Tax years', 'Employer details', 'Email and phone', 'Address outside UK (Uzb/KZ/KGZ/TJK)', 'Sort code and account number', 'How many times have you come to work (nechinchi bor kelishingiz ishga?)'],
        'documents': ['P45 (PDF / fayli shaklida)', 'Passport (rasm / scaner qilib)', 'Address outside UK - Uzb/KZ/KGZ/TJK', 'National Insurance number', 'Email and phone', 'Card details - Sort code and account number (Angliya kartangizdan)', 'Nechinchi bor kelishingiz ishga?'],
        'strict_flow': True
    },
    'schengen': {
        'collect_items': ['Full name', 'Passport number', 'Sharecode', 'Evisa', 'Yashash manzili (address)', "O'qish yoki ish joyidan malumotnoma", 'Email', 'Phone number', 'Full-time payslip if applicable', 'Last 3 months bank statement'],
        'documents': ['Passport', 'Sharecode', 'Evisa', 'Yashash manzili', "O'qish yoki ish joyidan malumotnoma", 'Email', 'Phone number', 'Photo 3.5×4.5', 'Payslip (if full-time)', 'Bank statement – last 3 months (ohirgi 3 oylik)'],
    },
    'self': {
        'collect_items': ['Full name', 'UTR number', 'Tax year', 'Income sources', 'Expenses'],
        'documents': ['ID document', 'Bank statements', 'Income records', 'Expense receipts']
    },
    'company': {
        'collect_items': ['Company name', 'Company number', 'Director details', 'VAT registration'],
        'documents': ['Certificate of incorporation', 'Bank statements', 'Invoices', 'Receipts']
    }
}

# Tone rules for AI
TONE_RULES = """
TONE RULES:
- Sound like a real consultant in a live chat, not a formal letter
- Be friendly but professional; be nice and welcoming to the user
- At the start of the conversation, mention that you're glad they contacted Brightway Consulting (e.g. "Рады, что вы обратились в Brightway Consulting!" / "Glad you're here at Brightway Consulting!" / same in Uzbek)
- Use emojis sometimes — not a lot, one or two per message when it fits (e.g. 👋 at greeting, ✅ when you got something). Don't overdo it
- Use natural conversational language
- Keep responses concise but helpful
- Ask one question at a time
- Acknowledge what the user says before asking for more
"""

# Anti-bot patterns
ANTI_BOT_PATTERNS = """
AVOID THESE PATTERNS:
- Don't say "Great!", "Absolutely!", "Certainly!"
- Don't say "Kindly provide..."
- Don't use overly formal phrases
- Don't repeat the same greeting structure
- Don't use numbered lists for simple questions
"""

# Style examples
STYLE_EXAMPLES = """
GOOD EXAMPLES:
EN: "Got it! And what's your passport number?"
EN: "Thanks for that. Do you have a copy of your P45?"
RU: "Понял! А какой у вас номер паспорта?"
UZ: "Tushundim! Pasport raqamingiz qanday?"
UZ (natural): "Yaxshi, tushundim. To'liq ismingizni yozib bering." / "Rahmat. Endi P45 nusxangiz bormi?"
"""

# Natural language for Uzbek and Russian
NATURAL_LANGUAGE = """
When replying in Uzbek or Russian, sound natural and conversational:
- Use everyday spoken language, as in a friendly chat or text message. Avoid stiff, formal, or textbook phrases.
- In Uzbek: avoid overly formal wording like "Avvalambor", "Sizdan bir nechta ma'lumot kerak bo'ladi" – prefer shorter, natural phrases (e.g. "Ismingiz nima?", "Ma'lumotlaringizni yozing").
- In Russian: same – use normal spoken Russian, not official or translated tone.
- Match how a real consultant would text a client in that language, not a formal letter or machine translation.
"""

# Marker in AI response when info collection is complete and user should be assigned to a consultant
READY_FOR_CONSULTANT_MARKER = '[READY_FOR_CONSULTANT]'

# Behavior: collect information then assign to consultant
COLLECT_AND_ASSIGN_BEHAVIOR = """
YOUR ROLE:
- You are an assistant for Brightway Consulting. Your job is to collect the information and documents we need for the user's service, then assign them to a human consultant.
- At the start of the conversation (or when the user chooses a service), briefly state: you will collect the required information and then assign them to a consultant who will take over.
- Collect information and documents step by step: ask for one thing at a time, acknowledge what they provide, then ask for the next. Use the "Information to collect" and "Documents to request" lists above as your checklist.
- When you have collected ALL required information and documents listed for this service, end your reply with exactly """ + READY_FOR_CONSULTANT_MARKER + """ (on its own line, no other text after it). Before that line you may say e.g. "I have everything I need. I'm assigning you to a consultant who will contact you shortly."
- Do NOT output """ + READY_FOR_CONSULTANT_MARKER + """ until you have collected every required item and document.
"""

# General system prompt
GENERAL_SYSTEM_PROMPT = """You are a helpful AI assistant for Brightway Consulting, a UK-based consultancy 
that helps with student visas, tax refunds, and company accounting.

Your job is to:
1. Understand what service the user needs
2. Collect necessary information and documents (step by step)
3. When collection is complete, assign them to a consultant (end your message with """ + READY_FOR_CONSULTANT_MARKER + """)
4. Be helpful and professional

If you can't determine what service they need, ask clarifying questions.
"""


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
    from core.models import ServiceDefinition
    
    lang_map = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}
    target_lang = lang_map.get(lang, 'English')
    
    # Try to get service definition from database
    svc_def = None
    try:
        svc_def = ServiceDefinition.objects.filter(slug=service, is_active=True).first()
    except Exception as e:
        logger.error(f"Error loading service definition: {e}")
    
    if svc_def and svc_def.ai_system_prompt:
        # Use custom AI system prompt from database
        if svc_def.ai_strict_flow:
            # Strict flow - use prompt as-is
            base_prompt = svc_def.ai_system_prompt
        else:
            # Flexible flow - append collect items and documents
            base_prompt = svc_def.ai_system_prompt
            
            collect_items = svc_def.get_collect_items()
            if collect_items:
                base_prompt += f"\n\nInformation to collect:\n" + "\n".join(f"- {item}" for item in collect_items)
            
            documents = svc_def.get_documents_list()
            if documents:
                base_prompt += f"\n\nDocuments to request:\n" + "\n".join(f"- {doc}" for doc in documents)
    else:
        # Fallback to hardcoded prompts
        base_prompt = _build_hardcoded_prompt(service)
    
    # Append collect-then-assign behavior (for non-general services) and common rules
    if service and service != 'general':
        base_prompt = base_prompt.rstrip() + "\n\n" + COLLECT_AND_ASSIGN_BEHAVIOR
    # Append common rules
    full_prompt = f"""{base_prompt}

{TONE_RULES}

{ANTI_BOT_PATTERNS}

{STYLE_EXAMPLES}

CRITICAL – Language: You MUST reply in the same language as the user's last message. If the user wrote in Russian (e.g. Привет, мне нужна помощь), reply ONLY in Russian. If they wrote in Uzbek, reply ONLY in Uzbek. If they wrote in English, reply in English. Never reply in English when the user wrote in Russian or Uzbek. Check the user's message: Russian uses Cyrillic (Привет, как, виза); Uzbek may use Latin (Salom, yordam) or Cyrillic. Match it.

{NATURAL_LANGUAGE}

Respond to the user's actual last message. If their message is normal text (e.g. a question or request in any language), answer that text.
If the user has ALREADY said they need visa, tax refund, or accounting (e.g. "мне нужна помощь по визе", "help with visa", "tax refund", "виза", "налог", "бухгалтерия") — do NOT ask again "what do you need?" or "visa, tax or accounting?". Acknowledge their request and start collecting information for that service immediately (e.g. ask for their full name or first doc). Only ask "what service do you need?" when they have NOT mentioned visa, tax, or accounting (e.g. only "Привет" or "Hello").
When the user's message is exactly "[Sticker]" (they sent a sticker only): do NOT say "it seems you sent a sticker", "you sent a sticker", or similar. Instead reply briefly asking them to type what they need (e.g. Schengen visa, tax refund, accounting) so you can help. When the user sent plain text, do not refer to stickers.

When the user has just sent a file (photo, document, voice, video), you may suggest a short filename so we can label it. If you can infer what the file is (e.g. passport, id_front, receipt, p60), end your message with a line: FILENAME: label (e.g. FILENAME: passport or FILENAME: id_front). Use one or two words, no path and no extension. If unsure, omit this line.

This turn, you MUST reply ONLY in {target_lang}. Do not switch to another language.
"""
    
    return full_prompt


def _build_hardcoded_prompt(service: str) -> str:
    """Build prompt from hardcoded service info."""
    
    if service == 'student':
        return """You are an AI assistant helping with Student Visa and University applications for the UK.

Your job is to collect the following information from the user:
- Full name (as in passport)
- Passport number
- Date of birth
- University name and course
- CAS number (if available)
- Previous UK visa history

Request these documents:
- Passport scan (photo page)
- University acceptance letter
- Financial documents (bank statements)
- English test results (IELTS/TOEFL)

Guide them step by step, asking for one piece of information at a time."""

    elif service == 'paye':
        return """You are an AI assistant helping with PAYE Tax Refund claims in the UK.

Collect the following information and request these documents (one at a time):

Information to collect:
- Full name
- National Insurance raqamingiz (National Insurance number)
- Which tax years they want to claim (last 4 years possible)
- Employer details (name, dates worked)
- Email manzilingiz va telefon raqamingiz (email and phone number)
- Angliyadan tashqaridagi manzilingiz – Uzb/KZ/KGZ/TJK (address outside UK)
- Karta rekvizitlaringiz: Sort code va account nomer (from your UK bank card)
- Nechinchi bor kelishingiz ishga? (How many times have you come to work?)

Documents to request:
- P45 – PDF / fayli shaklida (in file/PDF form)
- Pasportingiz – rasm yoki scaner qilib (passport – photo or scan)
- Angliyadan tashqaridagi manzilingiz (Uzb/KZ/KGZ/TJK)
- National Insurance raqamingiz
- Email va telefon raqamingiz
- Karta rekvizitlaringiz – Angliya kartangizdan Sort code va account nomer
- Nechinchi bor kelishingiz ishga? (answer in text)

Only move to the next step after completing the current one. When speaking to Uzbek-speaking users, use Uzbek for explanations and document names where listed above."""

    elif service == 'schengen':
        return """You are an AI assistant helping with Schengen visa applications.

Collect the following information and request these documents (one at a time):

Information to collect:
- Full name (as in passport)
- Passport number and validity
- Sharecode
- Evisa (if applicable)
- Yashash manzili (residence address)
- O'qish yoki ish joyidan malumotnoma (letter from school or employer)
- Email and phone number
- If working full-time: payslip
- Last 3 months bank statement (ohirgi 3 oylik bank statement)

Documents to request:
- Passport
- Sharecode
- Evisa
- Yashash manzili (proof of address)
- O'qish yoki ish joyidan malumotnoma
- Email and telephone number (written/confirmed)
- Rasm 3.5×4.5 (photo 3.5×4.5 cm)
- Full-time ishlasa: payslip
- Bank statement – last 3 months (ohirgi 3 oylik)

Guide them step by step. When the user writes in Uzbek, use Uzbek for explanations and document names where listed above."""

    elif service == 'self':
        return """You are an AI assistant helping with Self Assessment Tax Returns in the UK.

Collect the following information:
- Full name and UTR number
- Tax year for the return
- Sources of income (self-employment, rental, dividends, etc.)
- Business expenses to claim
- Previous tax returns submitted

Request these documents:
- Bank statements for the tax year
- Income records/invoices
- Expense receipts
- Previous tax return (if available)

Guide them through the information collection process."""

    elif service == 'company':
        return """You are an AI assistant helping with Company Accounting services in the UK.

Collect the following information:
- Company name and registration number
- Director details
- Financial year end date
- VAT registration status
- Payroll requirements

Request these documents:
- Certificate of incorporation
- Bank statements
- Sales invoices
- Purchase receipts
- Payroll records (if applicable)

Understand their accounting needs and guide them accordingly."""

    else:
        return GENERAL_SYSTEM_PROMPT


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
    
    # Add conversation history (limited to last 20 messages)
    if conversation_history:
        for msg in conversation_history[-20:]:
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


def transcribe_voice(file_path: str, language_hint: str = None) -> str:
    """
    Transcribe voice/audio file using OpenAI Whisper-1.
    
    Args:
        file_path: Path to audio file
        language_hint: Optional language hint (ISO 639-1 code)
        
    Returns:
        Transcribed text or None on error
    """
    client = get_openai_client()
    if not client:
        return None
    
    file_path = Path(file_path)
    if not file_path.exists():
        logger.error(f"Audio file not found: {file_path}")
        return None
    
    # Whisper-1 supported formats
    supported_formats = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}
    file_ext = file_path.suffix.lower()
    
    # Convert if needed
    temp_file = None
    if file_ext in {'.ogg', '.oga', '.opus'}:
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_file.close()
        converted_path = convert_audio(str(file_path), temp_file.name)
        if not converted_path:
            logger.error(f"Failed to convert {file_ext} to WAV")
            return None
        file_path = Path(converted_path)
    elif file_ext not in supported_formats:
        logger.error(f"Unsupported audio format: {file_ext}")
        return None
    
    try:
        start_time = time.time()
        
        # Prepare API call
        with open(file_path, 'rb') as audio_file:
            kwargs = {
                'model': 'whisper-1',
                'file': audio_file,
            }
            
            # Add language hint if provided
            if language_hint:
                # Map our codes to Whisper codes
                lang_map = {
                    'en': 'en',
                    'ru': 'ru',
                    'uz': 'uz',
                }
                whisper_lang = lang_map.get(language_hint[:2].lower())
                if whisper_lang:
                    kwargs['language'] = whisper_lang
            
            response = client.audio.transcriptions.create(**kwargs)
        
        response_time = time.time() - start_time
        _track_usage(response_time=response_time)
        
        transcription = response.text if hasattr(response, 'text') else str(response)
        logger.info(f"Transcribed audio ({response_time:.2f}s): {transcription[:50]}...")
        
        return transcription
        
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        _track_usage(error=True)
        return None
    
    finally:
        # Clean up temp file
        if temp_file and Path(temp_file.name).exists():
            try:
                os.unlink(temp_file.name)
            except:
                pass


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
