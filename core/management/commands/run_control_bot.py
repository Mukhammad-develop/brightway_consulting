#!/usr/bin/env python3
"""
Django management command to run the consultant control bot.

Usage:
    python manage.py run_control_bot
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run the consultant control bot (forward a client message to stop/resume the bot).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting consultant control bot...'))
        from bot.control_bot import run
        run()
