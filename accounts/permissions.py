from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Allow only logged-in users whose role is in `roles`."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def supervisor_or_admin_required(view):
    return role_required("supervisor", "admin")(view)


def admin_required(view):
    return role_required("admin")(view)
