"""
Core database models for Brightway Consulting.

All models are defined here to ensure proper relationships and organization.
"""

import json
from datetime import datetime
from django.db import models


class TgUser(models.Model):
    """Telegram user model - stores user information from Telegram."""
    
    telegram_id = models.BigIntegerField(unique=True, db_column='tg_id')
    username = models.CharField(max_length=100, null=True, blank=True)
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    language_code = models.CharField(max_length=10, default='en', db_column='language')
    is_bot = models.BooleanField(default=False)
    profile_data = models.TextField(default='{}')  # JSON field
    profile_photo_path = models.CharField(max_length=500, null=True, blank=True)  # relative path under uploads/profiles/
    bio = models.TextField(null=True, blank=True)  # Telegram "about" / bio
    chat_mode = models.CharField(max_length=20, default='menu')
    linked_account = models.IntegerField(default=0)  # Which userbot sent last
    created_at = models.DateTimeField(default=datetime.now)
    
    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
    
    def __str__(self):
        if self.username:
            return f"@{self.username}"
        return f"User {self.telegram_id}"
    
    def get_profile_data(self):
        """Parse and return profile data as dict."""
        try:
            return json.loads(self.profile_data or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_profile_data(self, data):
        """Set profile data from dict."""
        self.profile_data = json.dumps(data)
        self.save(update_fields=['profile_data'])


class Case(models.Model):
    """Case model - represents a consulting case for a user."""
    
    SERVICE_CHOICES = [
        ('student', 'Student Visa & University'),
        ('paye', 'PAYE Tax Refund'),
        ('self', 'Self Assessment Tax'),
        ('company', 'Company Accounting'),
        ('general', 'General Inquiry'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('received', 'Received'),
        ('refunded', 'Refunded'),
    ]
    
    user = models.ForeignKey(TgUser, on_delete=models.CASCADE, related_name='cases')
    service = models.CharField(max_length=50, choices=SERVICE_CHOICES, default='general')
    assigned_to = models.ForeignKey('AdminUser', null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_cases')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='GBP')
    notes = models.TextField(null=True, blank=True)
    conversation_history = models.TextField(default='[]')  # JSON list
    context = models.TextField(default='{}')  # JSON dict
    ai_enabled = models.BooleanField(default=True)  # Assistant can turn off; auto-off when info collected until case closed
    created_at = models.DateTimeField(default=datetime.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'cases'
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Case #{self.pk} - {self.get_service_display()} ({self.status})"
    
    def get_conversation(self):
        """Parse and return conversation history as list."""
        try:
            return json.loads(self.conversation_history or '[]')
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_conversation(self, conv_list):
        """Set conversation history from list."""
        self.conversation_history = json.dumps(conv_list)
        self.save(update_fields=['conversation_history'])
    
    def add_message(self, role, content, sender=None):
        """Append a message to the conversation history."""
        conv = self.get_conversation()
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
        }
        if sender:
            message['sender'] = sender
        conv.append(message)
        self.conversation_history = json.dumps(conv)
        self.save(update_fields=['conversation_history', 'updated_at'])


class Document(models.Model):
    """Document model - stores uploaded documents for cases."""
    
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='documents')
    file_path = models.CharField(max_length=500, db_column='filename', null=True, blank=True)  # actual path on disk
    display_name = models.CharField(max_length=255, null=True, blank=True)  # human-readable name (e.g. passport_123.jpg)
    file_type = models.CharField(max_length=50, db_column='doc_type', null=True, blank=True)
    telegram_file_id = models.TextField(db_column='file_id')  # "local:<filename>" or Telegram file_id
    file_unique_id = models.CharField(max_length=100, null=True, blank=True)
    media_type = models.CharField(max_length=20, default='document')  # document|photo|voice
    transcription = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    uploaded_at = models.DateTimeField(default=datetime.now, db_column='created_at')
    
    class Meta:
        db_table = 'documents'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"Document: {self.file_path or self.telegram_file_id[:20]}..."


class Payment(models.Model):
    """Payment model - tracks payments for cases."""
    
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='GBP')
    payment_date = models.DateTimeField(default=datetime.now, db_column='created_at')
    method = models.CharField(max_length=50, null=True, blank=True)
    reference = models.CharField(max_length=100, null=True, blank=True, db_column='proof_file_id')
    notes = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, default='pending')
    
    class Meta:
        db_table = 'payments'
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"Payment #{self.pk} - {self.currency} {self.amount}"


class AdminUser(models.Model):
    """Admin user model for panel authentication."""
    
    ROLE_CHOICES = [
        ('master', 'Master'),
        ('admin', 'Admin'),
        ('consultant', 'Consultant'),
    ]
    
    username = models.CharField(max_length=100, unique=True)
    password_hash = models.CharField(max_length=256)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='consultant')
    display_name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    theme_mode = models.CharField(max_length=10, default='dark')  # 'dark' | 'light'
    theme_dark = models.CharField(max_length=20, default='blue')  # color theme when dark
    theme_light = models.CharField(max_length=20, default='blue')  # color theme when light
    created_at = models.DateTimeField(default=datetime.now)
    last_login = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'admin_users'
        ordering = ['username']
    
    def __str__(self):
        return f"{self.display_name or self.username} ({self.role})"


class ServiceDefinition(models.Model):
    """Dynamic service definition - allows admins to configure services."""
    
    slug = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    name_ru = models.CharField(max_length=100, null=True, blank=True)
    name_uz = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(blank=True, default='')
    description_ru = models.TextField(blank=True, default='')
    description_uz = models.TextField(blank=True, default='')
    keywords = models.TextField(blank=True, default='', db_column='service_keywords')  # JSON list
    ai_system_prompt = models.TextField(blank=True, default='')
    ai_collect_items = models.TextField(blank=True, default='')  # JSON list
    ai_documents_list = models.TextField(blank=True, default='')  # JSON list
    ai_strict_flow = models.BooleanField(default=False)
    badge_color = models.CharField(max_length=20, default='general')
    icon_emoji = models.CharField(max_length=10, blank=True, default='📋')
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'service_definitions'
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return f"{self.icon_emoji} {self.name}"
    
    def get_keywords_list(self):
        """Parse and return keywords as list."""
        if not self.keywords:
            return []
        # Handle both comma-separated and JSON formats
        try:
            return json.loads(self.keywords)
        except (json.JSONDecodeError, TypeError):
            return [k.strip() for k in self.keywords.split(',') if k.strip()]
    
    def get_collect_items(self):
        """Parse and return collect items as list."""
        try:
            return json.loads(self.ai_collect_items or '[]')
        except (json.JSONDecodeError, TypeError):
            return []
    
    def get_documents_list(self):
        """Parse and return documents list as list."""
        try:
            return json.loads(self.ai_documents_list or '[]')
        except (json.JSONDecodeError, TypeError):
            return []


class ServiceStep(models.Model):
    """Service step for tracking progress through a service workflow."""
    
    service = models.ForeignKey(ServiceDefinition, on_delete=models.CASCADE, related_name='steps')
    step_number = models.IntegerField(default=0, db_column='order')
    label = models.CharField(max_length=100)
    slug = models.CharField(max_length=50)
    title = models.CharField(max_length=100, null=True, blank=True)
    title_ru = models.CharField(max_length=100, null=True, blank=True)
    title_uz = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(blank=True, default='')
    description_ru = models.TextField(blank=True, default='')
    description_uz = models.TextField(blank=True, default='')
    is_required = models.BooleanField(default=True)
    is_final = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'service_steps'
        ordering = ['step_number']
        unique_together = [['service', 'slug']]
    
    def __str__(self):
        return f"{self.service.name} - Step {self.step_number}: {self.label}"


class CaseTracking(models.Model):
    """Case tracking - tracks current progress of a case through service steps."""
    
    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name='tracking')
    current_step = models.ForeignKey(ServiceStep, null=True, blank=True, on_delete=models.SET_NULL)
    progress_percentage = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True, db_column='updated_at')
    updated_by = models.ForeignKey(AdminUser, null=True, blank=True, on_delete=models.SET_NULL)
    
    class Meta:
        db_table = 'case_tracking'
    
    def __str__(self):
        step_name = self.current_step.label if self.current_step else 'Not started'
        return f"Tracking for Case #{self.case_id} - {step_name}"
    
    def get_completed_steps(self):
        """Get all steps with order < current_step.order."""
        if not self.current_step:
            return ServiceStep.objects.none()
        return ServiceStep.objects.filter(
            service=self.case.service,
            step_number__lt=self.current_step.step_number
        )
    
    def get_progress_pct(self):
        """Calculate progress percentage."""
        if not self.current_step:
            return 0
        max_order = ServiceStep.objects.filter(service=self.case.service).aggregate(
            models.Max('step_number')
        )['step_number__max'] or 1
        return int((self.current_step.step_number / max_order) * 100)


class CaseTrackingLog(models.Model):
    """Log entries for case tracking changes."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    
    tracking = models.ForeignKey(CaseTracking, on_delete=models.CASCADE, related_name='logs', null=True, blank=True)
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='tracking_logs')
    step = models.ForeignKey(ServiceStep, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    from_step = models.ForeignKey(ServiceStep, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    to_step = models.ForeignKey(ServiceStep, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, default='', db_column='note')
    changed_by = models.ForeignKey(AdminUser, null=True, blank=True, on_delete=models.SET_NULL)
    changed_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    
    class Meta:
        db_table = 'case_tracking_log'
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"Log: Case #{self.case_id} step change at {self.changed_at}"


class ClientNote(models.Model):
    """Notes about clients written by admin users."""
    
    user = models.ForeignKey(TgUser, on_delete=models.CASCADE, related_name='notes')
    admin_user = models.ForeignKey(AdminUser, null=True, blank=True, on_delete=models.SET_NULL, db_column='author_id')
    author_name = models.CharField(max_length=100, default='Admin')
    note_text = models.TextField(db_column='content')
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'client_notes'
        ordering = ['-is_pinned', '-created_at']
    
    def __str__(self):
        return f"Note for {self.user} by {self.author_name}"


class Notification(models.Model):
    """Notifications for admin users."""
    
    admin_user = models.ForeignKey(AdminUser, on_delete=models.CASCADE, related_name='notifications', db_column='recipient_id')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=500, null=True, blank=True)
    
    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification: {self.title}"


# Additional models from the specification

class Reminder(models.Model):
    """Reminders for cases."""
    
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='reminders')
    reminder_type = models.CharField(max_length=50, db_column='type')
    due_at = models.DateTimeField()
    sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'reminders'
        ordering = ['due_at']
    
    def __str__(self):
        return f"Reminder for Case #{self.case_id} - {self.reminder_type}"


class PendingSend(models.Model):
    """Pending messages to send via userbot."""
    
    user_tg_id = models.CharField(max_length=50)
    message = models.TextField()
    sender_name = models.CharField(max_length=100, default='Admin')
    sent = models.BooleanField(default=False)
    account_index = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'pending_sends'
        ordering = ['-created_at']
    
    def __str__(self):
        status = "sent" if self.sent else "pending"
        return f"Message to {self.user_tg_id} ({status})"


class ImportRequest(models.Model):
    """Import requests for chat history."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]
    
    user_tg_id = models.CharField(max_length=50)
    label = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message_count = models.IntegerField(default=0)
    error_msg = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'import_requests'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Import {self.user_tg_id} - {self.status}"


class AdminAssignment(models.Model):
    """Assignment of admin users to clients."""
    
    admin = models.ForeignKey(AdminUser, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(TgUser, on_delete=models.CASCADE, related_name='assignments')
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'admin_assignments'
        unique_together = [['admin', 'user']]
    
    def __str__(self):
        return f"{self.admin.username} assigned to {self.user}"


class UserAiProfile(models.Model):
    """AI-extracted profile data for users."""
    
    user = models.OneToOneField(TgUser, on_delete=models.CASCADE, related_name='ai_profile')
    extracted_data = models.TextField(default='{}')  # JSON
    pinned_data = models.TextField(default='[]')  # JSON list of {"label": "...", "value": "..."}
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_ai_profiles'
    
    def __str__(self):
        return f"AI Profile for {self.user}"
    
    def get_data(self):
        """Parse and return extracted data as dict."""
        try:
            return json.loads(self.extracted_data or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def get_pinned(self):
        """Parse and return pinned items as list of dicts with label/value."""
        try:
            data = json.loads(self.pinned_data or '[]')
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []


class AiReport(models.Model):
    """AI-generated business reports."""
    
    REPORT_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    period_start = models.CharField(max_length=20)
    period_end = models.CharField(max_length=20)
    stats = models.TextField(default='{}')  # JSON
    ai_conclusion = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'ai_reports'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_report_type_display()} Report - {self.period_start} to {self.period_end}"
    
    def get_stats(self):
        """Parse and return stats as dict."""
        try:
            return json.loads(self.stats or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}
