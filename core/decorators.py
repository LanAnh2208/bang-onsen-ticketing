from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied


def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.account_status != 'Active' or request.user.role not in allowed_roles:
                raise PermissionDenied("Bạn không có quyền truy cập vào phân hệ này.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator