from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone
from core.models import Order, OrderItem, ShiftReconciliation, User


def get_dashboard_overview_data(target_date=None, channel_filter=None, staff_id=None):
    if target_date is None:
        target_date = timezone.localdate()

    paid_orders = Order.objects.filter(
        order_status='Paid',
        created_time__date=target_date
    )

    if channel_filter in ('COUNTER', 'ONLINE'):
        paid_orders = paid_orders.filter(channel=channel_filter)
    if staff_id:
        paid_orders = paid_orders.filter(created_by_id=staff_id)

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
            revenue=Sum('subtotal')
        )
        .order_by('-revenue')
    )

    hourly_labels = [f"{h:02d}:00" for h in range(7, 22)]
    hourly_pos = []
    hourly_online = []
    for h in range(7, 22):
        hour_qs = paid_orders.filter(created_time__hour=h)
        pos_val = hour_qs.filter(channel='COUNTER').aggregate(s=Sum('total_amount'))['s'] or 0
        online_val = hour_qs.filter(channel='ONLINE').aggregate(s=Sum('total_amount'))['s'] or 0
        hourly_pos.append(float(pos_val))
        hourly_online.append(float(online_val))

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

    shift_reports = ShiftReconciliation.objects.filter(shift_date=target_date).select_related('receptionist')
    receptionists = User.objects.filter(role='RECEPTIONIST').order_by('full_name')

    return {
        'target_date': target_date,
        'summary': summary,
        'service_breakdown': service_breakdown,
        'hourly_labels': hourly_labels,
        'hourly_pos': hourly_pos,
        'hourly_online': hourly_online,
        'staff_reconciliation': staff_reconciliation,
        'shift_reports': shift_reports,
        'receptionists': receptionists,
        'recent_orders': paid_orders.select_related('customer', 'created_by').order_by('-created_time')[:15],
    }