"""
Service Management views for the admin panel.
Allows admins to manage service definitions and their steps.
"""

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST, require_http_methods

from core.models import ServiceDefinition, ServiceStep, Case
from ..decorators import login_required, elevated_required
from .helpers import session_ctx

# Step slug -> emoji for services list preview
STEP_ICONS = {
    'paid': '💰', 'docs_received': '📄', 'application_prepared': '📝',
    'submitted': '📤', 'done': '✅', 'p45_verified': '📋', 'docs_collected': '📁',
    'submitted_hmrc': '📨', 'refund_processed': '💳', 'info_gathered': '📋',
    'return_prepared': '📑', 'filed': '📂', 'onboarded': '👤', 'books_updated': '📒',
}


@login_required
@elevated_required
def services_list(request):
    """List all service definitions."""
    services = ServiceDefinition.objects.prefetch_related('steps').all()
    
    # Count cases per service
    service_data = []
    for svc in services:
        steps_ordered = list(svc.steps.all().order_by('step_number'))
        steps_with_icons = [
            {'step': s, 'icon': STEP_ICONS.get((s.slug or '').lower(), '•')}
            for s in steps_ordered
        ]
        service_data.append({
            'service': svc,
            'case_count': Case.objects.filter(service=svc.slug).count(),
            'steps': steps_with_icons,
        })
    
    context = {
        'page_title': 'Service Management',
        'services': service_data,
        **session_ctx(request),
    }
    return render(request, 'panel/services_list.html', context)


@login_required
@elevated_required
def service_add(request):
    """Add a new service definition."""
    if request.method == 'POST':
        # Get form data
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip().lower().replace(' ', '_')
        description = request.POST.get('description', '').strip()
        name_ru = request.POST.get('name_ru', '').strip()
        name_uz = request.POST.get('name_uz', '').strip()
        description_ru = request.POST.get('description_ru', '').strip()
        description_uz = request.POST.get('description_uz', '').strip()
        keywords = request.POST.get('keywords', '').strip()
        ai_system_prompt = request.POST.get('ai_system_prompt', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        icon_emoji = request.POST.get('icon_emoji', '📋').strip() or '📋'
        badge_color = request.POST.get('badge_color', 'general').strip()
        display_order = int(request.POST.get('display_order', 0) or 0)
        
        # Validation
        if not name:
            messages.error(request, 'Service name is required.')
            return redirect('panel:service_add')
        
        if not slug:
            slug = name.lower().replace(' ', '_')[:50]
        
        # Check for duplicate slug
        if ServiceDefinition.objects.filter(slug=slug).exists():
            messages.error(request, f'A service with slug "{slug}" already exists.')
            return redirect('panel:service_add')
        
        # Create service
        service = ServiceDefinition.objects.create(
            name=name,
            slug=slug,
            description=description,
            name_ru=name_ru,
            name_uz=name_uz,
            description_ru=description_ru,
            description_uz=description_uz,
            keywords=keywords,
            ai_system_prompt=ai_system_prompt,
            is_active=is_active,
            icon_emoji=icon_emoji,
            badge_color=badge_color,
            display_order=display_order,
        )
        
        # Create default steps
        default_steps = [
            {'label': 'Paid', 'slug': 'paid', 'step_number': 1},
            {'label': 'In Progress', 'slug': 'in_progress', 'step_number': 2},
            {'label': 'Done', 'slug': 'done', 'step_number': 3, 'is_final': True},
        ]
        for step_data in default_steps:
            ServiceStep.objects.create(
                service=service,
                label=step_data['label'],
                slug=step_data['slug'],
                step_number=step_data['step_number'],
                is_final=step_data.get('is_final', False),
            )
        
        messages.success(request, f'Service "{name}" created successfully with default steps.')
        return redirect('panel:services_list')
    
    context = {
        'page_title': 'Add Service',
        'form_action': 'add',
        **session_ctx(request),
    }
    return render(request, 'panel/service_form.html', context)


@login_required
@elevated_required
def service_edit(request, service_id):
    """Edit an existing service definition."""
    service = get_object_or_404(ServiceDefinition, pk=service_id)
    
    if request.method == 'POST':
        # Get form data
        service.name = request.POST.get('name', '').strip() or service.name
        service.description = request.POST.get('description', '').strip()
        service.name_ru = request.POST.get('name_ru', '').strip()
        service.name_uz = request.POST.get('name_uz', '').strip()
        service.description_ru = request.POST.get('description_ru', '').strip()
        service.description_uz = request.POST.get('description_uz', '').strip()
        service.keywords = request.POST.get('keywords', '').strip()
        service.ai_system_prompt = request.POST.get('ai_system_prompt', '').strip()
        service.is_active = request.POST.get('is_active') == 'on'
        service.icon_emoji = request.POST.get('icon_emoji', '📋').strip() or '📋'
        service.badge_color = request.POST.get('badge_color', 'general').strip()
        service.display_order = int(request.POST.get('display_order', 0) or 0)
        
        # AI settings
        service.ai_collect_items = request.POST.get('ai_collect_items', '').strip()
        service.ai_documents_list = request.POST.get('ai_documents_list', '').strip()
        service.ai_strict_flow = request.POST.get('ai_strict_flow') == 'on'
        
        service.save()
        
        messages.success(request, f'Service "{service.name}" updated successfully.')
        return redirect('panel:services_list')
    
    # Strip whitespace for display so inputs don't show leading/trailing blank
    def _s(s):
        return (s or '').strip()
    service.name = _s(service.name)
    service.slug = _s(service.slug)
    service.description = _s(service.description)
    service.name_ru = _s(service.name_ru)
    service.name_uz = _s(service.name_uz)
    service.description_ru = _s(service.description_ru)
    service.description_uz = _s(service.description_uz)
    service.keywords = _s(service.keywords)
    service.ai_system_prompt = _s(service.ai_system_prompt)
    service.icon_emoji = _s(service.icon_emoji) or '📋'
    service.ai_collect_items = _s(service.ai_collect_items)
    service.ai_documents_list = _s(service.ai_documents_list)
    
    context = {
        'page_title': f'Edit Service: {service.name}',
        'form_action': 'edit',
        'service': service,
        **session_ctx(request),
    }
    return render(request, 'panel/service_form.html', context)


@login_required
@elevated_required
@require_POST
def service_delete(request, service_id):
    """Delete a service definition."""
    service = get_object_or_404(ServiceDefinition, pk=service_id)
    
    # Check if any cases reference this service
    case_count = Case.objects.filter(service=service.slug).count()
    if case_count > 0:
        messages.error(request, f'Cannot delete "{service.name}" - {case_count} cases use this service. Consider deactivating instead.')
        return redirect('panel:services_list')
    
    # Delete steps first, then service
    ServiceStep.objects.filter(service=service).delete()
    service_name = service.name
    service.delete()
    
    messages.success(request, f'Service "{service_name}" deleted successfully.')
    return redirect('panel:services_list')


@login_required
@elevated_required
@require_POST
def service_toggle(request, service_id):
    """Toggle service active status."""
    service = get_object_or_404(ServiceDefinition, pk=service_id)
    service.is_active = not service.is_active
    service.save(update_fields=['is_active'])
    
    status = 'activated' if service.is_active else 'deactivated'
    messages.success(request, f'Service "{service.name}" {status}.')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'is_active': service.is_active})
    return redirect('panel:services_list')


@login_required
@elevated_required
def service_steps(request, service_id):
    """Manage service steps."""
    service = get_object_or_404(ServiceDefinition, pk=service_id)
    steps = service.steps.all().order_by('step_number')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            label = request.POST.get('label', '').strip()
            slug = request.POST.get('slug', '').strip().lower().replace(' ', '_')
            description = request.POST.get('description', '').strip()
            title = request.POST.get('title', '').strip()
            title_ru = request.POST.get('title_ru', '').strip()
            title_uz = request.POST.get('title_uz', '').strip()
            is_required = request.POST.get('is_required') == 'on'
            is_final = request.POST.get('is_final') == 'on'
            
            if not label:
                messages.error(request, 'Step label is required.')
                return redirect('panel:service_steps', service_id=service_id)
            
            if not slug:
                slug = label.lower().replace(' ', '_')[:50]
            
            # Check for duplicate slug
            if ServiceStep.objects.filter(service=service, slug=slug).exists():
                messages.error(request, f'A step with slug "{slug}" already exists for this service.')
                return redirect('panel:service_steps', service_id=service_id)
            
            # Get next step number
            max_step = steps.aggregate(max_num=models.Max('step_number'))['max_num'] or 0
            
            ServiceStep.objects.create(
                service=service,
                label=label,
                slug=slug,
                title=title or label,
                title_ru=title_ru,
                title_uz=title_uz,
                description=description,
                step_number=max_step + 1,
                is_required=is_required,
                is_final=is_final,
            )
            messages.success(request, f'Step "{label}" added successfully.')
            
        elif action == 'delete':
            step_id = request.POST.get('step_id')
            try:
                step = ServiceStep.objects.get(pk=step_id, service=service)
                step_label = step.label
                step.delete()
                messages.success(request, f'Step "{step_label}" deleted.')
            except ServiceStep.DoesNotExist:
                messages.error(request, 'Step not found.')
        
        elif action == 'reorder':
            # Handle step reordering (expects JSON body)
            try:
                import json
                data = json.loads(request.body)
                step_order = data.get('order', [])
                for idx, step_id in enumerate(step_order):
                    ServiceStep.objects.filter(pk=step_id, service=service).update(step_number=idx + 1)
                return JsonResponse({'ok': True})
            except (json.JSONDecodeError, KeyError):
                return JsonResponse({'ok': False, 'error': 'Invalid data'})
        
        return redirect('panel:service_steps', service_id=service_id)
    
    context = {
        'page_title': f'Steps: {service.name}',
        'service': service,
        'steps': steps,
        **session_ctx(request),
    }
    return render(request, 'panel/service_steps.html', context)


@login_required
@elevated_required
@require_POST
def step_edit(request, service_id, step_id):
    """Edit a service step."""
    service = get_object_or_404(ServiceDefinition, pk=service_id)
    step = get_object_or_404(ServiceStep, pk=step_id, service=service)
    
    step.label = request.POST.get('label', '').strip() or step.label
    step.title = request.POST.get('title', '').strip()
    step.title_ru = request.POST.get('title_ru', '').strip()
    step.title_uz = request.POST.get('title_uz', '').strip()
    step.description = request.POST.get('description', '').strip()
    step.description_ru = request.POST.get('description_ru', '').strip()
    step.description_uz = request.POST.get('description_uz', '').strip()
    step.is_required = request.POST.get('is_required') == 'on'
    step.is_final = request.POST.get('is_final') == 'on'
    
    step.save()
    
    messages.success(request, f'Step "{step.label}" updated.')
    return redirect('panel:service_steps', service_id=service_id)


@login_required
@elevated_required
@require_POST
def test_prompt(request, service_id):
    """Test AI system prompt with a sample message."""
    service = get_object_or_404(ServiceDefinition, pk=service_id)
    
    try:
        data = json.loads(request.body)
        message = data.get('message', '')
        
        if not message:
            return JsonResponse({'ok': False, 'error': 'No message provided'})
        
        # Build test prompt from service definition
        from bot.services import test_ai_prompt, build_system_prompt, TONE_RULES
        
        # Use the full system prompt as configured
        if service.ai_system_prompt:
            system_prompt = service.ai_system_prompt
        else:
            system_prompt = f"You are an AI assistant for {service.name} service."
        
        # Add tone rules if not already included
        if TONE_RULES not in system_prompt:
            system_prompt += f"\n\n{TONE_RULES}"
        
        # Test the prompt using our AI service
        ai_response = test_ai_prompt(system_prompt, message)
        
        return JsonResponse({
            'ok': True, 
            'response': ai_response
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})
    except Exception as e:
        return JsonResponse({
            'ok': False,
            'error': f'Error testing prompt: {str(e)}'
        })


# Import models at top level to avoid circular imports
from django.db import models
