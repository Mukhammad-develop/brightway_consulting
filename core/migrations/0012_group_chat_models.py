from django.db import migrations, models
import django.db.models.deletion
from datetime import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_case_last_message_times'),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupChat',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group_id', models.BigIntegerField(unique=True, help_text='Telegram chat ID (negative for supergroups)')),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('language', models.CharField(
                    choices=[('uz', 'Uzbek'), ('ru', 'Russian'), ('en', 'English')],
                    default='uz', max_length=10,
                    help_text='Default language for bot replies in this group')),
                ('cooldown_hours', models.PositiveIntegerField(default=24,
                    help_text='Hours before the bot re-engages the same user')),
                ('behavior_prompt', models.TextField(blank=True, default='',
                    help_text='AI instructions for what topics to handle in this group')),
                ('created_at', models.DateTimeField(default=datetime.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'group_chats', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='GroupBotMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='bot_messages', to='core.groupchat')),
                ('message_id', models.BigIntegerField()),
                ('triggered_by_user_id', models.BigIntegerField(blank=True, null=True,
                    help_text="User whose message triggered this bot reply")),
                ('created_at', models.DateTimeField(default=datetime.now)),
            ],
            options={'db_table': 'group_bot_messages', 'unique_together': {('group', 'message_id')}},
        ),
        migrations.CreateModel(
            name='GroupCooldown',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='cooldowns', to='core.groupchat')),
                ('user_tg_id', models.BigIntegerField()),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(default=datetime.now)),
            ],
            options={'db_table': 'group_cooldowns', 'unique_together': {('group', 'user_tg_id')}},
        ),
    ]
