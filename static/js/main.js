/**
 * Brightway Consulting - Main JavaScript
 * Handles language switching, animations, and interactive features
 */

// ==================== Translations ====================
const translations = {
    en: {
        // Navigation
        nav_home: "Home",
        nav_services: "Services",
        nav_contact: "Contact",
        
        // Hero Section
        hero_badge: "Trusted by 500+ clients in the UK",
        hero_title_1: "Expert Consulting for",
        hero_title_2: "Tax & Immigration",
        hero_subtitle: "Professional assistance with student visas, tax refunds, self-assessment returns, and company accounting. We make complex processes simple.",
        hero_cta: "Start Free Consultation",
        hero_cta_secondary: "View Services",
        scroll_down: "Scroll to explore",
        
        // Stats
        stat_clients: "Happy Clients",
        stat_success: "Success Rate",
        stat_support: "24/7 Support",
        stat_24_7: "24/7 Support",
        stat_languages: "Languages Supported",
        stat_compliant: "UK Compliant",
        stat_secure: "Secure & Private",
        
        // Services Section
        services_label: "Our Services",
        services_title: "Comprehensive Solutions for Your Needs",
        services_desc: "From visa applications to tax returns, we provide expert guidance every step of the way.",
        learn_more: "Learn more",
        services_hero_title: "Comprehensive Consulting Solutions",
        services_hero_desc: "Expert guidance for all your UK tax and immigration needs. Choose the service that fits your situation.",
        get_started: "Get Started",
        
        // Process Section
        process_label: "How It Works",
        process_title: "Simple 4-Step Process",
        process_desc: "Get started in minutes with our consultation system.",
        process_1_title: "Start a Conversation",
        process_1_desc: "Open our Telegram channel and tell us what you need help with. We support English, Russian, and Uzbek.",
        process_2_title: "Share Your Details",
        process_2_desc: "Answer a few questions about your situation. We'll guide you through exactly what information we need.",
        process_3_title: "Upload Documents",
        process_3_desc: "Send photos of your documents directly in the chat. We securely store and process everything.",
        process_4_title: "We Handle the Rest",
        process_4_desc: "Our expert consultants review your case and take care of all the paperwork and submissions.",
        
        // Why Choose Us
        why_label: "Why Choose Us",
        why_title: "Your Trusted Partner in the UK",
        why_desc: "We combine expert knowledge with efficient processes to deliver exceptional results.",
        why_1_title: "Expert Consultants",
        why_1_desc: "Qualified professionals with years of UK tax and immigration experience.",
        why_2_title: "Quick Response",
        why_2_desc: "Get updates and reach us anytime through our Telegram channel.",
        why_3_title: "Transparent Pricing",
        why_3_desc: "No hidden fees. Know exactly what you'll pay before you start.",
        why_4_title: "Multilingual Support",
        why_4_desc: "Communicate in English, Russian, or Uzbek — whatever you prefer.",
        
        // CTA
        cta_title: "Ready to Get Started?",
        cta_desc: "Start your free consultation today. Our channel is available 24/7 to help you.",
        cta_button: "Start Free Consultation",
        cta_trust: "Secure • Confidential • Professional",
        cta_services_title: "Not Sure Which Service You Need?",
        cta_services_desc: "Reach us via our Telegram channel and we'll help you find the right solution for your situation.",
        cta_contact_title: "Ready to Get Started?",
        cta_contact_desc: "The fastest way to get help is through our Telegram channel. It's available 24/7!",
        
        // Footer
        footer_desc: "Professional consulting services for tax, immigration, and business needs in the UK.",
        footer_services: "Services",
        footer_company: "Company",
        footer_contact: "Contact",
        footer_admin: "Admin Panel",
        footer_rights: "All rights reserved.",
        service_student: "Student Visa",
        service_paye: "PAYE Tax Refund",
        service_self: "Self Assessment",
        service_company: "Company Accounting",
        
        // Contact Page
        contact_label: "Get In Touch",
        contact_hero_title: "We're Here to Help",
        contact_hero_desc: "Have questions? Reach out through any of these channels and we'll get back to you promptly.",
        contact_telegram: "Telegram Channel",
        contact_telegram_desc: "Join our channel for updates and to get in touch",
        contact_email: "Email",
        contact_email_desc: "Send us a detailed message",
        contact_phone: "Phone",
        contact_phone_desc: "Call us during business hours",
        contact_languages: "Languages",
        contact_languages_desc: "We speak your language",
        contact_form_title: "Send Us a Message",
        contact_form_desc: "Fill out the form and our team will get back to you within 24 hours.",
        contact_office: "Our Office",
        contact_hours: "Business Hours",
        form_name: "Full Name",
        form_email: "Email Address",
        form_phone: "Phone Number",
        form_message: "Your Message",
        form_submit: "Send Message",
        form_success_title: "Message Sent!",
        form_success_desc: "Thank you for reaching out. We'll get back to you shortly.",
        
        // FAQ
        faq_label: "FAQ",
        faq_title: "Frequently Asked Questions",
        faq_1_q: "How quickly will I get a response?",
        faq_1_a: "We respond promptly. For complex inquiries, our consultants typically respond within 24 hours during business days.",
        faq_2_q: "What languages do you support?",
        faq_2_a: "We provide full support in English, Russian, and Uzbek.",
        faq_3_q: "Is my information secure?",
        faq_3_a: "Absolutely. We use encrypted channels and secure storage. Your documents and personal information are handled with the utmost confidentiality.",
        faq_4_q: "What are your fees?",
        faq_4_a: "Our fees vary depending on the service. Contact us via our channel to get a personalized quote for your specific needs."
    },
    
    ru: {
        // Navigation
        nav_home: "Главная",
        nav_services: "Услуги",
        nav_contact: "Контакты",
        
        // Hero Section
        hero_badge: "Нам доверяют более 500 клиентов в Великобритании",
        hero_title_1: "Экспертные консультации",
        hero_title_2: "по налогам и иммиграции",
        hero_subtitle: "Профессиональная помощь со студенческими визами, возвратом налогов, налоговыми декларациями и бухгалтерией компаний. Мы упрощаем сложные процессы.",
        hero_cta: "Бесплатная консультация",
        hero_cta_secondary: "Смотреть услуги",
        scroll_down: "Прокрутите вниз",
        
        // Stats
        stat_clients: "Довольных клиентов",
        stat_success: "Успешных дел",
        stat_support: "Поддержка 24/7",
        stat_24_7: "Поддержка 24/7",
        stat_languages: "Языка поддержки",
        stat_compliant: "Соответствие UK",
        stat_secure: "Безопасно и приватно",
        
        // Services Section
        services_label: "Наши услуги",
        services_title: "Комплексные решения для ваших потребностей",
        services_desc: "От визовых заявлений до налоговых деклараций — мы оказываем экспертную поддержку на каждом этапе.",
        learn_more: "Подробнее",
        services_hero_title: "Комплексные консультационные решения",
        services_hero_desc: "Экспертное руководство по всем вопросам налогообложения и иммиграции в Великобритании.",
        get_started: "Начать",
        
        // Process Section
        process_label: "Как это работает",
        process_title: "Простой процесс из 4 шагов",
        process_desc: "Начните за несколько минут с нашей системой консультаций.",
        process_1_title: "Начните разговор",
        process_1_desc: "Откройте наш Telegram-канал и расскажите, с чем вам нужна помощь. Мы работаем на английском, русском и узбекском.",
        process_2_title: "Поделитесь информацией",
        process_2_desc: "Ответьте на несколько вопросов о вашей ситуации. Мы проведём вас через все необходимые детали.",
        process_3_title: "Загрузите документы",
        process_3_desc: "Отправьте фото документов прямо в чат. Мы надёжно храним и обрабатываем всё.",
        process_4_title: "Мы займёмся остальным",
        process_4_desc: "Наши эксперты рассмотрят ваше дело и займутся всеми документами и подачами.",
        
        // Why Choose Us
        why_label: "Почему мы",
        why_title: "Ваш надёжный партнёр в Великобритании",
        why_desc: "Мы сочетаем экспертные знания с эффективными процессами для достижения исключительных результатов.",
        why_1_title: "Эксперты-консультанты",
        why_1_desc: "Квалифицированные специалисты с многолетним опытом в UK налогах и иммиграции.",
        why_2_title: "Быстрый ответ",
        why_2_desc: "Получайте обновления и связывайтесь с нами в любое время через наш Telegram-канал.",
        why_3_title: "Прозрачное ценообразование",
        why_3_desc: "Никаких скрытых платежей. Знайте точную стоимость заранее.",
        why_4_title: "Многоязычная поддержка",
        why_4_desc: "Общайтесь на английском, русском или узбекском — как вам удобнее.",
        
        // CTA
        cta_title: "Готовы начать?",
        cta_desc: "Начните бесплатную консультацию сегодня. Наш канал доступен 24/7.",
        cta_button: "Бесплатная консультация",
        cta_trust: "Безопасно • Конфиденциально • Профессионально",
        cta_services_title: "Не уверены, какая услуга вам нужна?",
        cta_services_desc: "Свяжитесь с нами через наш Telegram-канал, и мы поможем найти правильное решение.",
        cta_contact_title: "Готовы начать?",
        cta_contact_desc: "Самый быстрый способ получить помощь — через наш Telegram-канал. Он доступен 24/7!",
        
        // Footer
        footer_desc: "Профессиональные консультационные услуги по налогам, иммиграции и бизнесу в Великобритании.",
        footer_services: "Услуги",
        footer_company: "Компания",
        footer_contact: "Контакты",
        footer_admin: "Панель админа",
        footer_rights: "Все права защищены.",
        service_student: "Студенческая виза",
        service_paye: "Возврат налога PAYE",
        service_self: "Self Assessment",
        service_company: "Бухгалтерия компании",
        
        // Contact Page
        contact_label: "Свяжитесь с нами",
        contact_hero_title: "Мы здесь, чтобы помочь",
        contact_hero_desc: "Есть вопросы? Свяжитесь с нами любым удобным способом, и мы оперативно ответим.",
        contact_telegram: "Telegram-канал",
        contact_telegram_desc: "Подпишитесь на канал для новостей и связи с нами",
        contact_email: "Email",
        contact_email_desc: "Отправьте нам подробное сообщение",
        contact_phone: "Телефон",
        contact_phone_desc: "Звоните в рабочее время",
        contact_languages: "Языки",
        contact_languages_desc: "Мы говорим на вашем языке",
        contact_form_title: "Отправьте нам сообщение",
        contact_form_desc: "Заполните форму, и наша команда ответит в течение 24 часов.",
        contact_office: "Наш офис",
        contact_hours: "Часы работы",
        form_name: "Полное имя",
        form_email: "Email адрес",
        form_phone: "Номер телефона",
        form_message: "Ваше сообщение",
        form_submit: "Отправить сообщение",
        form_success_title: "Сообщение отправлено!",
        form_success_desc: "Спасибо за обращение. Мы скоро свяжемся с вами.",
        
        // FAQ
        faq_label: "Вопросы",
        faq_title: "Часто задаваемые вопросы",
        faq_1_q: "Как быстро я получу ответ?",
        faq_1_a: "Мы отвечаем оперативно. На сложные вопросы наши консультанты обычно отвечают в течение 24 часов в рабочие дни.",
        faq_2_q: "Какие языки вы поддерживаете?",
        faq_2_a: "Мы обеспечиваем полную поддержку на английском, русском и узбекском языках.",
        faq_3_q: "Моя информация в безопасности?",
        faq_3_a: "Безусловно. Мы используем зашифрованные каналы и безопасное хранилище. Ваши документы и личная информация обрабатываются с максимальной конфиденциальностью.",
        faq_4_q: "Сколько стоят ваши услуги?",
        faq_4_a: "Наши цены зависят от услуги. Свяжитесь с нами через канал, чтобы получить персонализированную цену."
    },
    
    uz: {
        // Navigation
        nav_home: "Bosh sahifa",
        nav_services: "Xizmatlar",
        nav_contact: "Aloqa",
        
        // Hero Section
        hero_badge: "Buyuk Britaniyada 500+ mijoz ishonchi",
        hero_title_1: "Ekspert konsalting",
        hero_title_2: "soliq va immigratsiya bo'yicha",
        hero_subtitle: "Talaba vizalari, soliq qaytarishlari, soliq deklaratsiyalari va kompaniya buxgalteriyasi bo'yicha professional yordam. Biz murakkab jarayonlarni soddalashtramiz.",
        hero_cta: "Bepul konsultatsiya",
        hero_cta_secondary: "Xizmatlarni ko'rish",
        scroll_down: "Pastga aylantiring",
        
        // Stats
        stat_clients: "Mamnun mijozlar",
        stat_success: "Muvaffaqiyat darajasi",
        stat_support: "24/7 qo'llab-quvvatlash",
        stat_24_7: "24/7 qo'llab-quvvatlash",
        stat_languages: "Til qo'llab-quvvatlanadi",
        stat_compliant: "UK standartlariga mos",
        stat_secure: "Xavfsiz va maxfiy",
        
        // Services Section
        services_label: "Bizning xizmatlar",
        services_title: "Ehtiyojlaringiz uchun keng qamrovli yechimlar",
        services_desc: "Viza arizalaridan soliq deklaratsiyalarigacha — biz har bir bosqichda ekspert yordamini taqdim etamiz.",
        learn_more: "Batafsil",
        services_hero_title: "Keng qamrovli konsalting yechimlari",
        services_hero_desc: "Buyuk Britaniyadagi barcha soliq va immigratsiya ehtiyojlaringiz uchun ekspert yo'riqnomasi.",
        get_started: "Boshlash",
        
        // Process Section
        process_label: "Qanday ishlaydi",
        process_title: "Oddiy 4 bosqichli jarayon",
        process_desc: "Konsultatsiya tizimimiz bilan bir necha daqiqada boshlang.",
        process_1_title: "Suhbatni boshlang",
        process_1_desc: "Telegram kanalimizni oching va sizga qanday yordam kerakligini ayting. Biz ingliz, rus va o'zbek tillarida ishlaymiz.",
        process_2_title: "Ma'lumotlaringizni ulashing",
        process_2_desc: "Vaziyatingiz haqida bir nechta savollarga javob bering. Biz sizga kerakli ma'lumotlar orqali yo'l ko'rsatamiz.",
        process_3_title: "Hujjatlarni yuklang",
        process_3_desc: "Hujjatlaringiz rasmlarini to'g'ridan-to'g'ri chatga yuboring. Biz hamma narsani xavfsiz saqlaymiz va qayta ishlaymiz.",
        process_4_title: "Qolganini biz bajaramiz",
        process_4_desc: "Bizning ekspertlar ishingizni ko'rib chiqadi va barcha hujjatlar va topshiriqlarni bajaradi.",
        
        // Why Choose Us
        why_label: "Nega biz",
        why_title: "Buyuk Britaniyadagi ishonchli hamkoringiz",
        why_desc: "Biz ajoyib natijalarga erishish uchun ekspert bilimlarini samarali jarayonlar bilan birlashtiramiz.",
        why_1_title: "Ekspert maslahatchilar",
        why_1_desc: "UK soliq va immigratsiya bo'yicha ko'p yillik tajribaga ega malakali mutaxassislar.",
        why_2_title: "Tezkor javob",
        why_2_desc: "Kanalimiz orqali yangilanishlar oling va istalgan vaqtda biz bilan bog'laning.",
        why_3_title: "Shaffof narxlar",
        why_3_desc: "Yashirin to'lovlar yo'q. Boshlashdan oldin to'liq narxni bilib oling.",
        why_4_title: "Ko'p tilli qo'llab-quvvatlash",
        why_4_desc: "Ingliz, rus yoki o'zbek tilida muloqot qiling — sizga qulay.",
        
        // CTA
        cta_title: "Boshlashga tayyormisiz?",
        cta_desc: "Bugun bepul konsultatsiyani boshlang. Kanalimiz 24/7 mavjud.",
        cta_button: "Bepul konsultatsiya",
        cta_trust: "Xavfsiz • Maxfiy • Professional",
        cta_services_title: "Qaysi xizmat kerakligiga ishonchingiz komilmi?",
        cta_services_desc: "Telegram kanalimiz orqali biz bilan bog'laning va biz vaziyatingiz uchun to'g'ri yechimni topishga yordam beramiz.",
        cta_contact_title: "Boshlashga tayyormisiz?",
        cta_contact_desc: "Yordam olishning eng tezkor yo'li Telegram kanalimiz orqali. U 24/7 mavjud!",
        
        // Footer
        footer_desc: "Buyuk Britaniyada soliq, immigratsiya va biznes ehtiyojlari uchun professional konsalting xizmatlari.",
        footer_services: "Xizmatlar",
        footer_company: "Kompaniya",
        footer_contact: "Aloqa",
        footer_admin: "Admin panel",
        footer_rights: "Barcha huquqlar himoyalangan.",
        service_student: "Talaba vizasi",
        service_paye: "PAYE soliq qaytarishi",
        service_self: "Self Assessment",
        service_company: "Kompaniya buxgalteriyasi",
        
        // Contact Page
        contact_label: "Biz bilan bog'laning",
        contact_hero_title: "Biz yordam berishga tayyormiz",
        contact_hero_desc: "Savollaringiz bormi? Quyidagi yo'llardan biri orqali bog'laning va biz tezda javob beramiz.",
        contact_telegram: "Telegram kanal",
        contact_telegram_desc: "Yangilanishlar va aloqa uchun kanalimizga obuna bo'ling",
        contact_email: "Email",
        contact_email_desc: "Bizga batafsil xabar yuboring",
        contact_phone: "Telefon",
        contact_phone_desc: "Ish vaqtida qo'ng'iroq qiling",
        contact_languages: "Tillar",
        contact_languages_desc: "Biz sizning tilingizda gaplashamiz",
        contact_form_title: "Bizga xabar yuboring",
        contact_form_desc: "Formani to'ldiring va jamoamiz 24 soat ichida javob beradi.",
        contact_office: "Bizning ofis",
        contact_hours: "Ish vaqti",
        form_name: "To'liq ism",
        form_email: "Email manzil",
        form_phone: "Telefon raqam",
        form_message: "Xabaringiz",
        form_submit: "Xabar yuborish",
        form_success_title: "Xabar yuborildi!",
        form_success_desc: "Murojaat uchun rahmat. Biz tez orada siz bilan bog'lanamiz.",
        
        // FAQ
        faq_label: "Savollar",
        faq_title: "Ko'p so'raladigan savollar",
        faq_1_q: "Qanchalik tez javob olaman?",
        faq_1_a: "Biz tez javob beramiz. Murakkab so'rovlar uchun konsultantlarimiz odatda ish kunlarida 24 soat ichida javob beradi.",
        faq_2_q: "Qaysi tillarni qo'llab-quvvatlaysiz?",
        faq_2_a: "Biz ingliz, rus va o'zbek tillarida to'liq qo'llab-quvvatlashni ta'minlaymiz.",
        faq_3_q: "Ma'lumotlarim xavfsizmi?",
        faq_3_a: "Albatta. Biz shifrlangan kanallar va xavfsiz saqlashdan foydalanamiz. Hujjatlaringiz va shaxsiy ma'lumotlaringiz maksimal maxfiylik bilan qayta ishlanadi.",
        faq_4_q: "Xizmatlaringiz narxi qancha?",
        faq_4_a: "Narxlarimiz xizmatga qarab o'zgaradi. Shaxsiy narx olish uchun kanalimiz orqali biz bilan bog'laning."
    }
};

// ==================== Language Management ====================
const langFlags = {
    en: '🇬🇧',
    ru: '🇷🇺',
    uz: '🇺🇿'
};

const langNames = {
    en: 'EN',
    ru: 'RU',
    uz: 'UZ'
};

function getCurrentLanguage() {
    // Check localStorage first, then browser language, default to 'en'
    let lang = localStorage.getItem('brightway_lang');
    if (!lang) {
        const browserLang = navigator.language.slice(0, 2).toLowerCase();
        lang = ['en', 'ru', 'uz'].includes(browserLang) ? browserLang : 'en';
    }
    return lang;
}

function setLanguage(lang) {
    if (!translations[lang]) return;
    
    localStorage.setItem('brightway_lang', lang);
    
    // Update all elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (translations[lang][key]) {
            el.textContent = translations[lang][key];
        }
    });
    
    // Update language switcher display
    const currentFlag = document.getElementById('currentFlag');
    const currentLang = document.getElementById('currentLang');
    if (currentFlag) currentFlag.textContent = langFlags[lang];
    if (currentLang) currentLang.textContent = langNames[lang];
    
    // Update HTML lang attribute
    document.documentElement.lang = lang;
}

// ==================== Navigation ====================
function initNavigation() {
    const nav = document.getElementById('nav');
    const mobileToggle = document.getElementById('mobileToggle');
    const mobileMenu = document.getElementById('mobileMenu');
    
    // Scroll effect for navigation
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            nav.classList.add('scrolled');
        } else {
            nav.classList.remove('scrolled');
        }
        
        // Update scroll progress bar
        const scrollProgress = document.querySelector('.scroll-progress');
        if (scrollProgress) {
            const scrollPercent = (window.scrollY / (document.documentElement.scrollHeight - window.innerHeight)) * 100;
            scrollProgress.style.width = scrollPercent + '%';
        }
    });
    
    // Mobile menu toggle
    if (mobileToggle && mobileMenu) {
        mobileToggle.addEventListener('click', () => {
            mobileMenu.classList.toggle('open');
        });
        
        // Close mobile menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!mobileMenu.contains(e.target) && !mobileToggle.contains(e.target)) {
                mobileMenu.classList.remove('open');
            }
        });
    }
}

// ==================== Language Switcher ====================
function initLanguageSwitcher() {
    const langToggle = document.getElementById('langToggle');
    const langDropdown = document.getElementById('langDropdown');
    const langSwitcher = document.querySelector('.lang-switcher');
    const langOptions = document.querySelectorAll('.lang-option');
    const mobileLangBtns = document.querySelectorAll('.mobile-lang-btn');
    
    if (langToggle && langSwitcher) {
        // Toggle dropdown
        langToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            langSwitcher.classList.toggle('open');
        });
        
        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            langSwitcher.classList.remove('open');
        });
    }
    
    // Language option clicks
    langOptions.forEach(option => {
        option.addEventListener('click', () => {
            const lang = option.getAttribute('data-lang');
            setLanguage(lang);
            langSwitcher?.classList.remove('open');
        });
    });
    
    // Mobile language buttons
    mobileLangBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const lang = btn.getAttribute('data-lang');
            setLanguage(lang);
        });
    });
}

// ==================== Animations ====================
function initAnimations() {
    // Simple AOS-like animation on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // Add delay based on data-aos-delay attribute
                const delay = entry.target.getAttribute('data-aos-delay') || 0;
                setTimeout(() => {
                    entry.target.classList.add('aos-animate');
                }, delay);
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    document.querySelectorAll('[data-aos]').forEach(el => {
        observer.observe(el);
    });
}

// ==================== Smooth Scroll ====================
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

// ==================== Form Handling ====================
function initForms() {
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        // Auto-resize textareas
        const textareas = form.querySelectorAll('textarea');
        textareas.forEach(textarea => {
            textarea.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = this.scrollHeight + 'px';
            });
        });
    });
}

// ==================== Initialize ====================
document.addEventListener('DOMContentLoaded', () => {
    // Set initial language
    const currentLang = getCurrentLanguage();
    setLanguage(currentLang);
    
    // Initialize features
    initNavigation();
    initLanguageSwitcher();
    initAnimations();
    initSmoothScroll();
    initForms();
    
    console.log('Brightway Consulting initialized');
});
