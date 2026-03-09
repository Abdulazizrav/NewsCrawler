from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def get_user_role(user):
    """Returns role string or None if no profile."""
    try:
        return user.profile.role
    except Exception:
        return None


def is_superadmin(user):
    return get_user_role(user) == 'superadmin'


def is_channel_admin(user):
    return get_user_role(user) == 'channel_admin'


def superadmin_required(view_func):
    """Decorator: only superadmin can access."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/admin/login/')
        if not is_superadmin(request.user):
            messages.error(request, 'Access denied. Superadmin only.')
            return redirect('dashboard:home')
        return view_func(request, *args, **kwargs)
    return wrapper


def channel_admin_required(view_func):
    """Decorator: only channel admins can access."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/admin/login/')
        if not is_channel_admin(request.user):
            messages.error(request, 'Access denied.')
            return redirect('dashboard:home')
        return view_func(request, *args, **kwargs)
    return wrapper


def any_admin_required(view_func):
    """Decorator: any authenticated user with a profile."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/admin/login/')
        role = get_user_role(request.user)
        if not role:
            messages.error(request, 'No role assigned to your account.')
            return redirect('/admin/login/')
        return view_func(request, *args, **kwargs)
    return wrapper