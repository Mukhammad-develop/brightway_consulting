"""
Team Management views for the admin panel.
Allows master admins to manage team members (AdminUser records).
"""

from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Count

from core.models import AdminUser, AdminAssignment, TgUser
from ..decorators import login_required, master_required
from .helpers import session_ctx, hash_password
from .notifications import notify_masters


@login_required
@master_required
def team_list(request):
    """List all team members (AdminUser records)."""
    # Get filter
    role_filter = request.GET.get('role', '')
    search = request.GET.get('search', '').strip()
    
    team_members = AdminUser.objects.annotate(
        assignment_count=Count('assignments')
    )
    
    if role_filter:
        team_members = team_members.filter(role=role_filter)
    
    if search:
        team_members = team_members.filter(
            username__icontains=search
        ) | team_members.filter(
            display_name__icontains=search
        ) | team_members.filter(
            email__icontains=search
        )
    
    team_members = team_members.order_by('role', 'username')
    
    context = {
        'page_title': 'Team Management',
        'team_members': team_members,
        'role_filter': role_filter,
        'search': search,
        'roles': AdminUser.ROLE_CHOICES,
        **session_ctx(request),
    }
    return render(request, 'panel/team_list.html', context)


@login_required
@master_required
def team_add(request):
    """Add a new team member."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        display_name = request.POST.get('display_name', '').strip()
        email = request.POST.get('email', '').strip() or None
        role = request.POST.get('role', 'consultant')
        is_active = request.POST.get('is_active') == 'on'
        
        # Validation
        if not username:
            messages.error(request, 'Username is required.')
            return redirect('panel:team_add')
        
        if not password:
            messages.error(request, 'Password is required.')
            return redirect('panel:team_add')
        
        if len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
            return redirect('panel:team_add')
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return redirect('panel:team_add')
        
        # Check for duplicate username
        if AdminUser.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" is already taken.')
            return redirect('panel:team_add')
        
        # Create the admin user
        admin = AdminUser.objects.create(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name or username,
            email=email,
            role=role,
            is_active=is_active,
        )
        
        # Notify other masters
        current_admin_id = request.session.get('admin_id')
        notify_masters(
            f'New team member added',
            f'{request.session.get("admin_display", "Admin")} added {admin.display_name} ({admin.role}) to the team.',
            f'/admin/team/{admin.pk}/edit',
            exclude_id=current_admin_id
        )
        
        messages.success(request, f'Team member "{admin.display_name}" created successfully.')
        return redirect('panel:team_list')
    
    context = {
        'page_title': 'Add Team Member',
        'form_action': 'add',
        'roles': AdminUser.ROLE_CHOICES,
        **session_ctx(request),
    }
    return render(request, 'panel/team_form.html', context)


@login_required
@master_required
def team_edit(request, admin_id):
    """Edit an existing team member."""
    admin = get_object_or_404(AdminUser, pk=admin_id)
    
    if request.method == 'POST':
        display_name = request.POST.get('display_name', '').strip()
        email = request.POST.get('email', '').strip() or None
        role = request.POST.get('role', admin.role)
        is_active = request.POST.get('is_active') == 'on'
        new_password = request.POST.get('new_password', '').strip()
        
        # Update fields
        admin.display_name = display_name or admin.username
        admin.email = email
        admin.role = role
        admin.is_active = is_active
        
        # Update password if provided
        if new_password:
            if len(new_password) < 6:
                messages.error(request, 'Password must be at least 6 characters.')
                return redirect('panel:team_edit', admin_id=admin_id)
            admin.password_hash = hash_password(new_password)
            messages.info(request, 'Password has been updated.')
        
        admin.save()
        
        messages.success(request, f'Team member "{admin.display_name}" updated successfully.')
        return redirect('panel:team_list')
    
    # Get assignments for this admin
    assignments = AdminAssignment.objects.filter(admin=admin).select_related('user')
    
    context = {
        'page_title': f'Edit: {admin.display_name or admin.username}',
        'form_action': 'edit',
        'admin_user': admin,
        'assignments': assignments,
        'roles': AdminUser.ROLE_CHOICES,
        **session_ctx(request),
    }
    return render(request, 'panel/team_form.html', context)


@login_required
@master_required
@require_POST
def team_delete(request, admin_id):
    """Delete a team member."""
    admin = get_object_or_404(AdminUser, pk=admin_id)
    
    # Prevent deleting yourself
    if admin.pk == request.session.get('admin_id'):
        messages.error(request, 'You cannot delete your own account.')
        return redirect('panel:team_list')
    
    # Store name for message
    admin_name = admin.display_name or admin.username
    
    # Delete assignments first
    AdminAssignment.objects.filter(admin=admin).delete()
    
    # Delete the admin user
    admin.delete()
    
    # Notify other masters
    current_admin_id = request.session.get('admin_id')
    notify_masters(
        f'Team member removed',
        f'{request.session.get("admin_display", "Admin")} removed {admin_name} from the team.',
        None,
        exclude_id=current_admin_id
    )
    
    messages.success(request, f'Team member "{admin_name}" has been deleted.')
    return redirect('panel:team_list')


@login_required
@master_required
@require_POST
def team_toggle_status(request, admin_id):
    """Toggle a team member's active status."""
    admin = get_object_or_404(AdminUser, pk=admin_id)
    
    # Prevent deactivating yourself
    if admin.pk == request.session.get('admin_id'):
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('panel:team_list')
    
    admin.is_active = not admin.is_active
    admin.save(update_fields=['is_active'])
    
    status = 'activated' if admin.is_active else 'deactivated'
    messages.success(request, f'Team member "{admin.display_name}" has been {status}.')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'is_active': admin.is_active})
    return redirect('panel:team_list')


@login_required
@master_required
def team_assignments(request, admin_id):
    """Manage user assignments for a team member."""
    admin = get_object_or_404(AdminUser, pk=admin_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'assign':
            user_id = request.POST.get('user_id')
            try:
                user = TgUser.objects.get(pk=user_id)
                # Check if assignment already exists
                if not AdminAssignment.objects.filter(admin=admin, user=user).exists():
                    AdminAssignment.objects.create(admin=admin, user=user)
                    messages.success(request, f'User {user} assigned to {admin.display_name}.')
                else:
                    messages.info(request, 'User is already assigned to this team member.')
            except TgUser.DoesNotExist:
                messages.error(request, 'User not found.')
        
        elif action == 'remove':
            assignment_id = request.POST.get('assignment_id')
            try:
                assignment = AdminAssignment.objects.get(pk=assignment_id, admin=admin)
                assignment.delete()
                messages.success(request, 'Assignment removed.')
            except AdminAssignment.DoesNotExist:
                messages.error(request, 'Assignment not found.')
        
        return redirect('panel:team_assignments', admin_id=admin_id)
    
    # Get current assignments
    assignments = AdminAssignment.objects.filter(admin=admin).select_related('user')
    
    # Get unassigned users (not assigned to this admin)
    assigned_user_ids = assignments.values_list('user_id', flat=True)
    unassigned_users = TgUser.objects.exclude(pk__in=assigned_user_ids).order_by('-created_at')[:50]
    
    context = {
        'page_title': f'Assignments: {admin.display_name or admin.username}',
        'admin_user': admin,
        'assignments': assignments,
        'unassigned_users': unassigned_users,
        **session_ctx(request),
    }
    return render(request, 'panel/team_assignments.html', context)


@login_required
@master_required
@require_POST
def reset_password(request, admin_id):
    """Reset a team member's password."""
    admin = get_object_or_404(AdminUser, pk=admin_id)
    
    new_password = request.POST.get('new_password', '').strip()
    
    if not new_password:
        messages.error(request, 'New password is required.')
        return redirect('panel:team_edit', admin_id=admin_id)
    
    if len(new_password) < 6:
        messages.error(request, 'Password must be at least 6 characters.')
        return redirect('panel:team_edit', admin_id=admin_id)
    
    admin.password_hash = hash_password(new_password)
    admin.save(update_fields=['password_hash'])
    
    messages.success(request, f'Password for "{admin.display_name}" has been reset.')
    
    # Notify the user if they have a notification record
    from .notifications import notify_user
    notify_user(
        admin.pk,
        'Password Reset',
        'Your password has been reset by an administrator. Please log in with your new password.',
        '/admin/login'
    )
    
    return redirect('panel:team_edit', admin_id=admin_id)
