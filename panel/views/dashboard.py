"""
Dashboard view for the admin panel.
"""

from django.shortcuts import render
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from datetime import datetime, timedelta

from core.models import TgUser, Case, Document, Payment
from ..decorators import login_required
from .helpers import session_ctx


def get_ai_stats():
    """Get AI usage statistics from the bot services module."""
    try:
        from bot.services import get_ai_usage_stats
        return get_ai_usage_stats()
    except Exception as e:
        return {
            'api_calls_today': 0,
            'total_tokens_today': 0,
            'errors_today': 0,
            'avg_response_time': 0,
            'error_rate': 0,
        }


@login_required
def dashboard(request):
    """
    Main dashboard view.
    Shows overview of cases, users, revenue, recent activity, and AI usage.
    """
    context = session_ctx(request)
    
    # Get real statistics
    total_users = TgUser.objects.count()
    total_cases = Case.objects.count()
    active_cases = Case.objects.filter(status='active').count()
    
    # Calculate total revenue from payments
    total_revenue = Payment.objects.aggregate(total=Sum('amount'))['total'] or 0
    
    # Cases by status for chart
    cases_by_status = {
        'pending': Case.objects.filter(payment_status='pending').count(),
        'active': active_cases,
        'completed': Case.objects.filter(status='completed').count(),
    }
    
    # Cases by service type
    cases_by_service = Case.objects.values('service').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Revenue by month (last 6 months)
    six_months_ago = datetime.now() - timedelta(days=180)
    revenue_by_month = Payment.objects.filter(
        payment_date__gte=six_months_ago
    ).annotate(
        month=TruncMonth('payment_date')
    ).values('month').annotate(
        total=Sum('amount')
    ).order_by('month')
    
    # Recent users (last 10)
    recent_users = TgUser.objects.order_by('-created_at')[:10]
    
    # Recent cases (last 10)
    recent_cases = Case.objects.select_related('user').order_by('-created_at')[:10]
    
    # Service display names for the chart
    service_labels = {
        'student': 'Student Visa',
        'paye': 'PAYE Refund',
        'self': 'Self Assessment',
        'company': 'Company Accounting',
        'general': 'General Inquiry',
    }
    
    # Prepare cases by service with labels and percentages
    total_for_pct = max(total_cases, 1)  # Avoid division by zero
    cases_service_chart = []
    for item in cases_by_service:
        pct = int((item['count'] / total_for_pct) * 100)
        cases_service_chart.append({
            'service': item['service'],
            'label': service_labels.get(item['service'], item['service'].title()),
            'count': item['count'],
            'pct': pct,
        })
    
    # Get AI usage statistics
    ai_stats = get_ai_stats()
    
    # Documents with transcriptions count
    transcribed_docs = Document.objects.exclude(
        transcription__isnull=True
    ).exclude(transcription='').count()
    
    context.update({
        'page_title': 'Dashboard',
        'total_users': total_users,
        'total_cases': total_cases,
        'active_cases': active_cases,
        'total_revenue': total_revenue,
        'cases_by_status': cases_by_status,
        'cases_service_chart': cases_service_chart,
        'revenue_by_month': list(revenue_by_month),
        'recent_users': recent_users,
        'recent_cases': recent_cases,
        'ai_stats': ai_stats,
        'transcribed_docs': transcribed_docs,
    })
    
    return render(request, 'panel/dashboard.html', context)
