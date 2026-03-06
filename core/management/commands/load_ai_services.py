"""
Load AI config and service data from docs/AI_CONFIG_AND_SERVICES.md into ServiceDefinition.
Creates or updates the 5 services (student, paye, schengen, self, company) with full AI prompts and lists.
"""
import json
from django.core.management.base import BaseCommand
from core.models import ServiceDefinition


# Data aligned with docs/AI_CONFIG_AND_SERVICES.md and bot/services.py _build_hardcoded_prompt()
SERVICES = [
    {
        'slug': 'student',
        'name': 'Student Visa & University',
        'name_ru': 'Студенческая виза',
        'name_uz': 'Talaba vizasi',
        'description': 'Complete assistance with student visa applications, university admissions, and educational guidance.',
        'badge_color': 'student',
        'icon_emoji': '🎓',
        'display_order': 1,
        'ai_strict_flow': False,
        'ai_system_prompt': """You are an AI assistant helping with Student Visa and University applications for the UK.

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

Guide them step by step, asking for one piece of information at a time.""",
        'ai_collect_items': [
            'Full name (as in passport)',
            'Passport number',
            'Date of birth',
            'University name and course',
            'CAS number (if available)',
            'Previous UK visa history',
        ],
        'ai_documents_list': [
            'Passport scan (photo page)',
            'University acceptance letter',
            'Financial documents (bank statements)',
            'English test results (IELTS/TOEFL)',
        ],
    },
    {
        'slug': 'paye',
        'name': 'PAYE Tax Refund',
        'name_ru': 'Возврат налога PAYE',
        'name_uz': 'PAYE soliq qaytarish',
        'description': "Claim your tax refund if you've overpaid through PAYE. We handle the entire process with HMRC.",
        'badge_color': 'paye',
        'icon_emoji': '💰',
        'display_order': 2,
        'ai_strict_flow': True,
        'ai_system_prompt': """You are an AI assistant helping with PAYE Tax Refund claims in the UK.

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

Only move to the next step after completing the current one. When speaking to Uzbek-speaking users, use Uzbek for explanations and document names where listed above.""",
        'ai_collect_items': [
            'Full name',
            'National Insurance raqamingiz (National Insurance number)',
            'Which tax years to claim (last 4 years possible)',
            'Employer details (name, dates worked)',
            'Email manzilingiz va telefon raqamingiz (email and phone number)',
            'Angliyadan tashqaridagi manzilingiz – Uzb/KZ/KGZ/TJK (address outside UK)',
            'Karta rekvizitlaringiz: Sort code va account nomer (from your UK bank card)',
            'Nechinchi bor kelishingiz ishga? (How many times have you come to work?)',
        ],
        'ai_documents_list': [
            'P45 – PDF / fayli shaklida (in file/PDF form)',
            'Pasportingiz – rasm yoki scaner qilib (passport – photo or scan)',
            'Angliyadan tashqaridagi manzilingiz (Uzb/KZ/KGZ/TJK)',
            'National Insurance raqamingiz',
            'Email va telefon raqamingiz',
            'Karta rekvizitlaringiz – Angliya kartangizdan Sort code va account nomer',
            'Nechinchi bor kelishingiz ishga? (answer in text)',
        ],
    },
    {
        'slug': 'schengen',
        'name': 'Schengen Visa',
        'name_ru': 'Шенген виза',
        'name_uz': 'Shengen viza',
        'description': 'Assistance with Schengen visa applications: documents, Sharecode, Evisa, proof of address, bank statements.',
        'badge_color': 'general',
        'icon_emoji': '🇪🇺',
        'display_order': 3,
        'ai_strict_flow': False,
        'ai_system_prompt': """You are an AI assistant helping with Schengen visa applications.

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

Guide them step by step. When the user writes in Uzbek, use Uzbek for explanations and document names where listed above.""",
        'ai_collect_items': [
            'Full name (as in passport)',
            'Passport number and validity',
            'Sharecode',
            'Evisa (if applicable)',
            'Yashash manzili (residence address)',
            "O'qish yoki ish joyidan malumotnoma (letter from school or employer)",
            'Email and phone number',
            'If working full-time: payslip',
            'Last 3 months bank statement (ohirgi 3 oylik bank statement)',
        ],
        'ai_documents_list': [
            'Passport',
            'Sharecode',
            'Evisa',
            'Yashash manzili (proof of address)',
            "O'qish yoki ish joyidan malumotnoma",
            'Email and telephone number (written/confirmed)',
            'Rasm 3.5×4.5 (photo 3.5×4.5 cm)',
            'Full-time ishlasa: payslip',
            'Bank statement – last 3 months (ohirgi 3 oylik)',
        ],
    },
    {
        'slug': 'self',
        'name': 'Self Assessment Tax',
        'name_ru': 'Налог на самозанятость',
        'name_uz': 'Mustaqil soliq',
        'description': 'Professional self-assessment tax return preparation and filing for freelancers and self-employed.',
        'badge_color': 'self',
        'icon_emoji': '📊',
        'display_order': 4,
        'ai_strict_flow': False,
        'ai_system_prompt': """You are an AI assistant helping with Self Assessment Tax Returns in the UK.

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

Guide them through the information collection process.""",
        'ai_collect_items': [
            'Full name and UTR number',
            'Tax year for the return',
            'Sources of income (self-employment, rental, dividends, etc.)',
            'Business expenses to claim',
            'Previous tax returns submitted',
        ],
        'ai_documents_list': [
            'Bank statements for the tax year',
            'Income records/invoices',
            'Expense receipts',
            'Previous tax return (if available)',
        ],
    },
    {
        'slug': 'company',
        'name': 'Company Accounting',
        'name_ru': 'Бухгалтерия компании',
        'name_uz': 'Kompaniya hisobi',
        'description': 'Full accounting services for limited companies including VAT, payroll, and annual accounts.',
        'badge_color': 'company',
        'icon_emoji': '🏢',
        'display_order': 5,
        'ai_strict_flow': False,
        'ai_system_prompt': """You are an AI assistant helping with Company Accounting services in the UK.

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

Understand their accounting needs and guide them accordingly.""",
        'ai_collect_items': [
            'Company name and registration number',
            'Director details',
            'Financial year end date',
            'VAT registration status',
            'Payroll requirements',
        ],
        'ai_documents_list': [
            'Certificate of incorporation',
            'Bank statements',
            'Sales invoices',
            'Purchase receipts',
            'Payroll records (if applicable)',
        ],
    },
]


class Command(BaseCommand):
    help = 'Load AI config and service data (from docs/AI_CONFIG_AND_SERVICES.md) into service_definitions table.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be created/updated without writing to DB.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run – no DB changes'))

        for data in SERVICES:
            slug = data['slug']
            defaults = {
                'name': data['name'],
                'name_ru': data['name_ru'],
                'name_uz': data['name_uz'],
                'description': data['description'],
                'badge_color': data['badge_color'],
                'icon_emoji': data['icon_emoji'],
                'display_order': data['display_order'],
                'ai_strict_flow': data['ai_strict_flow'],
                'ai_system_prompt': data['ai_system_prompt'],
                'ai_collect_items': json.dumps(data['ai_collect_items'], ensure_ascii=False),
                'ai_documents_list': json.dumps(data['ai_documents_list'], ensure_ascii=False),
            }
            if dry_run:
                self.stdout.write(f'Would create/update: {slug} – {defaults["name"]}')
                continue
            obj, created = ServiceDefinition.objects.update_or_create(
                slug=slug,
                defaults=defaults,
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'  {action}: {obj.slug} – {obj.name}'))

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'Done. {len(SERVICES)} services in DB.'))
