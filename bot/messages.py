"""
Multi-language message templates for Brightway Consulting Telegram bot.

Supports English (en), Russian (ru), and Uzbek (uz).
"""

# First message sent to new users (no prior chat / no imported history). All three languages in one.
OPENING_MESSAGE = """Hello!
We're glad you contacted Brightway Consulting! How can we help you?

Здравствуйте!
Мы рады, что вы обратились в Brightway Consulting! Чем мы можем вам помочь?

Assalomu alaykum!
Brightway Consulting bilan bog'langanizdan mamnunmiz!
Sizga qanday yordam bera olamiz?"""

# Translation dictionary
T = {
    'en': {
        'welcome': """👋 Welcome to Brightway Consulting!

We provide expert assistance with:
🎓 Student Visa & University Applications
💰 PAYE Tax Refunds
📊 Self Assessment Tax Returns
🏢 Company Accounting

How can we help you today?""",

        'welcome_short': "Welcome to Brightway Consulting! How can I help you today?",

        'intro': """I'm your AI assistant. I can help you with:
• Student visa and university applications
• Tax refunds (PAYE)
• Self assessment tax returns
• Company accounting services

Just tell me what you need help with!""",

        'help': """📚 *Available Commands*

/start - Start a conversation
/help - Show this help message
/language - Change language
/mycase - Check your case status
/newcase - Start a new consultation

Or simply describe what you need help with and I'll guide you through the process.""",

        'ai_error': "Sorry, I encountered an error processing your request. Please try again or contact us directly on our website.",

        'case_none': "You don't have any active cases at the moment. Tell me what you need help with to get started!",

        'case_info': """📋 *Your Case Status*

Service: {service}
Status: {status}
Payment: {payment}
Documents: {doc_count}
Created: {created}""",

        'doc_received': "✅ Document received! I'll process it and get back to you shortly.",

        'voice_received': "🎤 Voice message received! I'll listen to it and respond shortly.",

        'photo_received': "📸 Photo received! I'll review it and continue with your case.",

        'language_changed': "Language changed to English.",

        'select_language': "Please select your preferred language:",

        'select_service': "Please select the service you need:",

        'new_case_started': "New consultation started! Please describe your situation and I'll help you.",

        'contact_received': "Thanks for sharing your contact information!",

        'processing': "Processing your request...",

        'consultant_will_reply': "A consultant will reply to you shortly. Thank you for your message.",

        'error_general': "Something went wrong. Please try again later.",

        'services': {
            'student': '🎓 Student Visa & University',
            'paye': '💰 PAYE Tax Refund',
            'schengen': '🇪🇺 Schengen Visa',
            'self': '📊 Self Assessment Tax',
            'company': '🏢 Company Accounting',
            'general': '📋 General Inquiry'
        }
    },

    'ru': {
        'welcome': """👋 Добро пожаловать в Brightway Consulting!

Мы предоставляем экспертную помощь:
🎓 Студенческие визы и поступление в университет
💰 Возврат налогов PAYE
📊 Декларации Self Assessment
🏢 Бухгалтерия компаний

Чем мы можем вам помочь?""",

        'welcome_short': "Добро пожаловать в Brightway Consulting! Чем я могу вам помочь?",

        'intro': """Я ваш AI-помощник. Я могу помочь вам с:
• Студенческими визами и поступлением
• Возвратом налогов (PAYE)
• Декларациями Self Assessment
• Бухгалтерскими услугами

Просто опишите, что вам нужно!""",

        'help': """📚 *Доступные команды*

/start - Начать разговор
/help - Показать справку
/language - Изменить язык
/mycase - Проверить статус заявки
/newcase - Начать новую консультацию

Или просто опишите, с чем вам нужна помощь.""",

        'ai_error': "Извините, произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте снова или свяжитесь с нами через наш сайт.",

        'case_none': "У вас пока нет активных заявок. Расскажите, чем я могу вам помочь!",

        'case_info': """📋 *Статус вашей заявки*

Услуга: {service}
Статус: {status}
Оплата: {payment}
Документы: {doc_count}
Создана: {created}""",

        'doc_received': "✅ Документ получен! Я обработаю его и скоро отвечу.",

        'voice_received': "🎤 Голосовое сообщение получено! Я прослушаю и отвечу.",

        'photo_received': "📸 Фото получено! Я просмотрю и продолжу работу над вашей заявкой.",

        'language_changed': "Язык изменён на русский.",

        'select_language': "Пожалуйста, выберите язык:",

        'select_service': "Пожалуйста, выберите нужную услугу:",

        'new_case_started': "Новая консультация начата! Опишите вашу ситуацию.",

        'contact_received': "Спасибо за контактные данные!",

        'processing': "Обрабатываю ваш запрос...",

        'consultant_will_reply': "Консультант ответит вам в ближайшее время. Спасибо за ваше сообщение.",

        'error_general': "Что-то пошло не так. Попробуйте позже.",

        'services': {
            'student': '🎓 Студенческая виза',
            'paye': '💰 Возврат PAYE',
            'schengen': '🇪🇺 Шенген виза',
            'self': '📊 Self Assessment',
            'company': '🏢 Бухгалтерия',
            'general': '📋 Общий вопрос'
        }
    },

    'uz': {
        'welcome': """👋 Brightway Consulting ga xush kelibsiz!

Biz ekspert yordam beramiz:
🎓 Talaba vizasi va universitetga hujjat topshirish
💰 PAYE soliq qaytarish
📊 Self Assessment soliq deklaratsiyalari
🏢 Kompaniya buxgalteriyasi

Bugun sizga qanday yordam bera olamiz?""",

        'welcome_short': "Brightway Consulting ga xush kelibsiz! Sizga qanday yordam bera olaman?",

        'intro': """Men sizning AI yordamchingizman. Men sizga yordam bera olaman:
• Talaba vizasi va universitetga hujjat topshirish
• Soliq qaytarish (PAYE)
• Self Assessment soliq deklaratsiyalari
• Kompaniya buxgalteriya xizmatlari

Sizga nima kerakligini aytib bering!""",

        'help': """📚 *Mavjud buyruqlar*

/start - Suhbatni boshlash
/help - Yordam ko'rsatish
/language - Tilni o'zgartirish
/mycase - Ariza holatini tekshirish
/newcase - Yangi maslahat boshlash

Yoki sizga nima kerakligini tasvirlab bering.""",

        'ai_error': "Kechirasiz, so'rovingizni qayta ishlashda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",

        'case_none': "Hozirda faol arizalaringiz yo'q. Nima yordam kerakligini ayting!",

        'case_info': """📋 *Ariza holati*

Xizmat: {service}
Holat: {status}
To'lov: {payment}
Hujjatlar: {doc_count}
Yaratilgan: {created}""",

        'doc_received': "✅ Hujjat qabul qilindi! Men uni ko'rib chiqaman va tez orada javob beraman.",

        'voice_received': "🎤 Ovozli xabar qabul qilindi! Men tinglayman va javob beraman.",

        'photo_received': "📸 Rasm qabul qilindi! Men ko'rib chiqaman va arizangiz ustida davom etaman.",

        'language_changed': "Til o'zbekchaga o'zgartirildi.",

        'select_language': "Iltimos, tilni tanlang:",

        'select_service': "Iltimos, kerakli xizmatni tanlang:",

        'new_case_started': "Yangi maslahat boshlandi! Vaziyatingizni tasvirlab bering.",

        'contact_received': "Kontakt ma'lumotlari uchun rahmat!",

        'processing': "So'rovingiz qayta ishlanmoqda...",

        'consultant_will_reply': "Konsultant tez orada sizga javob beradi. Xabaringiz uchun rahmat.",

        'error_general': "Nimadir noto'g'ri ketdi. Keyinroq urinib ko'ring.",

        'services': {
            'student': '🎓 Talaba vizasi',
            'paye': '💰 PAYE qaytarish',
            'schengen': '🇪🇺 Shengen viza',
            'self': '📊 Self Assessment',
            'company': '🏢 Buxgalteriya',
            'general': '📋 Umumiy savol'
        }
    }
}


def t(lang: str, key: str, **kwargs) -> str:
    """
    Get translated message.
    
    Args:
        lang: Language code (en, ru, uz)
        key: Translation key
        **kwargs: Format arguments
        
    Returns:
        Translated and formatted string
    """
    # Normalize language code
    lang = lang.lower()[:2] if lang else 'en'
    if lang not in T:
        lang = 'en'
    
    # Get message
    messages = T[lang]
    
    # Handle nested keys (e.g., 'services.student')
    if '.' in key:
        parts = key.split('.')
        value = messages
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                value = T['en'].get(key, key)
                break
    else:
        value = messages.get(key, T['en'].get(key, key))
    
    # Format with kwargs if provided
    if kwargs and isinstance(value, str):
        try:
            value = value.format(**kwargs)
        except KeyError:
            pass
    
    return value


def get_language_name(lang: str) -> str:
    """Get the display name for a language code."""
    names = {
        'en': 'English',
        'ru': 'Русский',
        'uz': "O'zbek"
    }
    return names.get(lang, 'English')


def get_language_flag(lang: str) -> str:
    """Get the flag emoji for a language code."""
    flags = {
        'en': '🇬🇧',
        'ru': '🇷🇺',
        'uz': '🇺🇿'
    }
    return flags.get(lang, '🇬🇧')


def get_all_languages() -> list:
    """Get list of all supported languages."""
    return [
        {'code': 'en', 'name': 'English', 'flag': '🇬🇧'},
        {'code': 'ru', 'name': 'Русский', 'flag': '🇷🇺'},
        {'code': 'uz', 'name': "O'zbek", 'flag': '🇺🇿'},
    ]


# Language keyboard callback data
LANG_CALLBACKS = {
    'lang_en': 'en',
    'lang_ru': 'ru',
    'lang_uz': 'uz'
}

# Service display names for each language
SERVICE_NAMES = {
    'en': {
        'student': 'Student Visa & University',
        'paye': 'PAYE Tax Refund',
        'schengen': 'Schengen Visa',
        'self': 'Self Assessment Tax',
        'company': 'Company Accounting',
        'general': 'General Inquiry'
    },
    'ru': {
        'student': 'Студенческая виза',
        'paye': 'Возврат PAYE',
        'schengen': 'Шенген виза',
        'self': 'Self Assessment',
        'company': 'Бухгалтерия',
        'general': 'Общий вопрос'
    },
    'uz': {
        'student': 'Talaba vizasi',
        'paye': 'PAYE qaytarish',
        'schengen': 'Shengen viza',
        'self': 'Self Assessment',
        'company': 'Buxgalteriya',
        'general': 'Umumiy savol'
    }
}


def get_service_name(service: str, lang: str = 'en') -> str:
    """Get localized service name."""
    lang = lang.lower()[:2] if lang else 'en'
    if lang not in SERVICE_NAMES:
        lang = 'en'
    return SERVICE_NAMES[lang].get(service, service)
