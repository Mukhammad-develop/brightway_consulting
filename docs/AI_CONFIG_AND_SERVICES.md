# Full AI configuration and service information

## Global AI configuration

- **Chat model:** `gpt-4o-mini`
- **Service detection (classifier):** `gpt-4o-mini`, max_tokens=20, temperature=0.1
- **Chat:** max_tokens=800, temperature=0.3, timeout=30s
- **Rate limit:** 30 AI calls per minute (shared)
- **Language:** `lang_map = {'en': 'English', 'ru': 'Russian', 'uz': 'Uzbek'}`; target language is appended to the system prompt. If the user’s last message is mainly in Uzbek → reply in Uzbek; mainly in Russian → reply in Russian; otherwise use `target_lang`.
- **Marker:** When collection is complete, the AI must end with `[READY_FOR_CONSULTANT]` on its own line.
- **Shared rules appended to every service prompt:** TONE_RULES, ANTI_BOT_PATTERNS, STYLE_EXAMPLES, language rule, “reply to actual last message”, FILENAME hint for file uploads.
- **Source of prompts:** If `ServiceDefinition` for that slug exists and has `ai_system_prompt` set, the DB is used (and optionally `ai_collect_items`, `ai_documents_list`, `ai_strict_flow`). Otherwise hardcoded prompts in `bot/services.py` are used.

---

## 1. Student Visa & University

**Slug:** `student`

**General (seed_data / display):**
- Name (EN): Student Visa & University  
- Name (RU): Студенческая виза  
- Name (UZ): Talaba vizasi  
- Description: Complete assistance with student visa applications, university admissions, and educational guidance.  
- Badge: `student` | Icon: 🎓 | Order: 1  

**AI – information to collect:**
- Full name (as in passport)
- Passport number
- Date of birth
- University name and course
- CAS number (if available)
- Previous UK visa history

**AI – documents to request:**
- Passport scan (photo page)
- University acceptance letter
- Financial documents (bank statements)
- English test results (IELTS/TOEFL)

**AI system prompt (hardcoded):**  
*You are an AI assistant helping with Student Visa and University applications for the UK. Your job is to collect the information and request the documents listed above. Guide them step by step, asking for one piece at a time.*

**SERVICE_INFO (fallback):**  
collect_items: Full name, Passport number, Date of birth, University name, Course details, CAS number  
documents: Passport scan, University acceptance letter, Financial documents, English test results  
strict_flow: not set  

---

## 2. PAYE Tax Refund

**Slug:** `paye`

**General:**
- Name (EN): PAYE Tax Refund  
- Name (RU): Возврат налога PAYE  
- Name (UZ): PAYE soliq qaytarish  
- Description: Claim your tax refund if you've overpaid through PAYE. We handle the entire process with HMRC.  
- Badge: `paye` | Icon: 💰 | Order: 2  

**AI – information to collect:**
- Full name
- National Insurance raqamingiz (National Insurance number)
- Which tax years to claim (last 4 years possible)
- Employer details (name, dates worked)
- Email manzilingiz va telefon raqamingiz (email and phone number)
- Angliyadan tashqaridagi manzilingiz – Uzb/KZ/KGZ/TJK (address outside UK)
- Karta rekvizitlaringiz: Sort code va account nomer (from your UK bank card)
- Nechinchi bor kelishingiz ishga? (How many times have you come to work?)

**AI – documents to request:**
- P45 – PDF / fayli shaklida (in file/PDF form)
- Pasportingiz – rasm yoki scaner qilib (passport – photo or scan)
- Angliyadan tashqaridagi manzilingiz (Uzb/KZ/KGZ/TJK)
- National Insurance raqamingiz
- Email va telefon raqamingiz
- Karta rekvizitlaringiz – Angliya kartangizdan Sort code va account nomer
- Nechinchi bor kelishingiz ishga? (answer in text)

**AI system prompt (hardcoded):**  
*You are an AI assistant helping with PAYE Tax Refund claims in the UK. Collect the above information and request the above documents one at a time. Only move to the next step after completing the current one. When speaking to Uzbek-speaking users, use Uzbek for explanations and document names where listed above.*

**SERVICE_INFO:** strict_flow: True  

---

## 3. Schengen Visa

**Slug:** `schengen`

**General:**
- Name (EN): Schengen Visa  
- Name (RU): Шенген виза  
- Name (UZ): Shengen viza  
- Description: Assistance with Schengen visa applications: documents, Sharecode, Evisa, proof of address, bank statements.  
- Badge: `general` | Icon: 🇪🇺 | Order: 3  

**AI – information to collect:**
- Full name (as in passport)
- Passport number and validity
- Sharecode
- Evisa (if applicable)
- Yashash manzili (residence address)
- O'qish yoki ish joyidan malumotnoma (letter from school or employer)
- Email and phone number
- If working full-time: payslip
- Last 3 months bank statement (ohirgi 3 oylik bank statement)

**AI – documents to request:**
- Passport
- Sharecode
- Evisa
- Yashash manzili (proof of address)
- O'qish yoki ish joyidan malumotnoma
- Email and telephone number (written/confirmed)
- Rasm 3.5×4.5 (photo 3.5×4.5 cm)
- Full-time ishlasa: payslip
- Bank statement – last 3 months (ohirgi 3 oylik)

**AI system prompt (hardcoded):**  
*You are an AI assistant helping with Schengen visa applications. Collect the above and request the documents one at a time. When the user writes in Uzbek, use Uzbek for explanations and document names where listed above.*

**SERVICE_INFO:** strict_flow: not set  

---

## 4. Self Assessment Tax

**Slug:** `self`

**General:**
- Name (EN): Self Assessment Tax  
- Name (RU): Налог на самозанятость  
- Name (UZ): Mustaqil soliq  
- Description: Professional self-assessment tax return preparation and filing for freelancers and self-employed.  
- Badge: `self` | Icon: 📊 | Order: 4  

**AI – information to collect:**
- Full name and UTR number
- Tax year for the return
- Sources of income (self-employment, rental, dividends, etc.)
- Business expenses to claim
- Previous tax returns submitted

**AI – documents to request:**
- Bank statements for the tax year
- Income records/invoices
- Expense receipts
- Previous tax return (if available)

**AI system prompt (hardcoded):**  
*You are an AI assistant helping with Self Assessment Tax Returns in the UK. Collect the above and request the documents. Guide them through the information collection process.*

**SERVICE_INFO:**  
collect_items: Full name, UTR number, Tax year, Income sources, Expenses  
documents: ID document, Bank statements, Income records, Expense receipts  

---

## 5. Company Accounting

**Slug:** `company`

**General:**
- Name (EN): Company Accounting  
- Name (RU): Бухгалтерия компании  
- Name (UZ): Kompaniya hisobi  
- Description: Full accounting services for limited companies including VAT, payroll, and annual accounts.  
- Badge: `company` | Icon: 🏢 | Order: 5  

**AI – information to collect:**
- Company name and registration number
- Director details
- Financial year end date
- VAT registration status
- Payroll requirements

**AI – documents to request:**
- Certificate of incorporation
- Bank statements
- Sales invoices
- Purchase receipts
- Payroll records (if applicable)

**AI system prompt (hardcoded):**  
*You are an AI assistant helping with Company Accounting services in the UK. Collect the above and request the documents. Understand their accounting needs and guide them accordingly.*

**SERVICE_INFO:**  
collect_items: Company name, Company number, Director details, VAT registration  
documents: Certificate of incorporation, Bank statements, Invoices, Receipts  

---

## Service detection (AI classifier)

Used to route the first (or unclear) message to a service. Single call, no keywords.

- **Prompt:** Classifier is told the list of services (student, paye, schengen, self, company, general) with short descriptions and must respond with only the slug.
- **Valid slugs:** `student`, `paye`, `schengen`, `self`, `company`, `general`. If the result is `general`, the code treats it as no specific service (case uses `general`).
- **Model:** gpt-4o-mini, max_tokens=20, temperature=0.1.
- **Context:** Last 5 messages can be passed as conversation_history for the classifier.

---

## Load this config into the database

To create or update the 5 services in `service_definitions` with the AI prompts and lists from this doc (and from `bot/services.py`), run:

```bash
cd /path/to/brightway_consulting && python manage.py load_ai_services
```

- Use `--dry-run` to see what would be created/updated without writing:  
  `python manage.py load_ai_services --dry-run`
- Command: `core/management/commands/load_ai_services.py`. It uses the same data as this doc and the hardcoded prompts.

---

## Where this lives in code

| What | Where |
|------|--------|
| Global AI (model, rate limit, tone, language) | `bot/services.py` |
| Hardcoded per-service prompts | `bot/services.py` → `_build_hardcoded_prompt()` |
| SERVICE_INFO (collect_items, documents, strict_flow) | `bot/services.py` → `SERVICE_INFO` |
| Seed data (names, descriptions, badge, icon, order) | `core/management/commands/seed_data.py` → `create_services()` |
| DB overrides (ai_system_prompt, ai_collect_items, ai_documents_list, ai_strict_flow) | `core.models.ServiceDefinition`; panel: Services CRUD |
| build_system_prompt | `bot/services.py` → uses DB if present, else hardcoded |
| Classifier prompt and valid_services | `bot/services.py` → `ai_detect_service()` |
