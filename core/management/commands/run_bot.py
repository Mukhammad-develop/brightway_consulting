#!/usr/bin/env python3
"""
Django management command to run the Telegram bot.

Usage:
    python manage.py run_bot
    python manage.py run_bot --userbot
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run the Telegram bot or userbot'

    def add_arguments(self, parser):
        parser.add_argument(
            '--userbot',
            action='store_true',
            help='Run the userbot instead of the main bot'
        )
        parser.add_argument(
            '--auth',
            action='store_true',
            help='Authenticate userbot account 1'
        )
        parser.add_argument(
            '--auth2',
            action='store_true',
            help='Authenticate userbot account 2'
        )

    def handle(self, *args, **options):
        if options['auth']:
            self.stdout.write('Authenticating userbot account 1...')
            from bot.userbot import authenticate
            authenticate(1)
            
        elif options['auth2']:
            self.stdout.write('Authenticating userbot account 2...')
            from bot.userbot import authenticate
            authenticate(2)
            
        elif options['userbot']:
            self.stdout.write(self.style.SUCCESS('Starting userbot...'))
            from bot.userbot import run_userbot
            run_userbot()
            
        else:
            self.stdout.write(self.style.SUCCESS('Starting Telegram bot...'))
            from bot.bot import run_bot
            run_bot()
