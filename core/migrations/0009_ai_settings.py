from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_adminuser_responsible_services"),
    ]

    operations = [
        migrations.CreateModel(
            name="AiSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_classifier_prompt", models.TextField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "ai_settings",
            },
        ),
    ]

