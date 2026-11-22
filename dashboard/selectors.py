import calendar
from datetime import date
from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone
from core.models import Order, OrderItem, ShiftReconciliation, User

MORNING_START_HOUR = 7
MORNING_END_HOUR = 13   # Ca sáng: 07:00 - 12:59
EVENING_END_HOUR = 22   # Ca tối: 13:00 - 21:59


def _shift_time_q(shift_filter):
    if shift_filter == 'MORNING':
        return Q(created_time__hour__gte=MORNING_START_HOUR, created_time__hour__lt=MORNING_END_HOUR)
    if shift_filter == 'EVENING':
        return Q(created_time__hour__gte=MORNING_END_HOUR, created_time__hour__lt=EVENING_END_HOUR)
    return Q()


def _resolve_period_range(period='day', target_date=None, month=None, quarter=None, year=None):
    today = timezone.localdate()
    base_date = target_date or today
    yr = year or base_date.year
    mo = month or base_date.month
    qt = quarter or ((base_date.month - 1) // 3 + 1)

    if period == 'month':
        last_day = calendar.monthrange(yr, mo)[1]
        start_date = date(yr, mo, 1)
        end_date = date(yr, mo, last_day)
        label = f"Tháng {mo:02d}/{yr}"
    elif period == 'quarter':
        start_month = (qt - 1) * 3 + 1
        end_month = start_month + 2
        last_day = calendar.monthrange(yr, end_month)[1]
        start_date = date(yr, start_month, 1)
        end_date = date(yr, end_month, last_day)
        label = f"Quý {qt}/{yr}"
    elif period == 'year':
        start_date = date(yr, 1, 1)
        end_date = date(yr, 12, 31)
        label = f"Năm {yr}"
    else:
        period = 'day'
        start_date = base_date
        end_date = base_date
        label = f"Ngày {base_date.strftime('%d/%m/%Y')}"

    return {
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'year': yr,
        'month': mo,
        'quarter': qt,
        'period_label': label,
    }


def get_dashboard_overview_data(
    target_date=None,
    channel_filter=None,
    staff_id=None,
    period='day',
    shift_filter='',
    month=None,
    quarter=None,
    year=None,
):
    if target_date is None:
        target_date = timezone.localdate()

    period_info = _resolve_period_range(
        period=period,
        target_date=target_date,
        month=month,
        quarter=quarter,
        year=year,
    )

    paid_orders = Order.objects.filter(
        order_status='Paid',
        created_time__date__gte=period_info['start_date'],
        created_time__date__lte=period_info['end_date'],
    )

    if channel_filter in ('COUNTER', 'ONLINE'):
        paid_orders = paid_orders.filter(channel=channel_filter)
    if staff_id:
        paid_orders = paid_orders.filter(created_by_id=staff_id)
    if shift_filter in ('MORNING', 'EVENING'):
        paid_orders = paid_orders.filter(_shift_time_q(shift_filter))

    summary = paid_orders.aggregate(
        total_revenue=Sum('total_amount'),
        total_tickets=Sum('total_quantity'),
        total_orders=Count('id'),
        online_revenue=Sum('total_amount', filter=Q(channel='ONLINE')),
        pos_revenue=Sum('total_amount', filter=Q(channel='COUNTER')),
        cash_revenue=Sum('total_amount', filter=Q(payment_method='CASH')),
        non_cash_revenue=Sum('total_amount', filter=~Q(payment_method='CASH')),
    )

    for key in summary:
        if summary[key] is None:
            summary[key] = Decimal('0') if 'revenue' in key else 0

    service_breakdown = (
        OrderItem.objects.filter(order__in=paid_orders)
        .values('service__service_id', 'service__service_name')
        .annotate(
            tickets_sold=Sum('quantity'),
            revenue=Sum('subtotal'),
        )
        .order_by('-revenue')
    )

    chart_labels = []
    chart_pos = []
    chart_online = []

    if period_info['period'] == 'day':
        chart_title = f"Biểu đồ doanh thu theo khung giờ ({period_info['period_label']})"
        for h in range(MORNING_START_HOUR, EVENING_END_HOUR):
            chart_labels.append(f"{h:02d}:00")
            hour_qs = paid_orders.filter(created_time__hour=h)
            pos_val = hour_qs.filter(channel='COUNTER').aggregate(s=Sum('total_amount'))['s'] or 0
            online_val = hour_qs.filter(channel='ONLINE').aggregate(s=Sum('total_amount'))['s'] or 0
            chart_pos.append(float(pos_val))
            chart_online.append(float(online_val))
    elif period_info['period'] in ('year', 'quarter'):
        chart_title = f"Biểu đồ doanh thu theo tháng ({period_info['period_label']})"
        start_m = 1 if period_info['period'] == 'year' else (period_info['quarter'] - 1) * 3 + 1
        end_m = 12 if period_info['period'] == 'year' else start_m + 2
        for m in range(start_m, end_m + 1):
            chart_labels.append(f"T{m:02d}")
            month_qs = paid_orders.filter(created_time__year=period_info['year'], created_time__month=m)
            pos_val = month_qs.filter(channel='COUNTER').aggregate(s=Sum('total_amount'))['s'] or 0
            online_val = month_qs.filter(channel='ONLINE').aggregate(s=Sum('total_amount'))['s'] or 0
            chart_pos.append(float(pos_val))
            chart_online.append(float(online_val))
    else:
        chart_title = f"Biểu đồ doanh thu theo ngày ({period_info['period_label']})"
        days_in_month = calendar.monthrange(period_info['year'], period_info['month'])[1]
        for d in range(1, days_in_month + 1):
            chart_labels.append(f"{d:02d}/{period_info['month']:02d}")
            day_qs = paid_orders.filter(
                created_time__year=period_info['year'],
                created_time__month=period_info['month'],
                created_time__day=d,
            )
            pos_val = day_qs.filter(channel='COUNTER').aggregate(s=Sum('total_amount'))['s'] or 0
            online_val = day_qs.filter(channel='ONLINE').aggregate(s=Sum('total_amount'))['s'] or 0
            chart_pos.append(float(pos_val))
            chart_online.append(float(online_val))

    staff_reconciliation = (
        paid_orders.filter(channel='COUNTER')
        .values('created_by__account_id', 'created_by__full_name', 'created_by__username')
        .annotate(
            order_count=Count('id'),
            ticket_count=Sum('total_quantity'),
            cash_total=Sum('total_amount', filter=Q(payment_method='CASH')),
            transfer_total=Sum('total_amount', filter=Q(payment_method='BANK_TRANSFER')),
            card_ewallet_total=Sum('total_amount', filter=Q(payment_method__in=['CARD', 'E_WALLET'])),
            total_collected=Sum('total_amount'),
        )
        .order_by('-total_collected')
    )

    shift_qs = ShiftReconciliation.objects.filter(
        shift_date__gte=period_info['start_date'],
        shift_date__lte=period_info['end_date'],
    ).select_related('receptionist')

    if shift_filter in ('MORNING', 'EVENING'):
        shift_qs = shift_qs.filter(shift_type=shift_filter)
    if staff_id:
        shift_qs = shift_qs.filter(receptionist_id=staff_id)

    shift_reports = shift_qs.order_by('-shift_date', 'shift_type')
    receptionists = User.objects.filter(role='RECEPTIONIST').order_by('full_name')

    return {
        'target_date': target_date,
        'period_info': period_info,
        'chart_title': chart_title,
        'summary': summary,
        'service_breakdown': service_breakdown,
        'hourly_labels': chart_labels,
        'hourly_pos': chart_pos,
        'hourly_online': chart_online,
        'staff_reconciliation': staff_reconciliation,
        'shift_reports': shift_reports,
        'receptionists': receptionists,
        'recent_orders': paid_orders.select_related('customer', 'created_by').order_by('-created_time')[:15],
    }