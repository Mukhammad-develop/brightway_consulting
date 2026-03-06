#!/usr/bin/env python3
"""
Django management command to run the Telegram userbot.

Usage:
    # First time only: create session (Telegram will send a code to TG_PHONE)
    python manage.py run_userbot --auth

    # Then start the userbot (uses saved session)
    python manage.py run_userbot

    # Optional second account:
    python manage.py run_userbot --auth2
    python manage.py run_userbot
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run the Telegram userbot. Run with --auth first to log in (session not connected otherwise).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auth',
            action='store_true',
            help='Authenticate account 1 (required once before first run)'
        )
        parser.add_argument(
            '--auth2',
            action='store_true',
            help='Authenticate account 2 (optional)'
        )

    def handle(self, *args, **options):
        from bot.userbot import authenticate, run_userbot
        
        if options['auth']:
            self.stdout.write('Authenticating userbot account 1...')
            authenticate(1)
        elif options['auth2']:
            self.stdout.write('Authenticating userbot account 2...')
            authenticate(2)
        else:
            self.stdout.write(self.style.SUCCESS('Starting userbot...'))
            run_userbot()
