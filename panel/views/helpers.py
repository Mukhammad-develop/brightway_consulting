"""
Helper functions for the admin panel.
"""

import hashlib
import secrets
from datetime import datetime
from django.conf import settings


def hash_password(password):
    """
    Hash a password using SHA-256 with a salt.
    Returns the hash in format: salt$hash
    """
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((salt + password).encode())
    return f"{salt}${hash_obj.hexdigest()}"


def verify_password(stored_hash, password):
    """
    Verify a password against a stored hash.
    """
    if not stored_hash or '$' not in stored_hash:
        return False
    
    try:
        salt, hash_value = stored_hash.split('$', 1)
        hash_obj = hashlib.sha256((salt + password).encode())
        return hash_obj.hexdigest() == hash_value
    except (ValueError, AttributeError):
        return False


def check_admin_login(username, password):
    """
    Check admin login credentials.
    Returns tuple: (success, role, admin_id, display_name)
    
    Checks:
    1. .env master credentials first (returns admin_id=None)
    2. Database AdminUser records
    """
    from core.models import AdminUser
    
    # Check .env master credentials (ADMIN_* and MASTER2_*)
    for env_user, env_pass, display in [
        (getattr(settings, 'ADMIN_USERNAME', ''), getattr(settings, 'ADMIN_PASSWORD', ''), 'Master Admin'),
        (getattr(settings, 'MASTER2_USERNAME', ''), getattr(settings, 'MASTER2_PASSWORD', ''), getattr(settings, 'MASTER2_DISPLAY', 'Master Admin')),
    ]:
        if env_user and username == env_user and password == env_pass:
            return (True, 'master', None, display)
    
    # Check database AdminUser
    try:
        admin = AdminUser.objects.get(username=username, is_active=True)
        if verify_password(admin.password_hash, password):
            # Update last login
            admin.last_login = datetime.now()
            admin.save(update_fields=['last_login'])
            return (True, admin.role, admin.pk, admin.display_name or admin.username)
    except AdminUser.DoesNotExist:
        pass
    
    return (False, None, None, None)


def get_current_admin(request):
    """
    Get the current admin user from session.
    Returns AdminUser instance or None.
    """
    from core.models import AdminUser
    
    admin_id = request.session.get('admin_id')
    if admin_id:
        try:
            return AdminUser.objects.get(pk=admin_id, is_active=True)
        except AdminUser.DoesNotExist:
            pass
    return None


def is_master(request):
    """Check if current user is a master admin."""
    return request.session.get('admin_role') == 'master'


def is_elevated(request):
    """Check if current user is master or admin (elevated privileges)."""
    return request.session.get('admin_role') in ('master', 'admin')


def get_unread_notification_count(admin_id):
    """Get count of unread notifications for an admin user."""
    if not admin_id:
        return 0
    from core.models import Notification
    return Notification.objects.filter(admin_user_id=admin_id, is_read=False).count()


def session_ctx(request):
    """
    Get session context for templates.
    Ensures theme is in session (load from AdminUser if DB admin and missing).
    """
    admin_id = request.session.get('admin_id')
    # Sync theme from DB if we have admin_id but no theme in session
    if admin_id and 'theme_mode' not in request.session:
        try:
            from core.models import AdminUser
            a = AdminUser.objects.get(pk=admin_id, is_active=True)
            request.session['theme_mode'] = getattr(a, 'theme_mode', 'dark')
            request.session['theme_dark'] = getattr(a, 'theme_dark', 'blue')
            request.session['theme_light'] = getattr(a, 'theme_light', 'blue')
        except Exception:
            request.session.setdefault('theme_mode', 'dark')
            request.session.setdefault('theme_dark', 'blue')
            request.session.setdefault('theme_light', 'blue')
    theme_mode = request.session.get('theme_mode', 'dark')
    theme_name = request.session.get('theme_dark', 'blue') if theme_mode == 'dark' else request.session.get('theme_light', 'blue')
    return {
        'session_admin_logged_in': request.session.get('admin_logged_in', False),
        'session_admin_username': request.session.get('admin_username', ''),
        'session_admin_role': request.session.get('admin_role', ''),
        'session_admin_display': request.session.get('admin_display', ''),
        'session_admin_id': admin_id,
        'is_master': is_master(request),
        'is_elevated': is_elevated(request),
        'unread_notifications': get_unread_notification_count(admin_id),
        'theme_mode': theme_mode,
        'theme_name': theme_name,
    }


def get_file_refs_for_conversation(case, conversation):
    """Build uid -> {id, filename, media_type} for [FILE:uid:filename:type] in conversation."""
    from core.models import Document
    refs = {}
    if not case:
        return refs
    for msg in (conversation or []):
        content = (msg.get('content') or '').strip()
        if not content.startswith('[FILE:') or not content.endswith(']'):
            continue
        try:
            parts = content[6:-1].split(':')
            if len(parts) >= 3:
                uid = parts[0]
                if uid in refs:
                    continue
                doc = (
                    Document.objects.filter(case=case, file_path__contains=uid).first()
                    or Document.objects.filter(case=case, file_unique_id__contains=uid).first()
                )
                if doc:
                    refs[uid] = {
                        'id': doc.pk,
                        'filename': doc.display_name or doc.file_path or parts[1],
                        'media_type': doc.media_type or parts[2],
                    }
        except Exception:
            pass
    return refs


def build_conversation_display(conversation, file_refs):
    """Add file_info to each message that is a [FILE:...] reference."""
    display = []
    for msg in (conversation or []):
        content = (msg.get('content') or '').strip()
        item = {**msg, 'content': content, 'file_info': None}
        if content.startswith('[FILE:') and content.endswith(']'):
            try:
                parts = content[6:-1].split(':')
                if len(parts) >= 3:
                    item['file_info'] = file_refs.get(parts[0])
                    if item['file_info']:
                        item['file_filename'] = item['file_info'].get('filename') or parts[1]
                        item['file_media_type'] = item['file_info'].get('media_type') or parts[2]
            except Exception:
                pass
        display.append(item)
    return display
