"""
Decorators for admin panel access control.
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def login_required(view_func):
    """
    Decorator to require admin login.
    Redirects to login page if not authenticated.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check if logged in via session
        if request.session.get('admin_logged_in'):
            return view_func(request, *args, **kwargs)
        
        # Not logged in - redirect to login
        messages.warning(request, 'Please log in to access this page.')
        return redirect('panel:login')
    
    return wrapper


def master_required(view_func):
    """
    Decorator to require master admin role.
    Must be used after @login_required.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # First check if logged in
        if not request.session.get('admin_logged_in'):
            messages.warning(request, 'Please log in to access this page.')
            return redirect('panel:login')
        
        # Check for master role
        if request.session.get('admin_role') != 'master':
            messages.error(request, 'Access denied. Master privileges required.')
            return redirect('panel:dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def elevated_required(view_func):
    """
    Decorator to require elevated privileges (master or admin role).
    Must be used after @login_required.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # First check if logged in
        if not request.session.get('admin_logged_in'):
            messages.warning(request, 'Please log in to access this page.')
            return redirect('panel:login')
        
        # Check for elevated role
        if request.session.get('admin_role') not in ('master', 'admin'):
            messages.error(request, 'Access denied. Admin privileges required.')
            return redirect('panel:dashboard')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper
