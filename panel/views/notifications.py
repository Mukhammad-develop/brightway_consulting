"""
Notifications System views for the admin panel.
Manages notifications for admin users.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST

from core.models import AdminUser, Notification
from ..decorators import login_required
from .helpers import session_ctx, get_current_admin


def create_notification(admin_user, title, message, link=None):
    """
    Helper function to create a notification for an admin user.
    
    Args:
        admin_user: AdminUser instance or admin_id (int)
        title: Notification title
        message: Notification message
        link: Optional URL link
    """
    if isinstance(admin_user, int):
        try:
            admin_user = AdminUser.objects.get(pk=admin_user)
        except AdminUser.DoesNotExist:
            return None
    
    if admin_user:
        return Notification.objects.create(
            admin_user=admin_user,
            title=title,
            message=message,
            link=link,
        )
    return None


def notify_masters(title, message, link=None, exclude_id=None):
    """
    Send notification to all master admin users.
    
    Args:
        title: Notification title
        message: Notification message
        link: Optional URL link
        exclude_id: Admin ID to exclude from notification
    """
    masters = AdminUser.objects.filter(role='master', is_active=True)
    if exclude_id:
        masters = masters.exclude(pk=exclude_id)
    
    for master in masters:
        create_notification(master, title, message, link)


def notify_user(admin_id, title, message, link=None):
    """
    Send notification to a specific admin user.
    
    Args:
        admin_id: AdminUser ID
        title: Notification title
        message: Notification message
        link: Optional URL link
    """
    return create_notification(admin_id, title, message, link)


def get_unread_count(admin_id):
    """Get count of unread notifications for an admin user."""
    if not admin_id:
        return 0
    return Notification.objects.filter(admin_user_id=admin_id, is_read=False).count()


@login_required
def notifications_list(request):
    """List all notifications for the current admin user."""
    admin_id = request.session.get('admin_id')
    
    if not admin_id:
        messages.info(request, 'Notifications are only available for database admin accounts.')
        return redirect('panel:dashboard')
    
    # Get filter
    filter_type = request.GET.get('filter', 'all')
    
    notifications = Notification.objects.filter(admin_user_id=admin_id)
    
    if filter_type == 'unread':
        notifications = notifications.filter(is_read=False)
    elif filter_type == 'read':
        notifications = notifications.filter(is_read=True)
    
    # Pagination
    page = int(request.GET.get('page', 1))
    per_page = 20
    total = notifications.count()
    notifications = notifications[(page - 1) * per_page:page * per_page]
    
    context = {
        'page_title': 'Notifications',
        'notifications': notifications,
        'filter_type': filter_type,
        'page': page,
        'total': total,
        'has_next': page * per_page < total,
        'has_prev': page > 1,
        **session_ctx(request),
    }
    return render(request, 'panel/notifications.html', context)


@login_required
def notification_create(request):
    """Create and send a notification."""
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient_id')
        title = request.POST.get('title', '').strip()
        message = request.POST.get('message', '').strip()
        link = request.POST.get('link', '').strip() or None
        send_to_all = request.POST.get('send_to_all') == 'on'
        
        if not title or not message:
            messages.error(request, 'Title and message are required.')
            return redirect('panel:notification_create')
        
        count = 0
        if send_to_all:
            # Send to all active admin users
            admins = AdminUser.objects.filter(is_active=True)
            for admin in admins:
                create_notification(admin, title, message, link)
                count += 1
            messages.success(request, f'Notification sent to {count} users.')
        elif recipient_id:
            # Send to specific user
            try:
                admin = AdminUser.objects.get(pk=recipient_id, is_active=True)
                create_notification(admin, title, message, link)
                messages.success(request, f'Notification sent to {admin.display_name or admin.username}.')
            except AdminUser.DoesNotExist:
                messages.error(request, 'Recipient not found.')
                return redirect('panel:notification_create')
        else:
            messages.error(request, 'Please select a recipient or check "Send to all".')
            return redirect('panel:notification_create')
        
        return redirect('panel:notifications')
    
    # GET - show form
    admins = AdminUser.objects.filter(is_active=True).order_by('username')
    
    context = {
        'page_title': 'Send Notification',
        'admins': admins,
        **session_ctx(request),
    }
    return render(request, 'panel/notification_form.html', context)


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    """Mark a single notification as read."""
    admin_id = request.session.get('admin_id')
    if not admin_id:
        return JsonResponse({'ok': False, 'error': 'No admin session'})
    
    try:
        notification = Notification.objects.get(pk=notification_id, admin_user_id=admin_id)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return JsonResponse({'ok': True})
    except Notification.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Notification not found'})


@login_required
@require_POST
def notification_mark_all_read(request):
    """Mark all notifications as read."""
    admin_id = request.session.get('admin_id')
    if not admin_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'No admin session'})
        messages.info(request, 'No notifications to mark.')
        return redirect('panel:notifications')
    
    Notification.objects.filter(admin_user_id=admin_id, is_read=False).update(is_read=True)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    
    messages.success(request, 'All notifications marked as read.')
    return redirect('panel:notifications')


@login_required
@require_POST
def notification_delete(request, notification_id):
    """Delete a notification."""
    admin_id = request.session.get('admin_id')
    if not admin_id:
        return JsonResponse({'ok': False, 'error': 'No admin session'})
    
    try:
        notification = Notification.objects.get(pk=notification_id, admin_user_id=admin_id)
        notification.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        messages.success(request, 'Notification deleted.')
    except Notification.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Notification not found'})
        messages.error(request, 'Notification not found.')
    
    return redirect('panel:notifications')


@login_required
def notification_preview(request):
    """Get latest notifications for dropdown preview."""
    admin_id = request.session.get('admin_id')
    if not admin_id:
        return JsonResponse({'items': []})
    
    notifications = Notification.objects.filter(admin_user_id=admin_id)[:5]
    
    items = []
    for n in notifications:
        items.append({
            'id': n.pk,
            'title': n.title,
            'message': n.message[:100] + '...' if len(n.message) > 100 else n.message,
            'is_read': n.is_read,
            'link': n.link,
            'created_at': n.created_at.isoformat(),
        })
    
    return JsonResponse({'items': items})


@login_required
@require_POST
def notification_mark_preview_read(request):
    """Mark preview notifications as read silently."""
    admin_id = request.session.get('admin_id')
    if not admin_id:
        return JsonResponse({'ok': False})
    
    # Mark last 5 unread as read
    Notification.objects.filter(
        admin_user_id=admin_id,
        is_read=False
    ).order_by('-created_at')[:5].update(is_read=True)
    
    return JsonResponse({'ok': True})
