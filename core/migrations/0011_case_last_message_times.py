from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_ai_settings_prompt_blocks"),
    ]

    operations = [
        migrations.AddField(
            model_name="case",
            name="last_user_message_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="case",
            name="last_admin_message_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

