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


def _parse_decimal_or_none(raw_value):
    cleaned = (raw_value or '').strip().replace(',', '')
    if cleaned == '':
        return None
    try:
        from decimal import Decimal
        val = Decimal(cleaned)
        return val if val >= 0 else None
    except Exception:
        return None


def _upsert_service_price(request, service, ticket_type, day_type, price_val, qt_price_val=None):
    if price_val is None and qt_price_val is None:
        return

    existing = ServicePrice.objects.filter(
        service=service,
        ticket_type=ticket_type,
        day_type=day_type,
    ).first()

    if existing:
        old_price = existing.price
        old_qt = existing.quang_tri_price
        next_price = price_val if price_val is not None else old_price
        next_qt = qt_price_val if qt_price_val is not None else old_qt

        if next_price != old_price or next_qt != old_qt:
            existing.price = next_price
            existing.quang_tri_price = next_qt
            existing.save()
            if getattr(request.user, 'is_authenticated', False):
                PriceAuditLog.objects.create(
                    service_price=existing,
                    old_price=old_price,
                    new_price=next_price,
                    old_quang_tri_price=old_qt,
                    new_quang_tri_price=next_qt,
                    changed_by=request.user,
                )
    else:
        created_price = ServicePrice.objects.create(
            service=service,
            ticket_type=ticket_type,
            day_type=day_type,
            price=price_val if price_val is not None else 0,
            quang_tri_price=qt_price_val,
        )
        if getattr(request.user, 'is_authenticated', False):
            PriceAuditLog.objects.create(
                service_price=created_price,
                old_price=0,
                new_price=created_price.price,
                old_quang_tri_price=None,
                new_quang_tri_price=created_price.quang_tri_price,
                changed_by=request.user,
            )


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
        action = (request.POST.get('action') or '').strip()

        if action == 'add_service':
            service_form = ServiceForm(request.POST)
            if service_form.is_valid():
                created_service = service_form.save()

                # Lưu đa đối tượng & đa khung ngày (nếu có nhập)
                price_entries = [
                    (
                        'ADULT',
                        'WEEKDAY',
                        _parse_decimal_or_none(request.POST.get('weekday_adult_price')),
                        _parse_decimal_or_none(request.POST.get('weekday_quang_tri_price')),
                    ),
                    (
                        'CHILD',
                        'WEEKDAY',
                        _parse_decimal_or_none(request.POST.get('weekday_child_price')),
                        None,
                    ),
                    (
                        'ADULT',
                        'WEEKEND',
                        _parse_decimal_or_none(request.POST.get('weekend_adult_price')),
                        _parse_decimal_or_none(request.POST.get('weekend_quang_tri_price')),
                    ),
                    (
                        'CHILD',
                        'WEEKEND',
                        _parse_decimal_or_none(request.POST.get('weekend_child_price')),
                        None,
                    ),
                ]

                has_any_price = False
                for t_type, d_type, p_val, qt_val in price_entries:
                    if p_val is not None or qt_val is not None:
                        _upsert_service_price(request, created_service, t_type, d_type, p_val, qt_val)
                        has_any_price = True

                # Tương thích ngược nếu có gửi field cũ
                legacy_price = _parse_decimal_or_none(request.POST.get('initial_price'))
                legacy_qt = _parse_decimal_or_none(request.POST.get('initial_quang_tri_price'))
                if legacy_price is not None or legacy_qt is not None:
                    legacy_ticket = request.POST.get('initial_ticket_type') or 'ADULT'
                    legacy_day = request.POST.get('initial_day_type') or 'WEEKDAY'
                    _upsert_service_price(request, created_service, legacy_ticket, legacy_day, legacy_price, legacy_qt)
                    has_any_price = True

                if has_any_price:
                    messages.success(
                        request,
                        f"Đã lưu gói dịch vụ '{created_service.service_name}' và cập nhật bảng giá thành công."
                    )
                else:
                    messages.success(
                        request,
                        f"Đã lưu gói dịch vụ '{created_service.service_name}' thành công."
                    )
                return redirect('dashboard:pricing_matrix')
            else:
                messages.error(request, "Lỗi nhập liệu gói dịch vụ. Vui lòng kiểm tra lại mã gói hoặc thông tin.")

        elif action == 'toggle_service':
            target_id = request.POST.get('service_pk') or request.POST.get('service_id')
            srv = get_object_or_404(Service, pk=target_id)
            current_status = (srv.service_status or '').strip().lower()
            is_currently_active = current_status in ('active', 'đang kinh doanh', '1', 'true')
            srv.service_status = 'Inactive' if is_currently_active else 'Active'
            srv.save()

            status_label = "tạm ngưng" if srv.service_status == 'Inactive' else "mở bán lại"
            messages.success(request, f"Đã {status_label} gói dịch vụ '{srv.service_name}'.")
            return redirect('dashboard:pricing_matrix')

        elif action == 'edit_service':
            target_id = request.POST.get('service_pk') or request.POST.get('service_id_pk')
            srv = get_object_or_404(Service, pk=target_id)

            new_service_id = (request.POST.get('service_id') or '').strip()
            new_service_name = (request.POST.get('service_name') or '').strip()
            new_description = (request.POST.get('description') or '').strip()
            new_status = (request.POST.get('service_status') or srv.service_status or 'Active').strip()
            raw_capacity = (request.POST.get('daily_capacity') or '').strip()

            try:
                new_capacity = int(raw_capacity)
                if new_capacity < 1:
                    raise ValueError()
            except ValueError:
                messages.error(request, "Sức chứa vé / ngày phải là số nguyên lớn hơn 0.")
                return redirect('dashboard:pricing_matrix')

            if not new_service_id or not new_service_name:
                messages.error(request, "Mã gói dịch vụ và tên gói dịch vụ không được để trống.")
                return redirect('dashboard:pricing_matrix')

            if Service.objects.exclude(pk=srv.pk).filter(service_id__iexact=new_service_id).exists():
                messages.error(request, f"Mã gói '{new_service_id}' đã được sử dụng bởi gói dịch vụ khác.")
                return redirect('dashboard:pricing_matrix')

            srv.service_id = new_service_id
            srv.service_name = new_service_name
            srv.daily_capacity = new_capacity
            srv.description = new_description
            srv.service_status = new_status
            srv.save()

            updated_price_val = _parse_decimal_or_none(request.POST.get('price'))
            if updated_price_val is not None:
                edit_ticket_type = request.POST.get('ticket_type') or 'ADULT'
                edit_day_type = request.POST.get('day_type') or 'WEEKDAY'
                _upsert_service_price(request, srv, edit_ticket_type, edit_day_type, updated_price_val)

            messages.success(request, f"Đã cập nhật gói dịch vụ '{srv.service_name}' thành công.")
            return redirect('dashboard:pricing_matrix')

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