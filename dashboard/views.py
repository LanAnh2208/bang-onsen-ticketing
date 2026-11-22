from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from core.models import Service, ServicePrice, PriceAuditLog, Voucher
from .decorators import admin_required
from .selectors import get_dashboard_overview_data
from .services import export_reconciliation_csv
from .forms import ServiceForm, ServicePriceForm, VoucherForm


def _parse_filter_params(request):
    date_str = request.GET.get('date')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.localdate()
    except ValueError:
        target_date = timezone.localdate()

    channel_filter = request.GET.get('channel', '')
    staff_id = request.GET.get('staff_id', '')
    return target_date, channel_filter, staff_id


@admin_required
def overview(request):
    target_date, channel_filter, staff_id = _parse_filter_params(request)

    if request.GET.get('export') == 'csv':
        return export_reconciliation_csv(target_date, channel_filter, staff_id)

    context = get_dashboard_overview_data(target_date, channel_filter, staff_id)
    context['selected_date'] = target_date.strftime('%Y-%m-%d')
    context['selected_channel'] = channel_filter
    context['selected_staff_id'] = staff_id
    return render(request, 'dashboard/overview.html', context)


@admin_required
def pricing_matrix(request):
    service_form = ServiceForm()
    price_form = ServicePriceForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_service':
            service_form = ServiceForm(request.POST)
            if service_form.is_valid():
                service_form.save()
                messages.success(request, "Đã thêm gói dịch vụ Onsen mới thành công.")
                return redirect('dashboard:pricing_matrix')
            else:
                messages.error(request, "Lỗi nhập liệu gói dịch vụ. Vui lòng kiểm tra lại mã gói hoặc thông tin.")

        elif action == 'toggle_service':
            srv = get_object_or_404(Service, id=request.POST.get('service_pk'))
            srv.service_status = 'Inactive' if srv.service_status == 'Active' else 'Active'
            srv.save()
            messages.success(request, f"Đã cập nhật trạng thái gói {srv.service_name} thành {srv.get_service_status_display()}.")
            return redirect('dashboard:pricing_matrix')

        elif action == 'save_price':
            service_id = request.POST.get('service')
            ticket_type = request.POST.get('ticket_type')
            day_type = request.POST.get('day_type')

            existing_price = ServicePrice.objects.filter(
                service_id=service_id,
                ticket_type=ticket_type,
                day_type=day_type
            ).first()

            if existing_price:
                old_price = existing_price.price
                old_qt_price = existing_price.quang_tri_price
                price_form = ServicePriceForm(request.POST, instance=existing_price)
                if price_form.is_valid():
                    updated_obj = price_form.save()
                    if old_price != updated_obj.price or old_qt_price != updated_obj.quang_tri_price:
                        PriceAuditLog.objects.create(
                            service_price=updated_obj,
                            changed_by=request.user,
                            old_price=old_price,
                            new_price=updated_obj.price,
                            old_quang_tri_price=old_qt_price,
                            new_quang_tri_price=updated_obj.quang_tri_price,
                        )
                    messages.success(request, "Đã cập nhật cấu hình bảng giá và lưu lịch sử thay đổi.")
                    return redirect('dashboard:pricing_matrix')
            else:
                price_form = ServicePriceForm(request.POST)
                if price_form.is_valid():
                    price_form.save()
                    messages.success(request, "Đã thiết lập mức giá mới vào ma trận.")
                    return redirect('dashboard:pricing_matrix')

            messages.error(request, "Dữ liệu bảng giá không hợp lệ. Vui lòng kiểm tra lại số tiền.")

    services = Service.objects.all().order_by('service_id')
    prices = ServicePrice.objects.select_related('service').order_by('service__service_id', 'day_type', 'ticket_type')
    audit_logs = PriceAuditLog.objects.select_related('service_price__service', 'changed_by').order_by('-changed_at')[:15]

    context = {
        'services': services,
        'prices': prices,
        'audit_logs': audit_logs,
        'service_form': service_form,
        'price_form': price_form,
    }
    return render(request, 'dashboard/pricing_matrix.html', context)


@admin_required
def voucher_list(request):
    form = VoucherForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_voucher':
            form = VoucherForm(request.POST)
            if form.is_valid():
                voucher = form.save()
                messages.success(request, f"Đã tạo mã voucher {voucher.voucher_code} thành công.")
                return redirect('dashboard:voucher_list')
            messages.error(request, "Thông tin voucher chưa hợp lệ. Vui lòng kiểm tra lại.")

        elif action == 'toggle_voucher':
            voucher = get_object_or_404(Voucher, id=request.POST.get('voucher_id'))
            voucher.voucher_status = 'Inactive' if voucher.voucher_status == 'Active' else 'Active'
            voucher.save()
            status_text = "kích hoạt" if voucher.voucher_status == 'Active' else "vô hiệu hóa"
            messages.success(request, f"Đã {status_text} mã voucher {voucher.voucher_code}.")
            return redirect('dashboard:voucher_list')

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    vouchers = Voucher.objects.all().order_by('-id')
    if search_query:
        vouchers = vouchers.filter(voucher_code__icontains=search_query)
    if status_filter in ('Active', 'Inactive'):
        vouchers = vouchers.filter(voucher_status=status_filter)

    all_vouchers = list(Voucher.objects.all())
    stats = {
        'total_count': len(all_vouchers),
        'active_count': sum(1 for v in all_vouchers if v.is_valid_today()),
        'total_used': sum(v.used_count for v in all_vouchers),
    }

    context = {
        'vouchers': vouchers,
        'form': form,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'today': timezone.localdate(),
    }
    return render(request, 'dashboard/voucher_list.html', context)


@admin_required
def staff_list(request):
    UserModel = get_user_model()
    has_role_field = any(f.name == 'role' for f in UserModel._meta.fields)
    has_full_name_field = any(f.name == 'full_name' for f in UserModel._meta.fields)
    has_account_status_field = any(f.name == 'account_status' for f in UserModel._meta.fields)

    form_data = {
        'username': '',
        'full_name': '',
        'email': '',
        'role': 'RECEPTIONIST',
    }

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_staff':
            username = (request.POST.get('username') or '').strip()
            full_name = (request.POST.get('full_name') or '').strip()
            email = (request.POST.get('email') or '').strip()
            password = request.POST.get('password') or ''
            role = (request.POST.get('role') or 'RECEPTIONIST').strip().upper()

            form_data = {
                'username': username,
                'full_name': full_name,
                'email': email,
                'role': role,
            }

            if not username or not password or (has_full_name_field and not full_name):
                messages.error(request, "Vui lòng nhập đầy đủ tên đăng nhập, họ tên và mật khẩu.")
                return redirect('dashboard:staff_list')

            if len(password) < 6:
                messages.error(request, "Mật khẩu khởi tạo phải có ít nhất 6 ký tự.")
                return redirect('dashboard:staff_list')

            if UserModel.objects.filter(username__iexact=username).exists():
                messages.error(request, f"Tên đăng nhập '{username}' đã tồn tại trong hệ thống.")
                return redirect('dashboard:staff_list')

            create_kwargs = {
                'username': username,
                'email': email,
                'is_active': True,
                'is_staff': True,
                'is_superuser': (role == 'ADMIN'),
            }
            if has_full_name_field:
                create_kwargs['full_name'] = full_name
            if has_role_field:
                valid_roles = {
                    code for code, _ in (
                        UserModel._meta.get_field('role').choices
                        or [('ADMIN', 'Quản trị viên'), ('RECEPTIONIST', 'Nhân viên lễ tân')]
                    )
                }
                create_kwargs['role'] = role if role in valid_roles else 'RECEPTIONIST'
            if has_account_status_field:
                create_kwargs['account_status'] = 'Active'

            try:
                new_user = UserModel(**create_kwargs)
                new_user.set_password(password)
                new_user.save()
            except IntegrityError:
                messages.error(request, "Không thể tạo tài khoản do trùng dữ liệu duy nhất trong hệ thống.")
                return redirect('dashboard:staff_list')

            acc_label = f" ({new_user.account_id})" if getattr(new_user, 'account_id', None) else ""
            messages.success(request, f"Đã tạo tài khoản '{new_user.username}'{acc_label} thành công.")
            return redirect('dashboard:staff_list')

        target_user = get_object_or_404(UserModel, pk=request.POST.get('user_pk'))

        if action == 'toggle_active':
            if target_user == request.user:
                messages.error(request, "Không thể tự vô hiệu hóa tài khoản đang đăng nhập.")
            else:
                next_active = not target_user.is_active
                target_user.is_active = next_active
                if has_account_status_field:
                    setattr(target_user, 'account_status', 'Active' if next_active else 'Inactive')
                target_user.save()
                state_text = "kích hoạt" if next_active else "tạm khóa"
                messages.success(request, f"Đã {state_text} tài khoản {target_user.username}.")
            return redirect('dashboard:staff_list')

        elif action == 'update_permission':
            selected_role = request.POST.get('role', '').strip()
            if has_role_field and selected_role:
                role_upper = selected_role.upper()
                if role_upper == 'ADMIN':
                    target_user.is_superuser = True
                    target_user.is_staff = True
                    setattr(target_user, 'role', 'ADMIN')
                else:
                    if target_user == request.user and target_user.is_superuser:
                        messages.error(request, "Không thể tự hạ quyền Quản trị viên của tài khoản đang đăng nhập.")
                        return redirect('dashboard:staff_list')
                    target_user.is_superuser = False
                    target_user.is_staff = role_upper in ('ADMIN', 'MANAGER', 'STAFF', 'RECEPTIONIST')
                    setattr(target_user, 'role', selected_role)
                target_user.save()
                messages.success(request, f"Đã cập nhật vai trò của {target_user.username} thành {selected_role}.")
            else:
                perm_level = request.POST.get('perm_level', 'staff')
                if perm_level == 'admin':
                    target_user.is_staff = True
                    target_user.is_superuser = True
                elif perm_level == 'staff':
                    target_user.is_staff = True
                    target_user.is_superuser = False
                else:
                    target_user.is_staff = False
                    target_user.is_superuser = False
                target_user.save()
                messages.success(request, f"Đã cập nhật quyền cho {target_user.username}.")
            return redirect('dashboard:staff_list')

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    all_users = list(UserModel.objects.all())
    stats = {
        'total_users': len(all_users),
        'active_users': sum(1 for u in all_users if u.is_active),
        'admin_users': sum(
            1 for u in all_users
            if u.is_superuser or (has_role_field and str(getattr(u, 'role', '')).upper() == 'ADMIN')
        ),
    }

    users_qs = UserModel.objects.all()
    if search_query:
        query_filter = Q(username__icontains=search_query) | Q(email__icontains=search_query)
        if has_full_name_field:
            query_filter |= Q(full_name__icontains=search_query)
        users_qs = users_qs.filter(query_filter)

    if status_filter == 'active':
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        users_qs = users_qs.filter(is_active=False)

    order_field = 'full_name' if has_full_name_field else 'username'
    users = list(users_qs.order_by(order_field))

    role_choices = []
    if has_role_field:
        role_field_obj = UserModel._meta.get_field('role')
        if role_field_obj.choices:
            role_choices = list(role_field_obj.choices)

    context = {
        'users': users,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'has_role_field': has_role_field,
        'has_full_name_field': has_full_name_field,
        'role_choices': role_choices,
        'form_data': form_data,
    }
    return render(request, 'dashboard/staff_list.html', context)