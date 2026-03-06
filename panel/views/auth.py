"""
Authentication views for the admin panel.
"""

from django.shortcuts import render, redirect
from django.contrib import messages
from .helpers import check_admin_login, session_ctx


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
    for key in ['admin_logged_in', 'admin_username', 'admin_role', 'admin_id', 'admin_display']:
        request.session.pop(key, None)
    
    messages.info(request, 'You have been logged out.')
    return redirect('panel:login')
