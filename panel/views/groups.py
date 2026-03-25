"""
Group Chat Monitoring views for the admin panel.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from core.models import GroupChat, GroupCooldown
from ..decorators import login_required, elevated_required
from .helpers import session_ctx


@login_required
@elevated_required
def group_chats_list(request):
    ctx = session_ctx(request)
    groups = GroupChat.objects.all()
    for g in groups:
        g.active_cooldowns = GroupCooldown.objects.filter(group=g).count()
    ctx['groups'] = groups
    ctx['page_title'] = 'Group Chats'
    return render(request, 'panel/group_chats.html', ctx)


@login_required
@elevated_required
def group_chat_add(request):
    ctx = session_ctx(request)
    ctx['page_title'] = 'Add Group Chat'
    ctx['action'] = 'add'
    ctx['lang_choices'] = GroupChat.LANGUAGE_CHOICES

    if request.method == 'POST':
        group_id_raw = request.POST.get('group_id', '').strip()
        title = request.POST.get('title', '').strip()
        language = request.POST.get('language', 'uz')
        cooldown_hours = request.POST.get('cooldown_hours', '24').strip()
        behavior_prompt = request.POST.get('behavior_prompt', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if not group_id_raw:
            messages.error(request, 'Group ID is required.')
            return render(request, 'panel/group_chat_form.html', ctx)
        try:
            group_id = int(group_id_raw)
        except ValueError:
            messages.error(request, 'Group ID must be a number.')
            return render(request, 'panel/group_chat_form.html', ctx)
        try:
            cooldown_hours = max(1, int(cooldown_hours))
        except ValueError:
            cooldown_hours = 24

        if GroupChat.objects.filter(group_id=group_id).exists():
            messages.error(request, f'A group with ID {group_id} already exists.')
            return render(request, 'panel/group_chat_form.html', ctx)

        GroupChat.objects.create(
            group_id=group_id,
            title=title,
            language=language,
            cooldown_hours=cooldown_hours,
            behavior_prompt=behavior_prompt,
            is_active=is_active,
        )
        messages.success(request, f'Group chat "{title or group_id}" added.')
        return redirect('panel:group_chats')

    return render(request, 'panel/group_chat_form.html', ctx)


@login_required
@elevated_required
def group_chat_edit(request, group_id):
    group = get_object_or_404(GroupChat, pk=group_id)
    ctx = session_ctx(request)
    ctx['page_title'] = f'Edit Group — {group.title or group.group_id}'
    ctx['action'] = 'edit'
    ctx['group'] = group
    ctx['lang_choices'] = GroupChat.LANGUAGE_CHOICES

    if request.method == 'POST':
        group.title = request.POST.get('title', '').strip()
        group.language = request.POST.get('language', 'uz')
        try:
            group.cooldown_hours = max(1, int(request.POST.get('cooldown_hours', '24')))
        except ValueError:
            group.cooldown_hours = 24
        group.behavior_prompt = request.POST.get('behavior_prompt', '').strip()
        group.is_active = request.POST.get('is_active') == 'on'
        group.save()
        messages.success(request, 'Group chat updated.')
        return redirect('panel:group_chats')

    return render(request, 'panel/group_chat_form.html', ctx)


@login_required
@elevated_required
def group_chat_delete(request, group_id):
    group = get_object_or_404(GroupChat, pk=group_id)
    if request.method == 'POST':
        name = group.title or str(group.group_id)
        group.delete()
        messages.success(request, f'Group "{name}" deleted.')
    return redirect('panel:group_chats')


@login_required
@elevated_required
def group_chat_toggle(request, group_id):
    group = get_object_or_404(GroupChat, pk=group_id)
    if request.method == 'POST':
        group.is_active = not group.is_active
        group.save(update_fields=['is_active'])
        status = 'activated' if group.is_active else 'deactivated'
        messages.success(request, f'Group "{group.title or group.group_id}" {status}.')
    return redirect('panel:group_chats')


@login_required
@elevated_required
def group_chat_clear_cooldowns(request, group_id):
    group = get_object_or_404(GroupChat, pk=group_id)
    if request.method == 'POST':
        count, _ = GroupCooldown.objects.filter(group=group).delete()
        messages.success(request, f'Cleared {count} cooldown(s) for "{group.title or group.group_id}".')
    return redirect('panel:group_chats')
