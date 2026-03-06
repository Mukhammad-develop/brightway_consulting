"""
Case management views for the admin panel.
"""

import json
from datetime import datetime
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q

from django.http import JsonResponse

from core.models import TgUser, Case, Document, Payment, ServiceDefinition, AdminAssignment, ImportRequest
from ..decorators import login_required, elevated_required
from .helpers import session_ctx, get_file_refs_for_conversation, build_conversation_display, get_current_admin, is_elevated


def get_service_choices():
    """Get service choices from ServiceDefinition or defaults."""
    services = ServiceDefinition.objects.filter(is_active=True).order_by('display_order')
    if services.exists():
        return [(s.slug, s.name) for s in services]
    return Case.SERVICE_CHOICES


@login_required
def cases_list(request):
    """
    List all cases with search, filter, and pagination.
    """
    context = session_ctx(request)
    
    # Get all cases with related user
    cases = Case.objects.select_related('user').order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        cases = cases.filter(
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(service__icontains=search_query) |
            Q(notes__icontains=search_query)
        )
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        cases = cases.filter(status=status_filter)
    
    # Filter by payment status
    payment_filter = request.GET.get('payment_status', '')
    if payment_filter:
        cases = cases.filter(payment_status=payment_filter)
    
    # Filter by service
    service_filter = request.GET.get('service', '')
    if service_filter:
        cases = cases.filter(service=service_filter)
    
    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    valid_sorts = ['created_at', '-created_at', 'updated_at', '-updated_at',
                   'service', '-service', 'status', '-status']
    if sort_by in valid_sorts:
        cases = cases.order_by(sort_by)
    else:
        cases = cases.order_by('-created_at')
    
    # Pagination (20 per page)
    paginator = Paginator(cases, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context.update({
        'page_title': 'Cases',
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'payment_filter': payment_filter,
        'service_filter': service_filter,
        'sort_by': sort_by,
        'total_count': paginator.count,
        'status_choices': Case.STATUS_CHOICES,
        'payment_choices': Case.PAYMENT_STATUS_CHOICES,
        'service_choices': get_service_choices(),
    })
    
    return render(request, 'panel/cases_list.html', context)


@login_required
def case_detail(request, case_id):
    """
    View case details including conversation history, documents, and payments.
    """
    context = session_ctx(request)
    
    case = get_object_or_404(Case.objects.select_related('user'), pk=case_id)
    
    # Get case documents
    documents = Document.objects.filter(case=case).order_by('-uploaded_at')
    
    # Get payment history
    payments = Payment.objects.filter(case=case).order_by('-payment_date')
    
    # Get conversation history with file refs for View/Download
    conversation = case.get_conversation()
    file_refs = get_file_refs_for_conversation(case, conversation)
    conversation_display = build_conversation_display(conversation, file_refs)
    
    # Get service display name
    service_display = dict(Case.SERVICE_CHOICES).get(case.service, case.service)
    
    context.update({
        'page_title': f'Case #{case.pk}',
        'case': case,
        'documents': documents,
        'payments': payments,
        'conversation': conversation_display,
        'service_display': service_display,
        'status_choices': Case.STATUS_CHOICES,
        'payment_choices': Case.PAYMENT_STATUS_CHOICES,
    })
    
    return render(request, 'panel/case_detail.html', context)


@login_required
def case_add(request):
    """
    Add a new case.
    """
    context = session_ctx(request)
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id', '').strip()
        service = request.POST.get('service', 'general')
        status = request.POST.get('status', 'active')
        payment_status = request.POST.get('payment_status', 'pending')
        total_amount = request.POST.get('total_amount', '0')
        paid_amount = request.POST.get('paid_amount', '0')
        currency = request.POST.get('currency', 'GBP')
        notes = request.POST.get('notes', '').strip() or None
        
        # Validation
        if not user_id:
            messages.error(request, 'User is required.')
            return render(request, 'panel/case_form.html', context)
        
        try:
            user = TgUser.objects.get(pk=user_id)
        except TgUser.DoesNotExist:
            messages.error(request, 'Selected user does not exist.')
            return render(request, 'panel/case_form.html', context)
        
        try:
            total_amount = Decimal(total_amount)
            paid_amount = Decimal(paid_amount)
        except:
            messages.error(request, 'Invalid amount values.')
            return render(request, 'panel/case_form.html', context)
        
        # Create case
        case = Case.objects.create(
            user=user,
            service=service,
            status=status,
            payment_status=payment_status,
            total_amount=total_amount,
            paid_amount=paid_amount,
            currency=currency,
            notes=notes,
        )
        
        messages.success(request, f'Case #{case.pk} created successfully.')
        return redirect('panel:case_detail', case_id=case.pk)
    
    # Get users for dropdown
    users = TgUser.objects.order_by('-created_at')[:100]
    
    context.update({
        'page_title': 'Add Case',
        'form_action': 'add',
        'users': users,
        'service_choices': get_service_choices(),
        'status_choices': Case.STATUS_CHOICES,
        'payment_choices': Case.PAYMENT_STATUS_CHOICES,
    })
    
    return render(request, 'panel/case_form.html', context)


@login_required
def case_edit(request, case_id):
    """
    Edit an existing case.
    """
    context = session_ctx(request)
    
    case = get_object_or_404(Case.objects.select_related('user'), pk=case_id)
    
    if request.method == 'POST':
        service = request.POST.get('service', case.service)
        status = request.POST.get('status', case.status)
        payment_status = request.POST.get('payment_status', case.payment_status)
        total_amount = request.POST.get('total_amount', str(case.total_amount))
        paid_amount = request.POST.get('paid_amount', str(case.paid_amount))
        currency = request.POST.get('currency', case.currency)
        notes = request.POST.get('notes', '').strip() or None
        
        try:
            total_amount = Decimal(total_amount)
            paid_amount = Decimal(paid_amount)
        except:
            messages.error(request, 'Invalid amount values.')
            return render(request, 'panel/case_form.html', context)
        
        # Update case
        case.service = service
        case.status = status
        case.payment_status = payment_status
        case.total_amount = total_amount
        case.paid_amount = paid_amount
        case.currency = currency
        case.notes = notes
        case.save()
        
        messages.success(request, f'Case #{case.pk} updated successfully.')
        return redirect('panel:case_detail', case_id=case.pk)
    
    context.update({
        'page_title': f'Edit Case #{case.pk}',
        'form_action': 'edit',
        'case': case,
        'service_choices': get_service_choices(),
        'status_choices': Case.STATUS_CHOICES,
        'payment_choices': Case.PAYMENT_STATUS_CHOICES,
    })
    
    return render(request, 'panel/case_form.html', context)


@login_required
def case_update(request, case_id):
    """
    Quick update case status and payment status.
    """
    if request.method != 'POST':
        return redirect('panel:case_detail', case_id=case_id)
    
    case = get_object_or_404(Case, pk=case_id)
    
    status = request.POST.get('status')
    payment_status = request.POST.get('payment_status')
    
    if status:
        case.status = status
    if payment_status:
        case.payment_status = payment_status
    
    case.save()
    
    messages.success(request, f'Case #{case.pk} updated successfully.')
    return redirect('panel:case_detail', case_id=case.pk)


def _consultant_can_access_case(request, case):
    """Consultants may only toggle AI for cases of assigned users."""
    if is_elevated(request):
        return True
    admin = get_current_admin(request)
    if not admin:
        return False
    return AdminAssignment.objects.filter(admin=admin, user=case.user).exists()


@login_required
def case_toggle_ai(request, case_id):
    """
    Toggle AI on/off for a case. POST only. Returns JSON { ok, ai_enabled }.
    """
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed'}, status=405)
    case = get_object_or_404(Case.objects.select_related('user'), pk=case_id)
    if not _consultant_can_access_case(request, case):
        return JsonResponse({'ok': False, 'error': 'Access denied'}, status=403)
    case.ai_enabled = not case.ai_enabled
    case.save(update_fields=['ai_enabled'])
    return JsonResponse({'ok': True, 'ai_enabled': case.ai_enabled})


@login_required
@elevated_required
def case_reimport_chat(request, case_id):
    """
    Queue re-import of chat for this case's user. Replaces conversation on the active case when userbot runs.
    """
    case = get_object_or_404(Case.objects.select_related('user'), pk=case_id)
    if not _consultant_can_access_case(request, case):
        messages.error(request, 'Access denied.')
        return redirect('panel:cases_list')
    ImportRequest.objects.create(
        user_tg_id=str(case.user.telegram_id),
        label=f"Re-import Case #{case.pk}",
        status='pending'
    )
    messages.success(request, f'Re-import queued for user {case.user.telegram_id}. Go to Import Chat to see status.')
    return redirect('panel:import_chat')
