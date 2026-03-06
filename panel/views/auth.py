"""
Authentication views for the admin panel.
"""

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods

from .helpers import check_admin_login, session_ctx, get_current_admin, hash_password, verify_password
from ..decorators import login_required


def _theme_choices():
    return [
        ('default', 'Default'),
        ('blue', 'Blue'),
        ('green', 'Green'),
        ('purple', 'Purple'),
    ]


def login_view(request):
    """
    Admin login view.
    GET: Display login form
    POST: Process login
    """
    # Already logged in? Redirect to dashboard
    if request.session.get('admin_logged_in'):
        return redirect('panel:dashboard')
    
    context = {}
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        if not username or not password:
            messages.error(request, 'Please enter both username and password.')
        else:
            success, role, admin_id, display_name = check_admin_login(username, password)
            
            if success:
                # Set session variables
                request.session['admin_logged_in'] = True
                request.session['admin_username'] = username
                request.session['admin_role'] = role
                request.session['admin_id'] = admin_id
                request.session['admin_display'] = display_name
                # Load theme from DB for DB admins
                if admin_id:
                    from core.models import AdminUser
                    try:
                        a = AdminUser.objects.get(pk=admin_id)
                        request.session['theme_mode'] = getattr(a, 'theme_mode', 'dark')
                        request.session['theme_dark'] = getattr(a, 'theme_dark', 'blue')
                        request.session['theme_light'] = getattr(a, 'theme_light', 'blue')
                    except Exception:
                        request.session.setdefault('theme_mode', 'dark')
                        request.session.setdefault('theme_dark', 'blue')
                        request.session.setdefault('theme_light', 'blue')
                else:
                    request.session.setdefault('theme_mode', 'dark')
                    request.session.setdefault('theme_dark', 'blue')
                    request.session.setdefault('theme_light', 'blue')
                
                messages.success(request, f'Welcome back, {display_name}!')
                return redirect('panel:dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
    
    return render(request, 'panel/login.html', context)


def logout_view(request):
    """
    Admin logout view.
    Clears session and redirects to login.
    """
    # Clear admin session data
    for key in ['admin_logged_in', 'admin_username', 'admin_role', 'admin_id', 'admin_display',
                'theme_mode', 'theme_dark', 'theme_light']:
        request.session.pop(key, None)
    
    messages.info(request, 'You have been logged out.')
    return redirect('panel:login')


@login_required
@require_http_methods(['GET', 'POST'])
def profile_view(request):
    """
    Admin profile page: account info, edit display name / username / password, theme settings.
    Master admin has no DB record so only display name and theme are stored in session.
    """
    from core.models import AdminUser
    
    context = {
        'page_title': 'Profile',
        'theme_choices': _theme_choices(),
        **session_ctx(request),
    }
    admin = get_current_admin(request)
    is_master = request.session.get('admin_role') == 'master'
    
    if request.method == 'GET':
        if admin:
            context['admin_user'] = admin
            context['current_username'] = admin.username
            context['current_display_name'] = admin.display_name or admin.username
            context['current_email'] = admin.email or ''
            context['current_theme_mode'] = getattr(admin, 'theme_mode', 'dark')
            context['current_theme_dark'] = getattr(admin, 'theme_dark', 'default')
            context['current_theme_light'] = getattr(admin, 'theme_light', 'default')
        else:
            context['admin_user'] = None
            context['current_username'] = request.session.get('admin_username', '')
            context['current_display_name'] = request.session.get('admin_display', 'Master Admin')
            context['current_email'] = ''
            context['current_theme_mode'] = request.session.get('theme_mode', 'dark')
            context['current_theme_dark'] = request.session.get('theme_dark', 'default')
            context['current_theme_light'] = request.session.get('theme_light', 'default')
        context['is_master'] = is_master
        return render(request, 'panel/profile.html', context)
    
    # POST: update profile
    display_name = request.POST.get('display_name', '').strip() or None
    theme_mode = request.POST.get('theme_mode', 'dark')
    theme_dark = request.POST.get('theme_dark', 'blue')
    theme_light = request.POST.get('theme_light', 'blue')
    
    if theme_mode not in ('dark', 'light'):
        theme_mode = 'dark'
    if theme_dark not in [c[0] for c in _theme_choices()]:
        theme_dark = 'blue'
    if theme_light not in [c[0] for c in _theme_choices()]:
        theme_light = 'blue'
    
    # Update session theme so UI reflects immediately
    request.session['theme_mode'] = theme_mode
    request.session['theme_dark'] = theme_dark
    request.session['theme_light'] = theme_light
    
    if admin:
        admin.display_name = display_name
        admin.theme_mode = theme_mode
        admin.theme_dark = theme_dark
        admin.theme_light = theme_light
        
        new_username = request.POST.get('username', '').strip()
        if new_username and new_username != admin.username:
            if AdminUser.objects.filter(username=new_username).exclude(pk=admin.pk).exists():
                messages.error(request, 'That username is already taken.')
                return redirect('panel:profile')
            admin.username = new_username
            request.session['admin_username'] = admin.username
        
        email = request.POST.get('email', '').strip() or None
        admin.email = email
        
        new_password = request.POST.get('password', '')
        if new_password:
            current_password = request.POST.get('current_password', '')
            if not verify_password(admin.password_hash, current_password):
                messages.error(request, 'Current password is incorrect.')
                return redirect('panel:profile')
            if len(new_password) < 6:
                messages.error(request, 'New password must be at least 6 characters.')
                return redirect('panel:profile')
            admin.password_hash = hash_password(new_password)
        
        admin.save()
        request.session['admin_display'] = admin.display_name or admin.username
        messages.success(request, 'Profile updated.')
    else:
        # Master: only session
        if display_name is not None:
            request.session['admin_display'] = display_name
        messages.success(request, 'Profile updated.')
    
    return redirect('panel:profile')


@login_required
@require_http_methods(['POST'])
def theme_toggle_view(request):
    """Toggle theme mode (dark/light) and redirect back."""
    current = request.session.get('theme_mode', 'dark')
    request.session['theme_mode'] = 'light' if current == 'dark' else 'dark'
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or '/admin/'
    return redirect(next_url)
