from django.db import migrations, models


def seed_ai_settings_defaults(apps, schema_editor):
    AiSettings = apps.get_model("core", "AiSettings")

    # Seed row pk=1 with sane defaults. Admin can edit later in Services & AI.
    obj, _ = AiSettings.objects.get_or_create(pk=1)

    if not (obj.general_system_prompt or "").strip():
        obj.general_system_prompt = (
            "You are a helpful AI assistant for Brightway Consulting, a UK-based consultancy "
            "that helps with student visas, tax refunds, and company accounting.\n\n"
            "Your job is to:\n"
            "1. Understand what service the user needs\n"
            "2. Collect necessary information and documents (step by step)\n"
            "3. When collection is complete, assign them to a consultant\n"
            "4. Be helpful and professional\n\n"
            "If you can't determine what service they need, ask clarifying questions."
        )

    if not (obj.collect_and_assign_behavior or "").strip():
        obj.collect_and_assign_behavior = (
            "YOUR ROLE:\n"
            "- You are an assistant for Brightway Consulting. Your job is to collect the information and documents we need for the user's service, then assign them to a human consultant.\n"
            "- At the start of the conversation (or when the user chooses a service), briefly state: you will collect the required information and then assign them to a consultant who will take over.\n"
            "- Collect information and documents step by step: ask for one thing at a time, acknowledge what they provide, then ask for the next.\n"
            "- When you have collected ALL required information and documents listed for this service, end your reply with exactly [READY_FOR_CONSULTANT] on its own line.\n"
            "- Do NOT output [READY_FOR_CONSULTANT] until you have collected every required item and document."
        )

    if not (obj.tone_rules or "").strip():
        obj.tone_rules = (
            "TONE RULES:\n"
            "- Sound like a real consultant in a live chat, not a formal letter\n"
            "- Be friendly but professional\n"
            "- Keep responses concise but helpful\n"
            "- Ask one question at a time\n"
            "- Acknowledge what the user says before asking for more"
        )

    if not (obj.anti_bot_patterns or "").strip():
        obj.anti_bot_patterns = (
            "AVOID THESE PATTERNS:\n"
            "- Don't say \"Great!\", \"Absolutely!\", \"Certainly!\"\n"
            "- Don't say \"Kindly provide...\"\n"
            "- Don't use overly formal phrases\n"
            "- Don't repeat the same greeting structure"
        )

    if not (obj.style_examples or "").strip():
        obj.style_examples = (
            "GOOD EXAMPLES:\n"
            "EN: \"Got it! And what's your passport number?\"\n"
            "RU: \"Понял! А какой у вас номер паспорта?\"\n"
            "UZ: \"Tushundim! Pasport raqamingiz qanday?\""
        )

    if not (obj.natural_language_rules or "").strip():
        obj.natural_language_rules = (
            "When replying in Uzbek or Russian, sound natural and conversational:\n"
            "- Use everyday spoken language, as in a friendly chat\n"
            "- Avoid stiff, formal or textbook phrases\n"
            "- Match the language the user is writing in; do not switch based on name"
        )

    if not (obj.common_rules or "").strip():
        obj.common_rules = (
            "CRITICAL – Language:\n"
            "- You MUST reply in the same language as the user's last message.\n"
            "- Do NOT change language based on the user's name.\n\n"
            "Respond to the user's actual last message.\n"
            "If the user's message is exactly \"[Sticker]\", ask them to type what they need.\n"
            "When the user sent a file, you may suggest a short filename by adding: FILENAME: label"
        )

    obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_ai_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="aisettings",
            name="general_system_prompt",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="aisettings",
            name="collect_and_assign_behavior",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="aisettings",
            name="tone_rules",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="aisettings",
            name="anti_bot_patterns",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="aisettings",
            name="style_examples",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="aisettings",
            name="natural_language_rules",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="aisettings",
            name="common_rules",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(seed_ai_settings_defaults, migrations.RunPython.noop),
    ]

