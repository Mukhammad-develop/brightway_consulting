"""
Public website views for Brightway Consulting.
"""

from django.shortcuts import render, redirect
from django.http import JsonResponse
from core.models import ServiceDefinition


def get_active_services():
    """Get active services from database or use defaults."""
    services = ServiceDefinition.objects.filter(is_active=True)
    if services.exists():
        return services
    
    # Return default services if none in database
    return [
        {
            'slug': 'student',
            'name': 'Student Visa & University',
            'description': 'Complete assistance with student visa applications, university admissions, and educational guidance.',
            'icon_emoji': '🎓',
            'badge_color': 'student',
        },
        {
            'slug': 'paye',
            'name': 'PAYE Tax Refund',
            'description': 'Claim your tax refund if you\'ve overpaid through PAYE. We handle the entire process with HMRC.',
            'icon_emoji': '💷',
            'badge_color': 'paye',
        },
        {
            'slug': 'self',
            'name': 'Self Assessment Tax',
            'description': 'Professional self-assessment tax return preparation and filing for freelancers and self-employed.',
            'icon_emoji': '📊',
            'badge_color': 'self',
        },
        {
            'slug': 'company',
            'name': 'Company Accounting',
            'description': 'Full accounting services for limited companies including VAT, payroll, and annual accounts.',
            'icon_emoji': '🏢',
            'badge_color': 'company',
        },
    ]


def index(request):
    """Landing page view."""
    services = get_active_services()
    context = {
        'services': services,
        'current_lang': request.session.get('language', 'en'),
    }
    return render(request, 'public/index.html', context)


def services(request):
    """Services page view."""
    services_list = get_active_services()
    context = {
        'services': services_list,
        'current_lang': request.session.get('language', 'en'),
    }
    return render(request, 'public/services.html', context)


def contact(request):
    """Contact page view."""
    context = {
        'current_lang': request.session.get('language', 'en'),
    }
    if request.method == 'POST':
        # Handle contact form submission
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        message = request.POST.get('message')
        
        # In production, this would send an email or store in database
        context['form_submitted'] = True
        context['form_success'] = True
        
    return render(request, 'public/contact.html', context)


def set_language(request, lang):
    """Set the user's language preference."""
    if lang in ['en', 'ru', 'uz']:
        request.session['language'] = lang
    
    # Redirect back to the referring page or home
    referer = request.META.get('HTTP_REFERER', '/')
    return redirect(referer)
