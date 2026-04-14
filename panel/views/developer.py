"""
Developer page — master-admin view showing all bot conversations for debugging.
"""

from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Q, Max

from core.models import Case
from ..decorators import master_required
from .helpers import session_ctx, get_file_refs_for_conversation, build_conversation_display


@master_required
def developer_view(request):
    context = session_ctx(request)

    # Filters
    ai_filter = request.GET.get('ai', '').strip()
    service_filter = request.GET.get('service', '').strip()
    search_query = request.GET.get('search', '').strip()

    cases = Case.objects.select_related('user', 'assigned_to', 'service_definition').all()

    if ai_filter == 'on':
        cases = cases.filter(ai_enabled=True)
    elif ai_filter == 'off':
        cases = cases.filter(ai_enabled=False)

    if service_filter:
        cases = cases.filter(service=service_filter)

    if search_query:
        cases = cases.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__telegram_id__icontains=search_query)
        )

    cases = cases.order_by('-updated_at', '-created_at')

    # Collect distinct services for the filter dropdown
    services = (
        Case.objects.exclude(service='')
        .exclude(service__isnull=True)
        .values_list('service', flat=True)
        .distinct()
        .order_by('service')
    )

    paginator = Paginator(cases, 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # Build conversation display for each case on this page
    cases_data = []
    for case in page_obj:
        conversation = case.get_conversation()
        file_refs = get_file_refs_for_conversation(case, conversation)
        messages_display = build_conversation_display(conversation, file_refs)
        cases_data.append({
            'case': case,
            'messages': messages_display,
            'msg_count': len(conversation),
        })

    context.update({
        'page_title': 'Developer',
        'page_obj': page_obj,
        'cases_data': cases_data,
        'ai_filter': ai_filter,
        'service_filter': service_filter,
        'search_query': search_query,
        'services': list(services),
        'total_count': paginator.count,
    })
    return render(request, 'panel/developer.html', context)
