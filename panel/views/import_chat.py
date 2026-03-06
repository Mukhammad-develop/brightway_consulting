"""
Import Chat views for the admin panel.
Allows importing chat history from Telegram via userbot.
"""

import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from core.models import ImportRequest, TgUser
from ..decorators import login_required, elevated_required
from .helpers import session_ctx


@login_required
@elevated_required
def import_chat_list(request):
    """
    View import chat queue and history.
    """
    context = session_ctx(request)
    
    if request.method == 'POST':
        # Queue new import
        tg_id = request.POST.get('tg_id', '').strip()
        label = request.POST.get('label', '').strip() or None
        
        if not tg_id:
            messages.error(request, 'Telegram ID is required.')
            return redirect('panel:import_chat')
        
        # Create import request
        ImportRequest.objects.create(
            user_tg_id=tg_id,
            label=label,
            status='pending'
        )
        
        messages.success(request, f'Import request queued for {tg_id}')
        return redirect('panel:import_chat')
    
    # Get import history
    imports = ImportRequest.objects.all().order_by('-created_at')
    
    # Pagination
    paginator = Paginator(imports, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Check for pending imports (for polling)
    pending_ids = list(
        ImportRequest.objects.filter(status__in=['pending', 'processing'])
        .values_list('pk', flat=True)
    )
    
    context.update({
        'page_title': 'Import Chat History',
        'page_obj': page_obj,
        'pending_ids': json.dumps(pending_ids),
    })
    
    return render(request, 'panel/import_chat.html', context)


@login_required
@elevated_required
def import_status(request, import_id):
    """
    Get status of an import request (for polling).
    """
    try:
        req = ImportRequest.objects.get(pk=import_id)
        return JsonResponse({
            'id': req.pk,
            'status': req.status,
            'message_count': req.message_count,
            'error_msg': req.error_msg,
            'completed_at': req.completed_at.isoformat() if req.completed_at else None,
        })
    except ImportRequest.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
@elevated_required
@require_POST
def import_cancel(request, import_id):
    """
    Cancel a pending import request.
    """
    try:
        req = ImportRequest.objects.get(pk=import_id)
        
        if req.status == 'pending':
            req.delete()
            messages.success(request, 'Import request cancelled.')
        else:
            messages.error(request, 'Cannot cancel import that is already processing.')
        
    except ImportRequest.DoesNotExist:
        messages.error(request, 'Import request not found.')
    
    return redirect('panel:import_chat')


@login_required
@elevated_required
@require_POST
def import_delete(request, import_id):
    """
    Delete an import request from history.
    """
    try:
        req = ImportRequest.objects.get(pk=import_id)
        req.delete()
        messages.success(request, 'Import record deleted.')
    except ImportRequest.DoesNotExist:
        messages.error(request, 'Import request not found.')
    
    return redirect('panel:import_chat')
