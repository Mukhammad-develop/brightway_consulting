from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Send notifications when assigned consultant has not replied in 3h/10h."

    def handle(self, *args, **options):
        from core.models import Reminder, Notification, AdminUser

        now = datetime.now()
        due = Reminder.objects.select_related("case", "case__user", "case__assigned_to").filter(
            sent=False,
            reminder_type__in=["no_reply_3h", "no_reply_10h"],
            due_at__lte=now,
        )[:200]

        if not due:
            self.stdout.write("No due reminders.")
            return

        masters = list(AdminUser.objects.filter(role="master", is_active=True))

        sent_count = 0
        for r in due:
            case = r.case
            if not case:
                continue

            # Only for active assigned cases where AI is off (human should reply)
            if case.status != "active" or not case.assigned_to_id or getattr(case, "ai_enabled", True):
                r.sent = True
                r.save(update_fields=["sent"])
                continue

            last_user = getattr(case, "last_user_message_at", None)
            if not last_user:
                r.sent = True
                r.save(update_fields=["sent"])
                continue

            last_admin = getattr(case, "last_admin_message_at", None)
            if last_admin and last_admin >= last_user:
                r.sent = True
                r.save(update_fields=["sent"])
                continue

            hours = "3" if r.reminder_type == "no_reply_3h" else "10"
            title = f"No reply in {hours}h"
            user_label = case.user.username or case.user.first_name or str(case.user.telegram_id)
            msg = f"Client {user_label}: no consultant reply in {hours} hours (Case #{case.pk}, service {case.service})."
            link = f"/admin/users/{case.user.pk}"

            recipients = []
            if case.assigned_to and case.assigned_to.is_active:
                recipients.append(case.assigned_to)
            recipients.extend(masters)

            # De-dupe recipients
            uniq = {a.pk: a for a in recipients if a and a.pk}.values()

            with transaction.atomic():
                for admin in uniq:
                    Notification.objects.create(
                        admin_user=admin,
                        title=title,
                        message=msg,
                        link=link,
                    )
                r.sent = True
                r.save(update_fields=["sent"])

            sent_count += 1

        self.stdout.write(self.style.SUCCESS(f"Processed reminders: {sent_count}"))

