"""
Shared state-machine logic for the simplified conversation flow (simpled branch).

This module is bot-transport-agnostic: it contains state management,
database helpers, AI calls and message-string builders.
Both simple_bot.py (pyTelegramBotAPI) and userbot.py (Telethon) import from here
so the flow logic is defined exactly once.

AI is used ONLY for:
  - Language detection          (detect_lang)
  - Fuzzy subject matching      (_ai_match_subject)
  - Fuzzy service matching      (_ai_match_service)
  - "Done" confirmation detect  (is_done_message)
  - Paraphrased thank-you msg   (generate_final_message)
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Step constants ─────────────────────────────────────────────────────────────
STEP_INIT = 'init'
STEP_LANG = 'awaiting_lang'
STEP_SUBJECT = 'awaiting_subject'
STEP_SERVICE = 'awaiting_service'
STEP_COLLECTING = 'collecting'
STEP_CONFIRM_CONSULTANT = 'confirm_consultant'
STEP_DONE = 'done'

_STATE_TTL_SECONDS = 3600  # idle state expires after 1 hour

# ── In-memory conversation state ───────────────────────────────────────────────
# Shared by whichever transport is running in this process.
# {user_tg_id (int): {'step', 'lang', 'subject_id', 'service_id',
#                     'case_id', 'items_to_collect', 'last_activity'}}
_state: dict = {}


# ── State helpers ──────────────────────────────────────────────────────────────

def get_state(uid: int) -> dict:
    s = _state.get(uid, {})
    if s:
        last = s.get('last_activity')
        if last and (datetime.now() - last).seconds > _STATE_TTL_SECONDS:
            _state.pop(uid, None)
            return {}
    return s


def set_state(uid: int, **kwargs) -> None:
    if uid not in _state:
        _state[uid] = {}
    _state[uid].update(kwargs)
    _state[uid]['last_activity'] = datetime.now()


def clear_state(uid: int) -> None:
    _state.pop(uid, None)


# ── Database helpers ───────────────────────────────────────────────────────────

def get_active_subjects() -> list:
    """Return ordered list of active Subject objects."""
    from core.models import Subject
    return list(Subject.objects.filter(is_active=True).order_by('display_order', 'name'))


def get_services_for_subject(subject_id: int) -> list:
    """Return ordered list of active ServiceDefinition objects for the subject."""
    from core.models import ServiceDefinition
    return list(
        ServiceDefinition.objects.filter(
            subject_id=subject_id, is_active=True
        ).order_by('display_order', 'name')
    )


def db_get_or_create_user(tg_id: int, first_name: str = None, username: str = None):
    """Get or create TgUser. Returns (user, created)."""
    from core.models import TgUser
    return TgUser.objects.get_or_create(
        telegram_id=tg_id,
        defaults={'first_name': first_name, 'username': username, 'language_code': ''},
    )


def db_save_user_language(tg_id: int, lang: str) -> None:
    """Persist user-chosen language to TgUser record."""
    from core.models import TgUser
    TgUser.objects.filter(telegram_id=tg_id).update(language_code=lang)


def db_get_or_open_case(user, service_slug: str = 'general'):
    """Return the user's active case or create a new one."""
    from core.models import Case
    case = Case.objects.filter(user=user, status='active').first()
    if not case:
        case = Case.objects.create(user=user, service=service_slug, status='active')
        logger.info('Created case #%s for user %s', case.pk, user.telegram_id)
    return case


def db_flush_pending_messages(case, uid: int) -> None:
    """
    Flush any user messages buffered in state before the case existed
    (i.e. sent during STEP_INIT / STEP_SUBJECT) into the case conversation.
    """
    state = get_state(uid)
    pending = state.get('pending_msgs', [])
    if not pending:
        return
    for role, content in pending:
        case.add_message(role, content)
    set_state(uid, pending_msgs=[])


def db_link_case_to_service(case, service_def, subject_id: int = None):
    """Link a case to a ServiceDefinition and optionally a Subject. Saves the case."""
    from core.models import Subject
    case.service = service_def.slug
    case.service_definition = service_def
    save_fields = ['service', 'service_definition']
    if subject_id:
        try:
            case.subject = Subject.objects.get(pk=subject_id)
            save_fields.append('subject')
        except Subject.DoesNotExist:
            pass
    case.save(update_fields=save_fields)


def db_try_assign_consultant(case, user):
    """Assign the least-loaded responsible consultant. Returns the consultant or None."""
    from django.db.models import Count
    from core.models import AdminUser, AdminAssignment

    qs = AdminUser.objects.filter(is_active=True, responsible_services__slug=case.service)
    consultant = (
        qs.annotate(n=Count('assigned_cases')).order_by('n', 'username').first()
    )
    if not consultant:
        consultant = (
            AdminUser.objects.filter(role='consultant', is_active=True)
            .annotate(n=Count('assigned_cases'))
            .order_by('n', 'username')
            .first()
        )
    if not consultant:
        consultant = AdminUser.objects.filter(is_active=True).order_by('role', 'username').first()
    if consultant:
        case.assigned_to = consultant
        case.save(update_fields=['assigned_to'])
        AdminAssignment.objects.get_or_create(admin=consultant, user=user)
        logger.info('Case #%s assigned to %s', case.pk, consultant.username)
    return consultant


def db_notify_consultant(consultant, case) -> None:
    """Create a panel Notification for the assigned consultant."""
    from core.models import Notification
    if not consultant:
        return
    Notification.objects.create(
        admin_user=consultant,
        title=f'New case: {case.service}',
        message=(
            f'New case #{case.pk} assigned to you.\n'
            f'Client: {case.user}\n'
            f'Service: {case.service}'
        ),
        link=f'/admin/cases/{case.pk}',
    )


def db_finalise_case(uid: int, tg_id: int, first_name: str, username: str, lang: str) -> str:
    """
    Finalise the case: assign consultant, disable AI, store final message.
    Returns the final thank-you message text.
    Called from both simple_bot (sync) and userbot (via run_sync executor).
    """
    user, _ = db_get_or_create_user(tg_id, first_name, username)
    state = get_state(uid)
    case_id = state.get('case_id')
    if not case_id:
        return generate_final_message(lang)

    from core.models import Case
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return generate_final_message(lang)

    consultant = db_try_assign_consultant(case, user)
    case.ai_enabled = False
    case.save(update_fields=['ai_enabled'])

    final_msg = generate_final_message(lang)
    case.add_message('assistant', final_msg)
    db_notify_consultant(consultant, case)
    set_state(uid, step=STEP_DONE)
    logger.info('Case #%s finalised (userbot) for user %s', case.pk, tg_id)
    return final_msg


# ── AI helpers ─────────────────────────────────────────────────────────────────

def detect_lang(text: str, fallback: str = 'en') -> str:
    """Detect message language, returning 'en', 'ru', or 'uz'."""
    from bot.services import detect_reply_lang
    result = detect_reply_lang(text)
    return result if result in ('en', 'ru', 'uz') else fallback


def ai_match_subject(text: str, subjects: list, lang: str) -> int | None:
    """AI fuzzy-match user text to a Subject. Returns pk or None."""
    if not subjects:
        return None
    from bot.services import get_openai_client
    client = get_openai_client()
    if not client:
        return None
    options = '\n'.join(
        f'- id={s.pk}: {s.name} / {s.name_ru or s.name} / {s.name_uz or s.name}'
        for s in subjects
    )
    system = (
        'Match the user reply to one of these subject categories.\n'
        f'{options}\n\n'
        'Reply with ONLY the numeric id of the best match, or "none". No other text.'
    )
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': text}],
            max_tokens=10, temperature=0.0, timeout=10,
        )
        raw = resp.choices[0].message.content.strip().lower()
        return None if raw == 'none' else int(raw)
    except Exception as e:
        logger.warning('ai_match_subject error: %s', e)
        return None


def ai_match_service(text: str, services: list, lang: str) -> int | None:
    """AI fuzzy-match user text to a ServiceDefinition. Returns pk or None."""
    if not services:
        return None
    from bot.services import get_openai_client
    client = get_openai_client()
    if not client:
        return None
    options = '\n'.join(
        f'- id={s.pk}: {s.name} / {s.name_ru or s.name} / {s.name_uz or s.name}'
        for s in services
    )
    system = (
        'Match the user reply to one of these services.\n'
        f'{options}\n\n'
        'Reply with ONLY the numeric id of the best match, or "none". No other text.'
    )
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': text}],
            max_tokens=10, temperature=0.0, timeout=10,
        )
        raw = resp.choices[0].message.content.strip().lower()
        return None if raw == 'none' else int(raw)
    except Exception as e:
        logger.warning('ai_match_service error: %s', e)
        return None


_DONE_KEYWORDS = {
    'en': {'done', 'ready', "that's all", 'thats all', 'finished', 'complete', 'completed', 'sent', 'all done'},
    'ru': {'готово', 'всё', 'все', 'готов', 'готова', 'закончил', 'закончила', 'отправил', 'отправила'},
    'uz': {'bitti', 'tayyor', 'tamom', 'bajarildi', 'yubordim', 'hammasi', 'tashlab boldim'},
}


def is_done_message(text: str, lang: str = 'en') -> bool:
    """Return True if the user is signalling they have sent all required information."""
    if not text:
        return False
    lower = text.strip().lower()
    for keywords in _DONE_KEYWORDS.values():
        for kw in keywords:
            if lower == kw or lower.startswith(kw):
                return True
    from bot.services import get_openai_client
    client = get_openai_client()
    if not client:
        return False
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': (
                    'You decide if a user message means they have finished sending '
                    'all required documents/information. Reply with YES or NO only.'
                )},
                {'role': 'user', 'content': text},
            ],
            max_tokens=3, temperature=0.0, timeout=8,
        )
        return resp.choices[0].message.content.strip().upper().startswith('YES')
    except Exception:
        return False


def find_faq_answer(text: str, service_def, lang: str) -> tuple:
    """
    Classify a user message during the collecting step.

    Returns (is_question: bool, answer: str | None):
      - (False, None)  → not a question; caller should send a simple ack
      - (True, str)    → question matched in FAQ; str is the answer in the user's language
      - (True, None)   → question not covered by FAQ; caller should redirect to consultant
    """
    from bot.services import get_openai_client
    from core.models import FaqEntry

    client = get_openai_client()
    if not client:
        return False, None

    faq_entries = list(FaqEntry.objects.filter(is_active=True).order_by('display_order', 'created_at'))
    lang_name = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}.get(lang, 'English')
    svc_name = service_def.name if service_def else 'our service'

    faq_block = ''
    if faq_entries:
        faq_lines = '\n'.join(
            f'[{i + 1}] Q: {e.question}\nA: {e.answer}'
            for i, e in enumerate(faq_entries)
        )
        faq_block = f'\n\nKnowledge base (FAQ):\n{faq_lines}'

    system = (
        f'The client is applying for "{svc_name}" and is submitting documents/information.{faq_block}\n\n'
        f'Classify the user message and reply with EXACTLY one of these formats:\n'
        f'  DATA               — the message is data/information being submitted (not a question)\n'
        f'  NO_ANSWER          — the message is a question but nothing in the FAQ covers it\n'
        f'  ANSWER: <text>     — the message is a question answered by the FAQ; <text> is the answer '
        f'in {lang_name} (1-3 sentences, natural, no markdown)\n\n'
        f'Rules: adapt the FAQ answer to the user\'s context; keep it concise; '
        f'end with a one-sentence reminder to continue submitting their documents.'
    )

    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': text},
            ],
            max_tokens=280,
            temperature=0.2,
            timeout=14,
        )
        raw = resp.choices[0].message.content.strip()
        upper = raw.upper()
        if upper.startswith('DATA'):
            return False, None
        if upper.startswith('NO_ANSWER'):
            return True, None
        if upper.startswith('ANSWER:'):
            return True, raw[7:].strip()
        # Unrecognised → treat as data to avoid false redirects
        return False, None
    except Exception as e:
        logger.warning('find_faq_answer error: %s', e)
        return False, None


def get_faq_redirect_text(lang: str) -> str:
    """
    Return the configurable "question forwarded to consultant" text in the
    user's language.  Falls back to built-in defaults if the admin hasn't
    configured the text yet.
    """
    from core.models import AiSettings
    from bot.services import get_openai_client

    _fallbacks = {
        'en': 'Your question has been forwarded to our consultant, who will get back to you shortly. '
              'Please continue sending the remaining documents in the meantime.',
        'ru': 'Ваш вопрос передан нашему консультанту — он ответит вам в ближайшее время. '
              'Пожалуйста, продолжайте отправлять оставшиеся документы.',
        'uz': "Savolingiz konsultantimizga yuborildi — u tez orada javob beradi. "
              "Shu orada qolgan hujjatlarni yuborishda davom eting.",
    }

    base_text = ''
    try:
        s = AiSettings.objects.filter(pk=1).first()
        base_text = (s.faq_unanswered_text or '').strip() if s else ''
    except Exception:
        pass

    if not base_text:
        return _fallbacks.get(lang, _fallbacks['en'])

    # Translate the admin-configured text to the user's language on the fly
    client = get_openai_client()
    if not client:
        return base_text

    lang_name = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}.get(lang, 'English')
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content':
                    f'Translate the following message to {lang_name}. '
                    f'Keep the exact tone and meaning. Return ONLY the translated text.'},
                {'role': 'user', 'content': base_text},
            ],
            max_tokens=180,
            temperature=0.1,
            timeout=8,
        )
        translated = resp.choices[0].message.content.strip()
        return translated or base_text
    except Exception:
        return base_text


def generate_final_message(lang: str) -> str:
    """Generate a unique paraphrased thank-you message in the user's language."""
    lang_name = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}.get(lang, 'English')
    from bot.services import get_openai_client
    client = get_openai_client()
    if client:
        try:
            resp = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {'role': 'system', 'content': (
                        f'Write a SHORT thank-you message in {lang_name} (2–3 sentences) '
                        'telling the client their request has been received and a consultant '
                        'will be in touch shortly. Be warm and professional. '
                        'Paraphrase differently each time — never use the same wording twice.'
                    )},
                    {'role': 'user', 'content': 'Generate the message now.'},
                ],
                max_tokens=120, temperature=0.9, timeout=15,
            )
            msg = resp.choices[0].message.content.strip()
            if msg:
                return msg
        except Exception as e:
            logger.warning('generate_final_message failed: %s', e)
    fallbacks = {
        'en': '✅ Thank you! Your request has been received and forwarded to a consultant. They will get back to you shortly.',
        'ru': '✅ Спасибо! Ваша заявка принята и передана консультанту. Они свяжутся с вами в ближайшее время.',
        'uz': "✅ Rahmat! Arizangiz qabul qilindi va konsultantga yuborildi. Ular tez orada siz bilan bog'lanishadi.",
    }
    return fallbacks.get(lang, fallbacks['en'])


# ── Message string builders ────────────────────────────────────────────────────

def build_lang_select() -> str:
    """Universal welcome shown before language is known — asks user to pick a language."""
    return (
        '👋 Welcome to Brightway Consulting!\n'
        '👋 Добро пожаловать в Brightway Consulting!\n'
        "👋 Brightway Consulting'a xush kelibsiz!\n\n"
        'Please choose your language / Выберите язык / Tilingizni tanlang:\n\n'
        "1. 🇺🇿 O'zbekcha\n"
        '2. 🇷🇺 Русский язык\n'
        '3. 🇬🇧 English'
    )


_LANG_KEYWORDS: dict[str, list[str]] = {
    'uz': ["o'zbek", "oʻzbek", 'uzbek', 'uz', 'узбек', '🇺🇿', 'ozbek', '1'],
    'ru': ['русский', 'russian', 'рус', 'rus', '🇷🇺', '2'],
    'en': ['english', 'eng', '🇬🇧', '3'],
}


def parse_lang_choice(text: str) -> str | None:
    """Return 'en', 'ru', or 'uz' if the text clearly identifies a language, else None."""
    stripped = text.strip()
    # Exact number shortcut (1/2/3 map to uz/ru/en)
    if stripped == '1':
        return 'uz'
    if stripped == '2':
        return 'ru'
    if stripped == '3':
        return 'en'
    lower = stripped.lower()
    for lang, keywords in _LANG_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return lang
    return None


def build_bot_intro(lang: str) -> str:
    """
    Dedicated bot self-introduction sent immediately after language selection,
    before showing service categories.
    """
    return {
        'en': (
            '🤖 I am an AI assistant for Brightway Consulting.\n\n'
            'Here is how this works:\n'
            '1️⃣ I will ask you a few questions and collect the necessary information.\n'
            '2️⃣ Once I have everything, I will pass your request to one of our human consultants.\n'
            '3️⃣ The consultant will review your case and get back to you directly — usually within a short time.\n\n'
            'I cannot give legal or professional advice myself, but our consultants can. '
            "Let's get started! 👇"
        ),
        'ru': (
            '🤖 Я — ИИ-помощник Brightway Consulting.\n\n'
            'Как это работает:\n'
            '1️⃣ Я задам вам несколько вопросов и соберу необходимую информацию.\n'
            '2️⃣ Как только у меня будет всё необходимое, я передам вашу заявку живому консультанту.\n'
            '3️⃣ Консультант изучит ваше обращение и свяжется с вами напрямую — обычно в короткие сроки.\n\n'
            'Сам я не даю юридических или профессиональных советов, но наши консультанты могут. '
            'Начнём! 👇'
        ),
        'uz': (
            "🤖 Men Brightway Consulting'ning AI yordamchisiman.\n\n"
            "Qanday ishlaydi:\n"
            "1️⃣ Men sizdan bir necha savol so'rayman va kerakli ma'lumotlarni yig'aman.\n"
            "2️⃣ Hamma narsa tayyor bo'lgach, arizangizni jonli konsultantga yuboraman.\n"
            "3️⃣ Konsultant sizning murojatingizni ko'rib chiqadi va to'g'ridan-to'g'ri siz bilan bog'lanadi — odatda qisqa muddatda.\n\n"
            "Men o'zim yuridik yoki kasbiy maslahat bera olmayman, lekin bizning konsultantlarimiz berishi mumkin. "
            "Boshlaylik! 👇"
        ),
    }.get(lang, (
        '🤖 I am an AI assistant. I will collect your information and pass it to a consultant, '
        'who will get back to you shortly. 👇'
    ))


def build_greeting(lang: str, subjects: list) -> str:
    """Category list — sent as a second message after build_bot_intro."""
    intro = {
        'en': 'What service do you need help with?\nPlease choose a category:',
        'ru': 'По какой теме вам нужна помощь?\nПожалуйста, выберите категорию:',
        'uz': "Qaysi xizmat bo'yicha yordam kerak?\nIltimos, bir toifani tanlang:",
    }.get(lang, 'Please choose a category:')
    lines = [f'{i}. {s.icon_emoji} {s.get_name(lang)}' for i, s in enumerate(subjects, 1)]
    return intro + ('\n\n' + '\n'.join(lines) if lines else '')


def build_greeting_universal(subjects: list) -> str:
    """
    Tri-lingual greeting shown when the user's language is not yet known
    (e.g. their very first message was a sticker or media).
    Lists service categories once using each language's name.
    """
    intro = (
        '👋 Hello! Welcome to Brightway Consulting.\n'
        '👋 Добро пожаловать в Brightway Consulting!\n'
        '👋 Brightway Consulting ga xush kelibsiz!\n\n'
        'I am an AI assistant — Я ИИ-помощник — Men AI yordamchisiman.\n'
        'I will collect your details and pass you to a consultant.\n\n'
        'Please choose a category / Выберите категорию / Toifani tanlang:'
    )
    # Show each subject in all 3 languages so every user can recognise their option
    lines = []
    for i, s in enumerate(subjects, 1):
        en = s.get_name('en')
        ru = s.get_name('ru')
        uz = s.get_name('uz')
        # Deduplicate identical names across languages
        parts = [en]
        if ru and ru != en:
            parts.append(ru)
        if uz and uz not in parts:
            parts.append(uz)
        lines.append(f'{i}. {s.icon_emoji} {" / ".join(parts)}')
    return intro + ('\n\n' + '\n'.join(lines) if lines else '')


def build_service_list(lang: str, subject, services: list) -> str:
    intro = {
        'en': f'{subject.get_name(lang)} — please choose a service:',
        'ru': f'{subject.get_name(lang)} — пожалуйста, выберите услугу:',
        'uz': f'{subject.get_name(lang)} — iltimos, xizmatni tanlang:',
    }.get(lang, f'{subject.get_name(lang)}:')
    lines = [intro]
    for i, svc in enumerate(services, 1):
        name = svc.name_ru if lang == 'ru' and svc.name_ru else (
            svc.name_uz if lang == 'uz' and svc.name_uz else svc.name
        )
        lines.append(f'{i}. {svc.icon_emoji} {name}')
    return '\n'.join(lines)


def build_collect_prompt(lang: str, service_def, items: list) -> str:
    svc_name = service_def.name_ru if lang == 'ru' and service_def.name_ru else (
        service_def.name_uz if lang == 'uz' and service_def.name_uz else service_def.name
    )
    intro = {
        'en': f'{svc_name}\n\nPlease send the following:',
        'ru': f'{svc_name}\n\nПожалуйста, отправьте следующее:',
        'uz': f'{svc_name}\n\nQuyidagilarni yuboring:',
    }.get(lang, f'{svc_name}\n\nPlease send:')
    numbered = '\n'.join(f'{i}. {item}' for i, item in enumerate(items, 1))
    hint = {
        'en': "\n\nWhen you have sent everything, reply Done.",
        'ru': '\n\nКогда всё отправите, напишите Готово.',
        'uz': "\n\nHammani yuborganingizdan so'ng, Bitti yoki tashlab boldim deb yozing.",
    }.get(lang, '')
    return f'{intro}\n\n{numbered}{hint}'


def build_not_understood(lang: str) -> str:
    return {
        'en': "Sorry, I didn't understand. Please choose from the list above.",
        'ru': 'Извините, не понял. Пожалуйста, выберите из списка выше.',
        'uz': "Kechirasiz, tushunmadim. Iltimos, yuqoridagi ro'yxatdan tanlang.",
    }.get(lang, 'Please choose from the list.')


def ai_contextual_reply(text: str, options: list, step: str, lang: str) -> str:
    """
    When the user's input doesn't directly match a subject/service, use AI to
    understand what they said and respond naturally, then guide them to choose
    from the available options. Falls back to build_not_understood on failure.
    """
    lang_name = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}.get(lang, 'English')
    if step == STEP_SUBJECT:
        context = 'The user needs to choose a service category. Available categories:\n' + '\n'.join(f'- {o}' for o in options)
    elif step == STEP_SERVICE:
        context = 'The user needs to choose a specific service. Available services:\n' + '\n'.join(f'- {o}' for o in options)
    else:
        context = 'Available options:\n' + '\n'.join(f'- {o}' for o in options)
    system = (
        f'You are a helpful assistant for Brightway Consulting, a consulting firm. '
        f'Always reply in {lang_name}. '
        f'{context}\n\n'
        'Understand what the user said, respond naturally and warmly, '
        'then politely ask them to choose one of the options above. '
        'Keep it concise (2-3 sentences max). No markdown, no asterisks.'
    )
    from bot.services import get_openai_client
    client = get_openai_client()
    if not client:
        return build_not_understood(lang)
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': text},
            ],
            max_tokens=150,
            temperature=0.4,
            timeout=10,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning('ai_contextual_reply error: %s', e)
        return build_not_understood(lang)


def build_no_services(lang: str) -> str:
    return {
        'en': 'Sorry, there are no services available for this category yet. Please contact us directly.',
        'ru': 'Извините, для этой категории пока нет доступных услуг. Свяжитесь с нами напрямую.',
        'uz': "Kechirasiz, bu toifa uchun hozircha xizmatlar yo'q. Bizga to'g'ridan-to'g'ri murojaat qiling.",
    }.get(lang, 'No services available.')


def build_ack(lang: str) -> str:
    return {
        'en': '✅ Received. Keep sending the remaining files or information. When you have sent everything, write Done.',
        'ru': '✅ Получено. Продолжайте отправлять оставшиеся файлы или информацию. Когда всё отправите, напишите Готово.',
        'uz': "✅ Qabul qilindi. Qolgan fayllar yoki ma'lumotlarni yuborishda davom eting. Hammasini yuborganingizdan so'ng, Bitti yoki tashlab boldim deb yozing.",
    }.get(lang, '✅ Received. Keep sending. Write Done when finished.')


def build_already_submitted(lang: str) -> str:
    return {
        'en': 'Your request has already been submitted. A consultant will be in touch.',
        'ru': 'Ваша заявка уже отправлена. Консультант свяжется с вами.',
        'uz': "Arizangiz allaqachon yuborildi. Konsultant siz bilan bog'lanadi.",
    }.get(lang, 'Your request has already been submitted.')


def build_consultant_confirm(lang: str) -> str:
    return {
        'en': 'Would you like me to connect you to a consultant now? They will get back to you as soon as possible. Reply Yes or No.',
        'ru': 'Хотите, чтобы я соединил вас с консультантом прямо сейчас? Они свяжутся с вами как можно скорее. Ответьте Да или Нет.',
        'uz': "Sizni hozir konsultant bilan bog'laymmi? Ular imkon qadar tezroq siz bilan bog'lanadi. Ha yoki Yo'q deb javob bering.",
    }.get(lang, 'Would you like me to connect you to a consultant? Reply Yes or No.')


def build_consultant_declined(lang: str) -> str:
    return {
        'en': 'No problem. Continue sending your information whenever you are ready.',
        'ru': 'Хорошо. Продолжайте отправлять информацию, когда будете готовы.',
        'uz': "Mayli. Tayyor bo'lganingizda ma'lumotlaringizni yuborishda davom eting.",
    }.get(lang, 'No problem. Continue whenever you are ready.')


# Specific multi-word phrases that clearly indicate a consultant request
_CONSULTANT_PHRASES = [
    'connect me', 'speak to', 'talk to', 'want a consultant', 'need a consultant',
    'contact consultant', 'real person', 'human agent', 'live agent', 'speak with someone',
    'соедини', 'поговорить с консультант', 'живой человек', 'консультант нужен',
    'konsultant bilan', 'ulang meni', 'konsultant kerak', "bog'lang", 'jonli odam',
]


def wants_consultant(text: str, lang: str = 'en') -> bool:
    """Return True if the user is clearly asking to be connected to a human consultant."""
    lower = text.strip().lower()
    for phrase in _CONSULTANT_PHRASES:
        if phrase in lower:
            return True
    # AI fallback for less obvious phrasing
    from bot.services import get_openai_client
    client = get_openai_client()
    if not client:
        return False
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': (
                    'Does this message clearly express a desire to speak with or be connected '
                    'to a human consultant, agent, or support person? '
                    'Reply YES or NO only. If unsure, reply NO.'
                )},
                {'role': 'user', 'content': text},
            ],
            max_tokens=3, temperature=0.0, timeout=8,
        )
        return resp.choices[0].message.content.strip().upper().startswith('YES')
    except Exception:
        return False


_YES_WORDS = {'yes', 'yeah', 'yep', 'ok', 'okay', 'sure', 'please', 'do it',
              'да', 'хорошо', 'ладно', 'конечно',
              'ha', "xo'sh", 'albatta', "bo'ldi", 'yaxshi', 'lol'}
_NO_WORDS = {'no', 'nope', 'cancel', 'back', 'stop',
             'нет', 'отмена', 'назад', 'не надо',
             "yo'q", 'bekor', 'ortga', 'kerak emas'}


def is_confirm_yes(text: str) -> bool:
    lower = text.strip().lower()
    return any(w in lower for w in _YES_WORDS)


def is_confirm_no(text: str) -> bool:
    lower = text.strip().lower()
    return any(w in lower for w in _NO_WORDS)
