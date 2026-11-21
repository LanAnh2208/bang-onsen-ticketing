from core.models import (
    User, Service, ServicePrice, Voucher,
    Customer, Order, OrderItem, PaymentTransaction, ShiftReconciliation
)
import json
from decimal import Decimal
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from core.decorators import role_required
from core.models import (
    User, Service, ServicePrice, Voucher,
    Customer, Order, OrderItem, PaymentTransaction
)
from .forms import InternalLoginForm, CounterCustomerForm


def _redirect_by_role(user):
    if user.role == 'ADMIN' or user.is_superuser:
        return redirect('/dashboard/')
    return redirect('/pos/')


def login_view(request):
    if request.user.is_authenticated and request.user.account_status == 'Active':
        return _redirect_by_role(request.user)

    form = InternalLoginForm(request.POST or None)
    error_message = None

    if request.method == 'POST':
        if form.is_valid():
            username = form.cleaned_data['username'].strip()
            password = form.cleaned_data['password']

            existing_user = User.objects.filter(username=username).first()
            if existing_user and existing_user.account_status != 'Active':
                error_message = 'Tài khoản của bạn đã bị khóa. Vui lòng liên hệ Quản lý.'
            else:
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    if user.role not in ('RECEPTIONIST', 'ADMIN') and not user.is_superuser:
                        error_message = 'Tài khoản không có quyền truy cập cổng nội bộ.'
                    else:
                        login(request, user)
                        messages.success(request, f'Xin chào {user.full_name or user.username}!')
                        return _redirect_by_role(user)
                else:
                    error_message = 'Tài khoản hoặc mật khẩu không chính xác.'
        else:
            error_message = 'Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.'

    return render(request, 'pos/login.html', {
        'form': form,
        'error_message': error_message,
    })


def logout_view(request):
    logout(request)
    messages.info(request, 'Bạn đã đăng xuất khỏi hệ thống nội bộ.')
    return redirect('pos:login')


def _get_remaining_capacity(service, target_date):
    sold = OrderItem.objects.filter(
        service=service,
        order__visit_date=target_date,
        order__order_status__in=['New', 'Paid']
    ).exclude(ticket_type='INFANT').aggregate(total=Sum('quantity'))['total'] or 0
    return max(0, service.daily_capacity - sold)


def _evaluate_checkin_order(order, today):
    """Đánh giá trạng thái hợp lệ của vé trước khi cho Check-in."""
    if order.order_status != 'Paid':
        return False, 'Đơn hàng chưa thanh toán hoặc đã bị hủy, không thể check-in.'
    if order.ticket_status == 'USED':
        used_time = timezone.localtime(order.checked_in_at).strftime('%H:%M %d/%m/%Y') if order.checked_in_at else ''
        return False, f'Vé này ĐÃ ĐƯỢC CHECK-IN trước đó ({used_time}). Không thể sử dụng lại.'
    if order.ticket_status == 'CANCELLED':
        return False, 'Vé này đã bị hủy.'
    if order.ticket_status == 'EXCHANGED':
        return False, 'Vé này đã được đổi sang mã vé mới. Vui lòng kiểm tra mã vé mới nhất của khách.'
    if order.visit_date != today:
        return False, f'Vé không đúng ngày sử dụng hôm nay (Ngày trên vé: {order.visit_date.strftime("%d/%m/%Y")}).'
    return True, 'Vé hợp lệ – Sẵn sàng xác nhận Check-in / Vào cổng.'


@role_required(['RECEPTIONIST', 'ADMIN'])
def counter_sale_view(request):
    today = timezone.localdate()
    day_type = ServicePrice.get_day_type_for_date(today)
    day_type_label = 'Cuối tuần (T7 – CN)' if day_type == 'WEEKEND' else 'Đầu tuần (T2 – T6)'

    services = Service.get_active_services().prefetch_related('prices')
    service_list = []
    prices_map = {}

    for svc in services:
        remaining = _get_remaining_capacity(svc, today)
        svc_prices = {
            'ADULT': {'normal': 0, 'qt': 0},
            'CHILD': {'normal': 0, 'qt': 0},
            'INFANT': {'normal': 0, 'qt': 0},
        }
        for p in svc.prices.filter(day_type=day_type):
            normal_val = float(p.price)
            qt_val = float(p.quang_tri_price) if p.quang_tri_price is not None else normal_val
            svc_prices[p.ticket_type] = {'normal': normal_val, 'qt': qt_val}

        service_list.append({
            'obj': svc,
            'remaining': remaining,
            'prices': svc_prices,
        })
        prices_map[str(svc.id)] = {
            'name': svc.service_name,
            'remaining': remaining,
            'prices': svc_prices,
        }

    active_vouchers = [v for v in Voucher.objects.filter(voucher_status='Active') if v.is_valid_today()]
    vouchers_map = {
        v.voucher_code: {
            'type': v.discount_type,
            'value': float(v.discount_value),
        } for v in active_vouchers
    }

    active_tab = request.GET.get('tab', 'sale')
    if active_tab not in ('sale', 'checkin'):
        active_tab = 'sale'

    created_order = None
    cash_received = Decimal('0')
    cash_change = Decimal('0')
    customer_form = CounterCustomerForm()

    # Biến trạng thái cho Tab Quét mã QR Check-in
    qr_query = ''
    checked_order = None
    can_checkin = False
    checkin_status_msg = ''
    qt_cccd_list = []

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'counter_sale')

        # --- NHÁNH 1: TRA CỨU MÃ VÉ QR ---
        if form_type == 'qr_lookup':
            active_tab = 'checkin'
            qr_query = request.POST.get('qr_code', '').strip()
            if not qr_query:
                messages.error(request, 'Vui lòng nhập hoặc quét mã vé QR / mã đơn hàng.')
            else:
                checked_order = (
                    Order.objects.select_related('customer', 'checked_in_by')
                    .prefetch_related('items__service')
                    .filter(Q(qr_code__iexact=qr_query) | Q(order_id__iexact=qr_query))
                    .first()
                )
                if not checked_order:
                    messages.error(request, f'Không tìm thấy vé nào khớp với mã "{qr_query}".')
                else:
                    can_checkin, checkin_status_msg = _evaluate_checkin_order(checked_order, today)
                    qt_cccd_list = [
                        it.cccd_number for it in checked_order.items.all()
                        if it.cccd_number and ServicePrice.is_quang_tri_cccd(it.cccd_number)
                    ]

        # --- NHÁNH 2: XÁC NHẬN CHECK-IN / VÀO CỔNG ---
        elif form_type == 'qr_confirm':
            active_tab = 'checkin'
            order_id = request.POST.get('order_id', '').strip()
            qr_query = order_id
            try:
                with transaction.atomic():
                    order = (
                        Order.objects.select_for_update()
                        .select_related('customer', 'checked_in_by')
                        .prefetch_related('items__service')
                        .filter(order_id=order_id)
                        .first()
                    )
                    if not order:
                        raise ValueError('Không tìm thấy đơn hàng để check-in.')

                    ok, msg = _evaluate_checkin_order(order, today)
                    if not ok:
                        checked_order = order
                        can_checkin = False
                        checkin_status_msg = msg
                        messages.error(request, msg)
                    else:
                        order.ticket_status = 'USED'
                        order.checked_in_at = timezone.now()
                        order.checked_in_by = request.user
                        order.save(update_fields=['ticket_status', 'checked_in_at', 'checked_in_by'])

                        checked_order = order
                        can_checkin = False
                        checkin_status_msg = 'Đã xác nhận Check-in thành công!'
                        qt_cccd_list = [
                            it.cccd_number for it in order.items.all()
                            if it.cccd_number and ServicePrice.is_quang_tri_cccd(it.cccd_number)
                        ]
                        messages.success(request, f'Check-in thành công cho đơn {order.order_id}!')
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Lỗi khi xác nhận check-in: {e}')

        # --- NHÁNH 3: BÁN VÉ TẠI QUẦY (POS) ---
        else:
            active_tab = 'sale'
            customer_form = CounterCustomerForm(request.POST)
            payment_method = request.POST.get('payment_method', 'CASH')
            voucher_code = request.POST.get('voucher_code', '').strip().upper()
            cart_json = request.POST.get('cart_data', '{}')
            qt_alloc_json = request.POST.get('qt_allocations', '[]')

            if payment_method not in ('CASH', 'BANK_TRANSFER'):
                messages.error(request, 'Phương thức thanh toán không hợp lệ.')
                return redirect('pos:counter_sale')

            try:
                cart_data = json.loads(cart_json)
            except json.JSONDecodeError:
                cart_data = {}

            try:
                qt_allocations = json.loads(qt_alloc_json)
            except json.JSONDecodeError:
                qt_allocations = []

            if not cart_data:
                messages.error(request, 'Vui lòng chọn ít nhất 1 vé trước khi thanh toán.')
                return redirect('pos:counter_sale')

            if not customer_form.is_valid():
                for errs in customer_form.errors.values():
                    messages.error(request, errs[0])
            else:
                c_name = customer_form.cleaned_data['customer_name'] or 'Khách lẻ tại quầy'
                c_phone = customer_form.cleaned_data['phone']
                c_cccd = customer_form.cleaned_data['cccd_number'] or None

                try:
                    with transaction.atomic():
                        customer = None
                        if c_phone:
                            customer, _ = Customer.objects.get_or_create(
                                phone=c_phone,
                                defaults={'customer_name': c_name, 'cccd_number': c_cccd}
                            )
                            if c_cccd and not customer.cccd_number:
                                customer.cccd_number = c_cccd
                                customer.save(update_fields=['cccd_number'])

                        qt_by_bucket = {}
                        seen_cccds = set()
                        for alloc in qt_allocations:
                            code = str(alloc.get('cccd', '')).strip()
                            s_id = str(alloc.get('service_id', ''))
                            t_type = str(alloc.get('ticket_type', ''))
                            if (
                                ServicePrice.is_quang_tri_cccd(code)
                                and code not in seen_cccds
                                and t_type in ('ADULT', 'CHILD')
                            ):
                                seen_cccds.add(code)
                                qt_by_bucket.setdefault((s_id, t_type), []).append(code)

                        items_to_create = []
                        subtotal_all = Decimal('0')
                        total_qty = 0

                        for svc_id_str, qty_dict in cart_data.items():
                            svc = Service.objects.select_for_update().get(pk=int(svc_id_str), service_status='Active')
                            req_paid_qty = int(qty_dict.get('ADULT', 0)) + int(qty_dict.get('CHILD', 0))
                            remaining = _get_remaining_capacity(svc, today)

                            if req_paid_qty > remaining:
                                raise ValueError(f'Gói {svc.service_name} chỉ còn {remaining} vé khả dụng hôm nay.')

                            for t_type in ('ADULT', 'CHILD'):
                                qty = int(qty_dict.get(t_type, 0))
                                if qty <= 0:
                                    continue
                                price_rule = ServicePrice.objects.filter(
                                    service=svc, ticket_type=t_type, day_type=day_type
                                ).first()
                                normal_p = price_rule.price if price_rule else Decimal('0')
                                qt_p = price_rule.quang_tri_price if (price_rule and price_rule.quang_tri_price is not None) else normal_p
                                total_qty += qty

                                assigned_cccds = qt_by_bucket.get((svc_id_str, t_type), [])[:qty]
                                for code in assigned_cccds:
                                    items_to_create.append({
                                        'service': svc,
                                        'ticket_type': t_type,
                                        'cccd_number': code,
                                        'quantity': 1,
                                        'unit_price': qt_p,
                                    })
                                    subtotal_all += qt_p

                                normal_qty = qty - len(assigned_cccds)
                                if normal_qty > 0:
                                    items_to_create.append({
                                        'service': svc,
                                        'ticket_type': t_type,
                                        'cccd_number': None,
                                        'quantity': normal_qty,
                                        'unit_price': normal_p,
                                    })
                                    subtotal_all += normal_p * normal_qty

                            infant_qty = int(qty_dict.get('INFANT', 0))
                            if infant_qty > 0:
                                total_qty += infant_qty
                                items_to_create.append({
                                    'service': svc,
                                    'ticket_type': 'INFANT',
                                    'cccd_number': None,
                                    'quantity': infant_qty,
                                    'unit_price': Decimal('0'),
                                })

                        if total_qty == 0:
                            raise ValueError('Chưa có vé nào được chọn.')

                        voucher_obj = None
                        discount_amount = Decimal('0')
                        if voucher_code:
                            voucher_obj = Voucher.objects.select_for_update().filter(voucher_code=voucher_code).first()
                            if voucher_obj and voucher_obj.is_valid_today():
                                if voucher_obj.discount_type == 'Percent':
                                    discount_amount = (subtotal_all * voucher_obj.discount_value / Decimal('100')).quantize(Decimal('1'))
                                else:
                                    discount_amount = min(subtotal_all, voucher_obj.discount_value)
                                voucher_obj.used_count += 1
                                voucher_obj.save(update_fields=['used_count'])
                            else:
                                raise ValueError(f'Mã voucher {voucher_code} không hợp lệ hoặc đã hết lượt.')

                        total_amount = max(Decimal('0'), subtotal_all - discount_amount)

                        if payment_method == 'CASH':
                            raw_cash = request.POST.get('cash_received', '0') or '0'
                            cash_received = Decimal(raw_cash)
                            if cash_received < total_amount:
                                raise ValueError('Số tiền khách đưa chưa đủ để thanh toán hóa đơn.')
                            cash_change = cash_received - total_amount

                        order = Order(
                            customer=customer,
                            channel='COUNTER',
                            total_quantity=total_qty,
                            visit_date=today,
                            voucher=voucher_obj,
                            discount_amount=discount_amount,
                            total_amount=total_amount,
                            payment_method=payment_method,
                            created_by=request.user,
                        )
                        order.issue_qr_ticket()
                        order.ticket_status = 'USED'
                        order.checked_in_at = timezone.now()
                        order.checked_in_by = request.user
                        order.save()

                        for item_data in items_to_create:
                            OrderItem.objects.create(order=order, **item_data)

                        PaymentTransaction.objects.create(
                            order=order,
                            transaction_type='INITIAL',
                            payment_method=payment_method,
                            amount=total_amount,
                            payment_status='Success',
                            completed_time=timezone.now(),
                        )

                        created_order = order
                        messages.success(request, f'Thanh toán thành công! Đã xuất vé cho đơn {order.order_id}.')
                except ValueError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    messages.error(request, f'Lỗi xử lý giao dịch: {e}')

    return render(request, 'pos/counter_sale.html', {
        'today': today,
        'day_type_label': day_type_label,
        'service_list': service_list,
        'active_vouchers': active_vouchers,
        'prices_map_json': json.dumps(prices_map),
        'vouchers_map_json': json.dumps(vouchers_map),
        'customer_form': customer_form,
        'created_order': created_order,
        'cash_received': cash_received,
        'cash_change': cash_change,
        'active_tab': active_tab,
        'qr_query': qr_query,
        'checked_order': checked_order,
        'can_checkin': can_checkin,
        'checkin_status_msg': checkin_status_msg,
        'qt_cccd_list': qt_cccd_list,
    })


@role_required(['RECEPTIONIST', 'ADMIN'])
def qr_checkin_view(request):
    return redirect('/pos/?tab=checkin')


@role_required(['RECEPTIONIST', 'ADMIN'])
def shift_reconciliation_view(request):
    today = timezone.localdate()
    now_local = timezone.localtime()
    default_shift = 'MORNING' if now_local.hour < 14 else 'EVENING'

    shift_type = request.POST.get('shift_type') or request.GET.get('shift') or default_shift
    if shift_type not in ('MORNING', 'EVENING'):
        shift_type = default_shift

    # Lấy toàn bộ đơn bán tại quầy (POS) đã thanh toán của nhân viên trong ngày hôm nay
    shift_orders = (
        Order.objects.filter(
            created_by=request.user,
            channel='COUNTER',
            order_status='Paid',
            created_time__date=today,
        )
        .select_related('customer')
        .order_by('-created_time')
    )

    cash_revenue = (
        shift_orders.filter(payment_method='CASH')
        .aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    )
    non_cash_revenue = (
        shift_orders.exclude(payment_method='CASH')
        .aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    )
    total_revenue = cash_revenue + non_cash_revenue
    total_tickets = shift_orders.aggregate(total=Sum('total_quantity'))['total'] or 0
    total_orders = shift_orders.count()

    # Kiểm tra xem nhân viên đã chốt ca này hôm nay chưa
    existing_shift = ShiftReconciliation.objects.filter(
        receptionist=request.user,
        shift_date=today,
        shift_type=shift_type,
    ).first()

    if request.method == 'POST':
        if existing_shift:
            messages.warning(request, f'Ca này đã được chốt trước đó (Mã ca: {existing_shift.shift_id}).')
            return redirect(f'/pos/shift/?shift={shift_type}')

        raw_actual = (request.POST.get('actual_cash') or '').strip()
        note = (request.POST.get('note') or '').strip()

        try:
            if raw_actual == '':
                raise ValueError('Vui lòng nhập số tiền mặt thực nhận tại quầy.')
            actual_cash = Decimal(raw_actual)
            if actual_cash < 0:
                raise ValueError('Số tiền mặt thực nhận không được nhỏ hơn 0.')

            with transaction.atomic():
                reconciliation = ShiftReconciliation.objects.create(
                    receptionist=request.user,
                    shift_date=today,
                    shift_type=shift_type,
                    actual_cash=actual_cash,
                    cash_revenue=cash_revenue,
                    non_cash_revenue=non_cash_revenue,
                    note=note,
                )

            if reconciliation.cash_variance == 0:
                messages.success(request, f'Chốt ca thành công ({reconciliation.shift_id}) – Khớp doanh thu!')
            else:
                messages.warning(
                    request,
                    f'Đã chốt ca ({reconciliation.shift_id}) với chênh lệch tiền mặt. Hệ thống đã ghi nhận cảnh báo gửi Quản lý.'
                )
            return redirect(f'/pos/shift/?shift={shift_type}')
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Không thể lưu đối soát ca: {e}')

    recent_shifts = ShiftReconciliation.objects.filter(
        receptionist=request.user
    ).order_by('-shift_date', '-reconciled_at')[:5]

    return render(request, 'pos/shift_reconciliation.html', {
        'today': today,
        'shift_type': shift_type,
        'shift_label': 'Ca sáng' if shift_type == 'MORNING' else 'Ca tối',
        'cash_revenue': cash_revenue,
        'non_cash_revenue': non_cash_revenue,
        'total_revenue': total_revenue,
        'total_tickets': total_tickets,
        'total_orders': total_orders,
        'shift_orders': shift_orders,
        'existing_shift': existing_shift,
        'recent_shifts': recent_shifts,
    })