from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_group_chat_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='aisettings',
            name='ai_master_enabled',
            field=models.BooleanField(
                default=True,
                help_text='Global AI switch. When OFF the bot never calls OpenAI, regardless of per-chat settings.',
            ),
        ),
    ]
