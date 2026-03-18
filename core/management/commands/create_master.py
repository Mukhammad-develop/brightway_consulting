"""
Create a master admin user (stored in DB). Use for first-time setup or new master accounts.
"""

from django.core.management.base import BaseCommand
from core.models import AdminUser
from panel.views.helpers import hash_password


class Command(BaseCommand):
    help = 'Create a new master admin user (username + password stored in DB).'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True, help='Login username')
        parser.add_argument('--password', required=True, help='Login password (min 6 chars)')
        parser.add_argument('--display-name', default='', help='Display name (default: username)')

    def handle(self, *args, **options):
        username = options['username'].strip()
        password = options['password']
        display_name = (options['display_name'] or '').strip() or username

        if not username:
            self.stderr.write(self.style.ERROR('Username is required.'))
            return

        if len(password) < 6:
            self.stderr.write(self.style.ERROR('Password must be at least 6 characters.'))
            return

        if AdminUser.objects.filter(username=username).exists():
            self.stderr.write(self.style.ERROR(f'Username "{username}" already exists.'))
            return

        AdminUser.objects.create(
            username=username,
            password_hash=hash_password(password),
            role='master',
            display_name=display_name,
            is_active=True,
        )
        self.stdout.write(self.style.SUCCESS(f'Master admin "{username}" created.'))
