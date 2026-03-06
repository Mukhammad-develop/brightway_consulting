"""
Management command to seed sample data for testing the admin panel.
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from core.models import (
    TgUser, Case, Document, Payment, AdminUser,
    ServiceDefinition, ServiceStep, Notification, ClientNote
)
from panel.views.helpers import hash_password


class Command(BaseCommand):
    help = 'Seed sample data for testing the admin panel'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            Notification.objects.all().delete()
            ClientNote.objects.all().delete()
            Document.objects.all().delete()
            Payment.objects.all().delete()
            Case.objects.all().delete()
            TgUser.objects.all().delete()
            ServiceStep.objects.all().delete()
            ServiceDefinition.objects.all().delete()
        
        self.stdout.write('Seeding sample data...')
        
        # Create admin users if not exist
        admins = self.create_admin_users()
        
        # Create service definitions
        self.create_services()
        
        # Create service steps
        self.create_service_steps()
        
        # Create sample users
        users = self.create_users()
        
        # Create sample cases
        cases = self.create_cases(users)
        
        # Create sample documents
        self.create_documents(cases)
        
        # Create sample payments
        self.create_payments(cases)
        
        # Create sample notifications
        self.create_notifications(admins)
        
        # Create sample client notes
        self.create_client_notes(users, admins)
        
        self.stdout.write(self.style.SUCCESS('Sample data seeded successfully!'))
        self.stdout.write(f'  - {TgUser.objects.count()} users')
        self.stdout.write(f'  - {Case.objects.count()} cases')
        self.stdout.write(f'  - {Document.objects.count()} documents')
        self.stdout.write(f'  - {Payment.objects.count()} payments')
        self.stdout.write(f'  - {ServiceDefinition.objects.count()} services')
        self.stdout.write(f'  - {ServiceStep.objects.count()} service steps')
        self.stdout.write(f'  - {Notification.objects.count()} notifications')
        self.stdout.write(f'  - {ClientNote.objects.count()} client notes')

    def create_admin_users(self):
        """Create admin users for testing."""
        admins_data = [
            ('admin', 'admin123', 'master', 'Master Admin'),
            ('consultant1', 'pass123', 'consultant', 'John Consultant'),
            ('consultant2', 'pass123', 'consultant', 'Sarah Helper'),
        ]
        
        created_admins = []
        for username, password, role, display_name in admins_data:
            admin, created = AdminUser.objects.get_or_create(
                username=username,
                defaults={
                    'password_hash': hash_password(password),
                    'role': role,
                    'display_name': display_name,
                }
            )
            created_admins.append(admin)
            if created:
                self.stdout.write(f'  Created admin: {username}')
        
        return created_admins

    def create_services(self):
        """Create service definitions."""
        services = [
            {
                'slug': 'student',
                'name': 'Student Visa & University',
                'name_ru': 'Студенческая виза',
                'name_uz': "Talaba vizasi",
                'description': 'Complete assistance with student visa applications, university admissions, and educational guidance.',
                'badge_color': 'student',
                'icon_emoji': '🎓',
                'display_order': 1,
            },
            {
                'slug': 'paye',
                'name': 'PAYE Tax Refund',
                'name_ru': 'Возврат налога PAYE',
                'name_uz': 'PAYE soliq qaytarish',
                'description': 'Claim your tax refund if you\'ve overpaid through PAYE. We handle the entire process with HMRC.',
                'badge_color': 'paye',
                'icon_emoji': '💰',
                'display_order': 2,
            },
            {
                'slug': 'schengen',
                'name': 'Schengen Visa',
                'name_ru': 'Шенген виза',
                'name_uz': 'Shengen viza',
                'description': 'Assistance with Schengen visa applications: documents, Sharecode, Evisa, proof of address, bank statements.',
                'badge_color': 'general',
                'icon_emoji': '🇪🇺',
                'display_order': 3,
            },
            {
                'slug': 'self',
                'name': 'Self Assessment Tax',
                'name_ru': 'Налог на самозанятость',
                'name_uz': 'Mustaqil soliq',
                'description': 'Professional self-assessment tax return preparation and filing for freelancers and self-employed.',
                'badge_color': 'self',
                'icon_emoji': '📊',
                'display_order': 4,
            },
            {
                'slug': 'company',
                'name': 'Company Accounting',
                'name_ru': 'Бухгалтерия компании',
                'name_uz': 'Kompaniya hisobi',
                'description': 'Full accounting services for limited companies including VAT, payroll, and annual accounts.',
                'badge_color': 'company',
                'icon_emoji': '🏢',
                'display_order': 5,
            },
        ]
        
        for svc in services:
            if not ServiceDefinition.objects.filter(slug=svc['slug']).exists():
                ServiceDefinition.objects.create(**svc)
                self.stdout.write(f"  Created service: {svc['name']}")

    def create_users(self):
        """Create sample Telegram users."""
        users_data = [
            (100001, 'john_doe', 'John', 'Doe', '+44123456789', 'en'),
            (100002, 'maria_smith', 'Maria', 'Smith', '+44987654321', 'en'),
            (100003, 'alex_jones', 'Alexander', 'Jones', None, 'en'),
            (100004, 'sergey_ivanov', 'Sergey', 'Ivanov', '+79111234567', 'ru'),
            (100005, 'anna_petrova', 'Anna', 'Petrova', '+79119876543', 'ru'),
            (100006, 'otabek_uzb', 'Otabek', 'Karimov', '+998901234567', 'uz'),
            (100007, 'dilshod_tash', 'Dilshod', 'Tashkent', '+998939876543', 'uz'),
            (100008, None, 'Michael', 'Brown', '+44555123456', 'en'),
            (100009, 'emma_wilson', 'Emma', 'Wilson', None, 'en'),
            (100010, 'david_lee', 'David', 'Lee', '+44777888999', 'en'),
        ]
        
        users = []
        for tg_id, username, first_name, last_name, phone, lang in users_data:
            user, created = TgUser.objects.get_or_create(
                telegram_id=tg_id,
                defaults={
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone': phone,
                    'language_code': lang,
                    'created_at': datetime.now() - timedelta(days=random.randint(1, 90)),
                }
            )
            users.append(user)
            if created:
                self.stdout.write(f'  Created user: {username or tg_id}')
        
        return users

    def create_cases(self, users):
        """Create sample cases."""
        services = ['student', 'paye', 'schengen', 'self', 'company', 'general']
        statuses = ['active', 'active', 'active', 'completed', 'completed', 'cancelled']
        payment_statuses = ['pending', 'pending', 'received', 'received', 'refunded']
        
        cases = []
        for user in users:
            # Each user gets 1-3 cases
            num_cases = random.randint(1, 3)
            for _ in range(num_cases):
                service = random.choice(services)
                status = random.choice(statuses)
                payment_status = random.choice(payment_statuses)
                total_amount = Decimal(random.choice([0, 150, 250, 350, 500]))
                paid_amount = total_amount if payment_status == 'received' else Decimal(0)
                
                case, created = Case.objects.get_or_create(
                    user=user,
                    service=service,
                    defaults={
                        'status': status,
                        'payment_status': payment_status,
                        'total_amount': total_amount,
                        'paid_amount': paid_amount,
                        'currency': 'GBP',
                        'notes': f'Sample case for {service} service',
                        'created_at': datetime.now() - timedelta(days=random.randint(1, 60)),
                    }
                )
                cases.append(case)
                
                # Add sample conversation
                if created:
                    case.add_message('user', f'Hello, I need help with {service} service.')
                    case.add_message('assistant', f'Hi! I\'d be happy to help you with {service}. Could you provide more details about your situation?')
                    case.add_message('user', 'Sure, I have some documents to share.')
        
        return cases

    def create_documents(self, cases):
        """Create sample documents for cases."""
        doc_types = [
            ('passport.pdf', 'pdf', 'document'),
            ('p45.pdf', 'pdf', 'document'),
            ('payslip.jpg', 'jpg', 'photo'),
            ('bank_statement.pdf', 'pdf', 'document'),
            ('id_card.png', 'png', 'photo'),
        ]
        
        for case in cases:
            # Each case gets 0-3 documents
            num_docs = random.randint(0, 3)
            for _ in range(num_docs):
                filename, file_type, media_type = random.choice(doc_types)
                unique_id = f'{random.randint(10000, 99999)}'
                
                Document.objects.get_or_create(
                    case=case,
                    file_unique_id=unique_id,
                    defaults={
                        'file_path': filename,
                        'file_type': file_type,
                        'telegram_file_id': f'sample_file_{unique_id}',
                        'media_type': media_type,
                        'description': f'Sample {file_type} document',
                    }
                )

    def create_payments(self, cases):
        """Create sample payments for cases."""
        payment_methods = ['Bank Transfer', 'PayPal', 'Stripe', 'Cash']
        
        for case in cases:
            if case.payment_status == 'received' and case.paid_amount > 0:
                Payment.objects.get_or_create(
                    case=case,
                    defaults={
                        'amount': case.paid_amount,
                        'currency': case.currency,
                        'method': random.choice(payment_methods),
                        'status': 'completed',
                        'payment_date': case.created_at + timedelta(days=random.randint(1, 7)),
                    }
                )



    def create_service_steps(self):
        """Create service steps for each service."""
        service_steps = {
            'student': [
                ('paid', 'Paid', 1, False),
                ('docs_received', 'Documents Received', 2, False),
                ('application_prepared', 'Application Prepared', 3, False),
                ('submitted', 'Submitted', 4, False),
                ('done', 'Done', 5, True),
            ],
            'paye': [
                ('paid', 'Paid', 1, False),
                ('p45_verified', 'P45 Verified', 2, False),
                ('docs_collected', 'Documents Collected', 3, False),
                ('submitted_hmrc', 'Submitted to HMRC', 4, False),
                ('refund_processed', 'Refund Processed', 5, False),
                ('done', 'Done', 6, True),
            ],
            'self': [
                ('paid', 'Paid', 1, False),
                ('info_gathered', 'Info Gathered', 2, False),
                ('return_prepared', 'Return Prepared', 3, False),
                ('filed', 'Filed', 4, False),
                ('done', 'Done', 5, True),
            ],
            'company': [
                ('paid', 'Paid', 1, False),
                ('onboarded', 'Onboarded', 2, False),
                ('books_updated', 'Books Updated', 3, False),
                ('filed', 'Filed', 4, False),
                ('done', 'Done', 5, True),
            ],
        }
        
        for slug, steps in service_steps.items():
            try:
                service = ServiceDefinition.objects.get(slug=slug)
                for step_slug, label, order, is_final in steps:
                    ServiceStep.objects.get_or_create(
                        service=service,
                        slug=step_slug,
                        defaults={
                            'label': label,
                            'step_number': order,
                            'is_final': is_final,
                            'title': label,
                        }
                    )
            except ServiceDefinition.DoesNotExist:
                pass
        
        self.stdout.write(f'  Created service steps')

    def create_notifications(self, admins):
        """Create sample notifications for admin users."""
        notifications_data = [
            ('New User Registered', 'A new user has joined the platform. Review their profile.'),
            ('Case Completed', 'Case #42 has been marked as completed.'),
            ('Payment Received', 'Payment of £250 received for Case #38.'),
            ('Document Uploaded', 'User John Doe uploaded a new document.'),
            ('Weekly Report Ready', 'Your weekly performance report is ready to view.'),
        ]
        
        for admin in admins:
            # Each admin gets 2-4 random notifications
            num_notifications = random.randint(2, 4)
            for i in range(num_notifications):
                title, message = random.choice(notifications_data)
                Notification.objects.create(
                    admin_user=admin,
                    title=title,
                    message=message,
                    is_read=random.choice([True, False]),
                    link='/admin/dashboard' if random.random() > 0.5 else None,
                )
        
        self.stdout.write(f'  Created sample notifications')

    def create_client_notes(self, users, admins):
        """Create sample client notes."""
        notes_templates = [
            'Client expressed interest in additional services.',
            'Follow up required regarding document submission.',
            'Client prefers communication in Russian.',
            'VIP client - prioritize their requests.',
            'Referred by existing client John Smith.',
            'Client has tight deadline - urgent case.',
        ]
        
        for user in users[:5]:  # Add notes for first 5 users
            admin = random.choice(admins)
            num_notes = random.randint(1, 2)
            for _ in range(num_notes):
                ClientNote.objects.create(
                    user=user,
                    admin_user=admin,
                    author_name=admin.display_name or admin.username,
                    note_text=random.choice(notes_templates),
                    is_pinned=random.random() > 0.7,  # 30% chance of being pinned
                )
        
        self.stdout.write(f'  Created sample client notes')
