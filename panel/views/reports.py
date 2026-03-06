"""
Reporting System views for the admin panel.
Generates and displays business reports with AI-driven insights.
"""

import json
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count

from core.models import TgUser, Case, Document, Payment, AiReport
from ..decorators import login_required, elevated_required
from .helpers import session_ctx


def compute_stats(start_date, end_date):
    """
    Compute statistics for a given period.
    Returns a dict with various metrics.
    """
    # New users in period
    new_users = TgUser.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    ).count()
    
    # Cases stats
    new_cases = Case.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    ).count()
    
    completed_cases = Case.objects.filter(
        status='completed',
        updated_at__gte=start_date,
        updated_at__lte=end_date
    ).count()
    
    active_cases = Case.objects.filter(status='active').count()
    
    # Payment stats
    paid_cases = Case.objects.filter(
        payment_status='received',
        updated_at__gte=start_date,
        updated_at__lte=end_date
    ).count()
    
    total_revenue = Payment.objects.filter(
        payment_date__gte=start_date,
        payment_date__lte=end_date,
        status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Documents uploaded
    docs_uploaded = Document.objects.filter(
        uploaded_at__gte=start_date,
        uploaded_at__lte=end_date
    ).count()
    
    # Cases by service
    by_service = {}
    service_counts = Case.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    ).values('service').annotate(count=Count('id'))
    
    for item in service_counts:
        by_service[item['service']] = item['count']
    
    # Cases by status
    by_status = {}
    status_counts = Case.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    ).values('status').annotate(count=Count('id'))
    
    for item in status_counts:
        by_status[item['status']] = item['count']
    
    return {
        'new_users': new_users,
        'new_cases': new_cases,
        'completed_cases': completed_cases,
        'active_cases': active_cases,
        'paid_cases': paid_cases,
        'total_revenue': float(total_revenue),
        'docs_uploaded': docs_uploaded,
        'by_service': by_service,
        'by_status': by_status,
    }


def generate_ai_conclusion(stats, report_type, period_start, period_end):
    """
    Generate AI-driven business insights based on the stats.
    Uses OpenAI API if available, otherwise returns a template conclusion.
    """
    try:
        from django.conf import settings
        import openai
        
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            return generate_template_conclusion(stats, report_type)
        
        # Build prompt for AI analysis
        prompt = f"""Analyze the following business statistics for a consulting firm that handles tax and immigration services in the UK.

Report Type: {report_type.capitalize()}
Period: {period_start} to {period_end}

Statistics:
- New Users: {stats['new_users']}
- New Cases: {stats['new_cases']}
- Completed Cases: {stats['completed_cases']}
- Active Cases: {stats['active_cases']}
- Paid Cases: {stats['paid_cases']}
- Total Revenue: £{stats['total_revenue']:.2f}
- Documents Uploaded: {stats['docs_uploaded']}

Cases by Service:
{json.dumps(stats['by_service'], indent=2)}

Cases by Status:
{json.dumps(stats['by_status'], indent=2)}

Please provide a 2-3 paragraph business analysis with:
1. Key performance highlights
2. Trends and patterns observed
3. Recommendations for improvement

Keep the tone professional and concise."""

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a business analyst providing insights for a UK consulting firm specializing in tax and immigration services."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content
    
    except Exception as e:
        return generate_template_conclusion(stats, report_type) + f"\n\n(Note: AI analysis unavailable - {str(e)[:50]})"


def generate_template_conclusion(stats, report_type):
    """Generate a template conclusion when AI is unavailable."""
    conclusion = f"""## {report_type.capitalize()} Business Summary

**Performance Overview:**
During this period, we registered {stats['new_users']} new users and opened {stats['new_cases']} new cases. The team completed {stats['completed_cases']} cases, with {stats['active_cases']} currently active.

**Financial Highlights:**
We recorded {stats['paid_cases']} paid cases with total revenue of £{stats['total_revenue']:.2f}. Document processing remained steady with {stats['docs_uploaded']} files uploaded.

**Recommendations:**
Continue monitoring case completion rates and follow up on pending payments to optimize cash flow."""
    
    return conclusion


@login_required
@elevated_required
def reports_dashboard(request):
    """Reports dashboard with generation options and history."""
    # Get live stats for last 24 hours
    now = datetime.now()
    day_ago = now - timedelta(days=1)
    live_stats = compute_stats(day_ago, now)
    
    # Get report history (last 20)
    reports = AiReport.objects.all()[:20]
    
    context = {
        'page_title': 'Reports',
        'live_stats': live_stats,
        'reports': reports,
        **session_ctx(request),
    }
    return render(request, 'panel/reports_dashboard.html', context)


@login_required
@elevated_required
@require_POST
def report_generate(request, report_type):
    """Generate a new report."""
    now = datetime.now()
    
    # Calculate period based on report type
    if report_type == 'daily':
        start = now - timedelta(days=1)
    elif report_type == 'weekly':
        start = now - timedelta(days=7)
    elif report_type == 'monthly':
        start = now - timedelta(days=30)
    elif report_type == 'quarterly':
        start = now - timedelta(days=90)
    else:
        messages.error(request, 'Invalid report type.')
        return redirect('panel:reports')
    
    # Compute stats
    stats = compute_stats(start, now)
    
    # Generate AI conclusion
    ai_conclusion = generate_ai_conclusion(
        stats, 
        report_type, 
        start.strftime('%Y-%m-%d'),
        now.strftime('%Y-%m-%d')
    )
    
    # Save report
    report = AiReport.objects.create(
        report_type=report_type,
        period_start=start.strftime('%Y-%m-%d'),
        period_end=now.strftime('%Y-%m-%d'),
        stats=json.dumps(stats),
        ai_conclusion=ai_conclusion,
    )
    
    messages.success(request, f'{report_type.capitalize()} report generated successfully.')
    return redirect('panel:report_view', report_id=report.pk)


@login_required
@elevated_required
def report_view(request, report_id):
    """View a specific report."""
    report = get_object_or_404(AiReport, pk=report_id)
    
    # Parse stats JSON
    try:
        stats = json.loads(report.stats or '{}')
    except json.JSONDecodeError:
        stats = {}
    
    # Calculate total cases for percentages
    total_by_service = sum(stats.get('by_service', {}).values()) or 1
    service_data = []
    for service, count in stats.get('by_service', {}).items():
        pct = (count / total_by_service) * 100
        service_data.append({
            'service': service,
            'count': count,
            'pct': pct,
        })
    
    context = {
        'page_title': f'{report.get_report_type_display()} Report',
        'report': report,
        'stats': stats,
        'service_data': service_data,
        **session_ctx(request),
    }
    return render(request, 'panel/report_view.html', context)


@login_required
@elevated_required
def report_custom(request):
    """Generate a custom report with custom date range."""
    if request.method == 'POST':
        start_str = request.POST.get('start_date', '')
        end_str = request.POST.get('end_date', '')
        
        try:
            start = datetime.strptime(start_str, '%Y-%m-%d')
            end = datetime.strptime(end_str, '%Y-%m-%d')
            
            if start > end:
                messages.error(request, 'Start date must be before end date.')
                return redirect('panel:reports')
            
            # Compute stats
            stats = compute_stats(start, end)
            
            # Generate AI conclusion
            ai_conclusion = generate_ai_conclusion(
                stats,
                'custom',
                start_str,
                end_str
            )
            
            # Save report
            report = AiReport.objects.create(
                report_type='custom',
                period_start=start_str,
                period_end=end_str,
                stats=json.dumps(stats),
                ai_conclusion=ai_conclusion,
            )
            
            messages.success(request, 'Custom report generated successfully.')
            return redirect('panel:report_view', report_id=report.pk)
            
        except ValueError:
            messages.error(request, 'Invalid date format. Please use YYYY-MM-DD.')
            return redirect('panel:reports')
    
    return redirect('panel:reports')


@login_required
@elevated_required
@require_POST
def report_delete(request, report_id):
    """Delete a report."""
    report = get_object_or_404(AiReport, pk=report_id)
    report.delete()
    messages.success(request, 'Report deleted successfully.')
    return redirect('panel:reports')
