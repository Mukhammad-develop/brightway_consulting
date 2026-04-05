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
STEP_SUBJECT = 'awaiting_subject'
STEP_SERVICE = 'awaiting_service'
STEP_COLLECTING = 'collecting'
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
        defaults={'first_name': first_name, 'username': username, 'language_code': 'en'},
    )


def db_get_or_open_case(user, service_slug: str = 'general'):
    """Return the user's active case or create a new one."""
    from core.models import Case
    case = Case.objects.filter(user=user, status='active').first()
    if not case:
        case = Case.objects.create(user=user, service=service_slug, status='active')
        logger.info('Created case #%s for user %s', case.pk, user.telegram_id)
    return case


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
    'uz': {'bitti', 'tayyor', 'tamom', 'bajarildi', 'yubordim', 'hammasi'},
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


def ai_answer_question(text: str, service_def, lang: str) -> str | None:
    """
    During the collecting step, determine whether the user's message is a
    clarifying question or actual data being submitted.

    Returns a brief answer string (in the user's language) if it's a question,
    or None if it's data/information (caller should just acknowledge).
    """
    from bot.services import get_openai_client
    client = get_openai_client()
    if not client:
        return None
    lang_name = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}.get(lang, 'English')
    svc_name = service_def.name if service_def else 'our service'
    system = (
        f'You are a helpful assistant for Brightway Consulting. '
        f'The client is applying for "{svc_name}" and is in the process of submitting their documents and information.\n\n'
        f'Decide: is this message a QUESTION asking for clarification, or is it information/data being provided?\n\n'
        f'If it IS a question: answer it briefly and helpfully in {lang_name} (1-3 sentences). '
        f'Then in the same language, remind them to continue sending the required information.\n\n'
        f'If it is NOT a question (i.e. actual data, a name, a number, a file description, etc.): '
        f'reply with exactly one word: DATA\n\n'
        f'No markdown, no asterisks.'
    )
    try:
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': text},
            ],
            max_tokens=200,
            temperature=0.3,
            timeout=12,
        )
        answer = resp.choices[0].message.content.strip()
        if answer.upper().startswith('DATA'):
            return None
        return answer
    except Exception as e:
        logger.warning('ai_answer_question error: %s', e)
        return None


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

def build_greeting(lang: str, subjects: list) -> str:
    intro = {
        'en': '👋 Hello! Welcome to Brightway Consulting.\n\nWhat service do you need help with?\nPlease choose a category:',
        'ru': '👋 Здравствуйте! Добро пожаловать в Brightway Consulting.\n\nПо какой теме вам нужна помощь?\nПожалуйста, выберите категорию:',
        'uz': "👋 Salom! Brightway Consulting ga xush kelibsiz.\n\nQaysi xizmat bo'yicha yordam kerak?\nIltimos, bir toifani tanlang:",
    }.get(lang, '')
    lines = [f'{i}. {s.icon_emoji} {s.get_name(lang)}' for i, s in enumerate(subjects, 1)]
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
        'uz': "\n\nHammani yuborganingizdan so'ng, Bitti deb yozing.",
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
        'uz': "✅ Qabul qilindi. Qolgan fayllar yoki ma'lumotlarni yuborishda davom eting. Hammasini yuborganingizdan so'ng, Bitti deb yozing.",
    }.get(lang, '✅ Received. Keep sending. Write Done when finished.')


def build_already_submitted(lang: str) -> str:
    return {
        'en': 'Your request has already been submitted. A consultant will be in touch.',
        'ru': 'Ваша заявка уже отправлена. Консультант свяжется с вами.',
        'uz': "Arizangiz allaqachon yuborildi. Konsultant siz bilan bog'lanadi.",
    }.get(lang, 'Your request has already been submitted.')
