"""
User management views for the admin panel.
Includes client notes functionality.
"""

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.views.decorators.http import require_POST

from core.models import TgUser, Case, Document, UserAiProfile, ClientNote, AdminUser, AdminAssignment
from ..decorators import login_required
from .helpers import session_ctx, get_current_admin, is_elevated, get_file_refs_for_conversation, build_conversation_display


def _consultant_can_access_user(request, target_user):
    """If current user is a consultant, they may only access assigned users."""
    if is_elevated(request):
        return True
    admin = get_current_admin(request)
    if not admin:
        return False
    return AdminAssignment.objects.filter(admin=admin, user=target_user).exists()


@login_required
def users_list(request):
    """
    List all users with search, filter, and pagination.
    """
    context = session_ctx(request)
    
    # Get all users
    users = TgUser.objects.annotate(
        cases_count=Count('cases'),
        docs_count=Count('cases__documents')
    )
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(telegram_id__icontains=search_query)
        )
    
    # Filter by language (case-insensitive: dropdown uses normalized code)
    language_filter = request.GET.get('language', '').strip()
    if language_filter:
        users = users.filter(language_code__iexact=language_filter)
    
    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    valid_sorts = ['created_at', '-created_at', 'username', '-username', 
                   'telegram_id', '-telegram_id', 'first_name', '-first_name']
    if sort_by in valid_sorts:
        users = users.order_by(sort_by)
    else:
        users = users.order_by('-created_at')
    
    # Pagination (20 per page)
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Unique languages for filter (dedupe: same language can appear multiple times in DB)
    raw_langs = TgUser.objects.exclude(
        language_code__isnull=True
    ).exclude(
        language_code=''
    ).values_list('language_code', flat=True).distinct()
    seen = set()
    languages = []
    for code in sorted(raw_langs, key=lambda x: (x or '').lower()):
        key = (code or '').strip().lower()
        if key and key not in seen:
            seen.add(key)
            languages.append(key)
    
    context.update({
        'page_title': 'Users',
        'page_obj': page_obj,
        'search_query': search_query,
        'language_filter': language_filter,
        'sort_by': sort_by,
        'languages': languages,
        'total_count': paginator.count,
    })
    
    return render(request, 'panel/users_list.html', context)


@login_required
def my_clients(request):
    """
    List clients assigned to the current consultant.
    Consultants see only their assigned users; masters/admins see the same list when visiting this page.
    """
    context = session_ctx(request)
    admin = get_current_admin(request)
    if not admin:
        return redirect('panel:login')
    assignments = AdminAssignment.objects.filter(admin=admin).select_related('user').order_by('-assigned_at')
    # Annotate with last case update for sorting
    from django.db.models import Max
    client_list = []
    for a in assignments:
        last_updated = Case.objects.filter(user=a.user).aggregate(Max('updated_at'))['updated_at__max']
        client_list.append({'assignment': a, 'user': a.user, 'last_updated': last_updated})
    client_list.sort(key=lambda x: x['last_updated'] or x['assignment'].assigned_at, reverse=True)
    context.update({
        'page_title': 'My Clients',
        'client_list': client_list,
    })
    return render(request, 'panel/my_clients.html', context)


@login_required
def user_detail(request, user_id):
    """
    View user profile with all details, cases, documents, and notes.
    Consultants can only view their assigned users.
    """
    context = session_ctx(request)
    
    user = get_object_or_404(TgUser, pk=user_id)
    if not _consultant_can_access_user(request, user):
        messages.error(request, 'You can only view clients assigned to you.')
        return redirect('panel:my_clients')
    
    # Get user's cases
    cases = Case.objects.filter(user=user).order_by('-created_at')
    
    # Get user's documents
    documents = Document.objects.filter(case__user=user).order_by('-uploaded_at')
    
    # Get AI profile data if exists
    ai_profile = None
    ai_data = {}
    try:
        ai_profile = UserAiProfile.objects.get(user=user)
        ai_data = ai_profile.get_data()
    except UserAiProfile.DoesNotExist:
        pass
    
    # Parse profile data
    profile_data = user.get_profile_data()
    
    # Get client notes (pinned first, then by date)
    notes = ClientNote.objects.filter(user=user).order_by('-is_pinned', '-created_at')
    
    # Active case and conversation for chat/reply
    active_case = Case.objects.filter(user=user, status='active').order_by('-updated_at').first()
    conversation = active_case.get_conversation() if active_case else []
    file_refs = get_file_refs_for_conversation(active_case, conversation)
    conversation_display = build_conversation_display(conversation, file_refs)
    
    # Get current admin for permission checks
    current_admin = get_current_admin(request)
    current_admin_id = request.session.get('admin_id')
    
    context.update({
        'page_title': f'User: {user.username or user.telegram_id}',
        'user_obj': user,
        'cases': cases,
        'documents': documents,
        'ai_profile': ai_profile,
        'ai_data': ai_data,
        'profile_data': profile_data,
        'notes': notes,
        'current_admin_id': current_admin_id,
        'active_case': active_case,
        'conversation': conversation_display,
    })
    
    return render(request, 'panel/user_detail.html', context)


@login_required
def user_add(request):
    """
    Add a new user.
    """
    context = session_ctx(request)
    
    if request.method == 'POST':
        telegram_id = request.POST.get('telegram_id', '').strip()
        username = request.POST.get('username', '').strip() or None
        first_name = request.POST.get('first_name', '').strip() or None
        last_name = request.POST.get('last_name', '').strip() or None
        phone = request.POST.get('phone', '').strip() or None
        language_code = request.POST.get('language_code', 'en')
        
        # Validation
        if not telegram_id:
            messages.error(request, 'Telegram ID is required.')
            return render(request, 'panel/user_form.html', context)
        
        try:
            telegram_id = int(telegram_id)
        except ValueError:
            messages.error(request, 'Telegram ID must be a number.')
            return render(request, 'panel/user_form.html', context)
        
        # Check if user already exists
        if TgUser.objects.filter(telegram_id=telegram_id).exists():
            messages.error(request, 'A user with this Telegram ID already exists.')
            return render(request, 'panel/user_form.html', context)
        
        # Create user
        user = TgUser.objects.create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            language_code=language_code,
        )
        
        # Queue chat import so userbot will fetch history, analyze with AI, and set AI off if they chatted before
        from core.models import ImportRequest
        ImportRequest.objects.create(
            user_tg_id=str(telegram_id),
            label=f'Add user: {username or first_name or str(telegram_id)}',
            status='pending'
        )
        
        messages.success(request, f'User {user} created successfully. Chat import has been queued—history will be imported and analyzed when the userbot runs.')
        return redirect('panel:user_detail', user_id=user.pk)
    
    context.update({
        'page_title': 'Add User',
        'form_action': 'add',
    })
    
    return render(request, 'panel/user_form.html', context)


@login_required
def user_edit(request, user_id):
    """
    Edit an existing user.
    """
    context = session_ctx(request)
    
    user = get_object_or_404(TgUser, pk=user_id)
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip() or None
        first_name = request.POST.get('first_name', '').strip() or None
        last_name = request.POST.get('last_name', '').strip() or None
        phone = request.POST.get('phone', '').strip() or None
        language_code = request.POST.get('language_code', 'en')
        
        # Update user
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.phone = phone
        user.language_code = language_code
        user.save()
        
        messages.success(request, f'User {user} updated successfully.')
        return redirect('panel:user_detail', user_id=user.pk)
    
    context.update({
        'page_title': f'Edit User: {user.username or user.telegram_id}',
        'form_action': 'edit',
        'user_obj': user,
    })
    
    return render(request, 'panel/user_form.html', context)




# =============================================================================
# CLIENT NOTES FUNCTIONALITY
# =============================================================================

@login_required
@require_POST
def note_add(request, user_id):
    """Add a new note for a user."""
    user = get_object_or_404(TgUser, pk=user_id)
    
    note_text = request.POST.get('note_text', '').strip()
    is_pinned = request.POST.get('is_pinned') == 'on'
    
    if not note_text:
        messages.error(request, 'Note content is required.')
        return redirect('panel:user_detail', user_id=user_id)
    
    # Get current admin
    admin_id = request.session.get('admin_id')
    admin_user = None
    author_name = request.session.get('admin_display', 'Admin')
    
    if admin_id:
        try:
            admin_user = AdminUser.objects.get(pk=admin_id)
            author_name = admin_user.display_name or admin_user.username
        except AdminUser.DoesNotExist:
            pass
    
    # Create the note
    ClientNote.objects.create(
        user=user,
        admin_user=admin_user,
        author_name=author_name,
        note_text=note_text,
        is_pinned=is_pinned,
    )
    
    messages.success(request, 'Note added successfully.')
    return redirect('panel:user_detail', user_id=user_id)


@login_required
@require_POST
def note_edit(request, user_id, note_id):
    """Edit an existing note."""
    user = get_object_or_404(TgUser, pk=user_id)
    note = get_object_or_404(ClientNote, pk=note_id, user=user)
    
    # Check permission: only author or master/admin can edit
    admin_id = request.session.get('admin_id')
    admin_role = request.session.get('admin_role', '')
    
    can_edit = (
        admin_role in ('master', 'admin') or
        (note.admin_user and note.admin_user.pk == admin_id) or
        (not note.admin_user and admin_id is None)  # .env master created note
    )
    
    if not can_edit:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Permission denied'})
        messages.error(request, 'You do not have permission to edit this note.')
        return redirect('panel:user_detail', user_id=user_id)
    
    note_text = request.POST.get('note_text', '').strip()
    is_pinned = request.POST.get('is_pinned') == 'on'
    
    if not note_text:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Note content is required'})
        messages.error(request, 'Note content is required.')
        return redirect('panel:user_detail', user_id=user_id)
    
    note.note_text = note_text
    note.is_pinned = is_pinned
    note.save()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'note_text': note.note_text,
            'is_pinned': note.is_pinned,
            'updated_at': note.updated_at.isoformat(),
        })
    
    messages.success(request, 'Note updated successfully.')
    return redirect('panel:user_detail', user_id=user_id)


@login_required
@require_POST
def note_delete(request, user_id, note_id):
    """Delete a note."""
    user = get_object_or_404(TgUser, pk=user_id)
    note = get_object_or_404(ClientNote, pk=note_id, user=user)
    
    # Check permission: only author or master/admin can delete
    admin_id = request.session.get('admin_id')
    admin_role = request.session.get('admin_role', '')
    
    can_delete = (
        admin_role in ('master', 'admin') or
        (note.admin_user and note.admin_user.pk == admin_id) or
        (not note.admin_user and admin_id is None)
    )
    
    if not can_delete:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Permission denied'})
        messages.error(request, 'You do not have permission to delete this note.')
        return redirect('panel:user_detail', user_id=user_id)
    
    note.delete()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    
    messages.success(request, 'Note deleted successfully.')
    return redirect('panel:user_detail', user_id=user_id)


@login_required
@require_POST
def note_toggle_pin(request, user_id, note_id):
    """Toggle the pinned status of a note."""
    user = get_object_or_404(TgUser, pk=user_id)
    note = get_object_or_404(ClientNote, pk=note_id, user=user)
    
    note.is_pinned = not note.is_pinned
    note.save(update_fields=['is_pinned'])
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'is_pinned': note.is_pinned})
    
    status = 'pinned' if note.is_pinned else 'unpinned'
    messages.success(request, f'Note {status}.')
    return redirect('panel:user_detail', user_id=user_id)


# =============================================================================
# TELEGRAM BOT MESSAGING FUNCTIONALITY
# =============================================================================

@login_required
@require_POST
def send_message(request, user_id):
    """
    Send a message to a user via the bot.
    Consultants can only send to their assigned users.
    """
    from core.models import PendingSend
    from datetime import datetime
    
    user = get_object_or_404(TgUser, pk=user_id)
    if not _consultant_can_access_user(request, user):
        return JsonResponse({'ok': False, 'error': 'You can only message clients assigned to you.'}, status=403)
    
    # Get message from request body (JSON)
    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()
    except (json.JSONDecodeError, ValueError):
        text = request.POST.get('text', '').strip()
    
    if not text:
        return JsonResponse({'ok': False, 'error': 'Message text is required'})
    
    # Get sender name
    sender_name = request.session.get('admin_display', 'Admin')
    
    # Get the account to use (based on user's linked_account)
    account_index = user.linked_account or 0
    
    # Create pending send record for the userbot to pick up
    pending = PendingSend.objects.create(
        user_tg_id=str(user.telegram_id),
        message=text,
        sender_name=sender_name,
        account_index=account_index
    )
    
    # Also try to send directly via bot
    bot_sent = False
    try:
        from bot.bot import send_message_to_user
        bot_sent = send_message_to_user(user.telegram_id, text, sender_name)
        
        if bot_sent:
            # Mark pending as sent if bot succeeded
            pending.sent = True
            pending.sent_at = datetime.now()
            pending.save(update_fields=['sent', 'sent_at'])
    except Exception as e:
        # Bot not available, userbot will handle it
        pass
    
    # Add to conversation history
    active_case = Case.objects.filter(user=user, status='active').first()
    if active_case:
        active_case.add_message('admin', text, sender_name)
    
    return JsonResponse({
        'ok': True,
        'tg_sent': bot_sent,
        'timestamp': datetime.now().isoformat(),
        'sender': sender_name,
    })


@login_required
def poll_messages(request, user_id):
    """
    Poll for new messages since a given timestamp.
    Consultants can only poll for their assigned users.
    """
    user = get_object_or_404(TgUser, pk=user_id)
    if not _consultant_can_access_user(request, user):
        return JsonResponse({'messages': [], 'file_docs': {}}, status=403)
    
    since = request.GET.get('since', '')
    
    # Collect all messages across all cases
    all_messages = []
    file_docs = {}
    
    for case in Case.objects.filter(user=user).order_by('created_at'):
        conversation = case.get_conversation()
        
        for msg in conversation:
            timestamp = msg.get('timestamp', '')
            
            # Filter by since if provided
            if since and timestamp and timestamp <= since:
                continue
            
            all_messages.append(msg)
            
            # Check for file references
            content = msg.get('content', '')
            if content.startswith('[FILE:'):
                try:
                    parts = content[6:-1].split(':')
                    if len(parts) >= 3:
                        uid, filename, media_type = parts[0], parts[1], parts[2]
                        if uid in file_docs:
                            continue
                        doc = (
                            Document.objects.filter(case=case, file_path__contains=uid).first()
                            or Document.objects.filter(case=case, file_unique_id__contains=uid).first()
                        )
                        if doc:
                            file_docs[uid] = {
                                'id': doc.pk,
                                'file_id': doc.telegram_file_id,
                                'filename': doc.display_name or doc.file_path or filename,
                                'media_type': doc.media_type or media_type,
                                'transcription': doc.transcription,
                            }
                except Exception:
                    pass
    
    # Sort by timestamp
    all_messages.sort(key=lambda x: x.get('timestamp', ''))
    
    return JsonResponse({
        'messages': all_messages,
        'file_docs': file_docs,
    })
