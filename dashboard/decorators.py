from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Vui lòng đăng nhập bằng tài khoản Quản trị viên.")
            return redirect('/admin-django/login/?next=' + request.path)

        is_active_admin = (
            getattr(request.user, 'role', None) == 'ADMIN'
            and getattr(request.user, 'account_status', 'Active') == 'Active'
        )
        if not is_active_admin:
            messages.error(request, "Bạn không có quyền truy cập vào phân hệ Quản trị viên.")
            return redirect('/')

        return view_func(request, *args, **kwargs)
    return _wrapped_view