from datetime import date, timedelta
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from core.models import OrderItem, Service, ServicePrice

INFO_PAGES = {
    'rooms': {
        'title': 'Phòng nghỉ',
        'desc': 'Deluxe, Premium, Premium Executive, Premium Grand, Junior Suite và Presidential Suite – không gian lưu trú chuẩn Nhật giữa thiên nhiên.',
    },
    'spa': {
        'title': 'Spa & Trị liệu',
        'desc': 'Massage toàn thân, chăm sóc da mặt chuyên sâu, massage tay/chân giúp phục hồi năng lượng sau khi tắm khoáng.',
    },
    'dining': {
        'title': 'Nhà hàng & Hội nghị',
        'desc': 'Bang Restaurant, An Bai Restaurant, Cay Bong Restaurant, Chuồn Restaurant, Bang Village Coffee Shop và không gian tổ chức sự kiện & hội nghị.',
    },
    'about': {
        'title': 'Giới thiệu',
        'desc': 'Khu nghỉ dưỡng suối khoáng nóng chuẩn Nhật Bản của Tập đoàn Trường Thịnh tại suối Bang – nguồn khoáng nóng tự nhiên 105°C.',
    },
    'contact': {
        'title': 'Liên hệ',
        'desc': 'Bang Onsen Spa & Resort – Suối Bang, tỉnh Quảng Trị. Hotline: 1900 8888 · Email: booking@bangonsen.vn.',
    },
}


def _fmt_vnd(amount: int) -> str:
    """Định dạng tiền tệ chuẩn dấu chấm ngăn cách hàng nghìn + đơn vị VNĐ."""
    return f"{int(amount):,}".replace(",", ".") + " VNĐ"


def _serialize_service(service_obj: Service) -> dict:
    price_map = {
        (sp.ticket_type, sp.day_type): sp
        for sp in ServicePrice.objects.filter(service=service_obj)
    }

    adult_wd = price_map.get(('ADULT', 'WEEKDAY'))
    adult_we = price_map.get(('ADULT', 'WEEKEND'))
    child_wd = price_map.get(('CHILD', 'WEEKDAY'))
    child_we = price_map.get(('CHILD', 'WEEKEND'))

    price_weekday = int(adult_wd.price) if adult_wd else 0
    price_weekend = int(adult_we.price) if adult_we else price_weekday

    price_qt_weekday = (
        int(adult_wd.quang_tri_price)
        if (adult_wd and adult_wd.quang_tri_price is not None)
        else price_weekday
    )
    price_qt_weekend = (
        int(adult_we.quang_tri_price)
        if (adult_we and adult_we.quang_tri_price is not None)
        else price_weekend
    )

    price_child_weekday = int(child_wd.price) if child_wd else int(price_weekday * 0.5)
    price_child_weekend = int(child_we.price) if child_we else int(price_weekend * 0.5)

    image_url = ''
    if service_obj.image:
        try:
            image_url = service_obj.image.url
        except ValueError:
            image_url = ''

    return {
        'id': service_obj.id,
        'service_code': service_obj.service_id,
        'name': service_obj.service_name,
        'cap': service_obj.daily_capacity,
        'is_active': (service_obj.service_status == 'Active'),
        'highlights': service_obj.description or 'Trải nghiệm tắm khoáng nóng Onsen chuẩn Nhật Bản kèm 1 suất ăn.',
        'image_url': image_url,
        'price_weekday': price_weekday,
        'price_weekend': price_weekend,
        'price_child_weekday': price_child_weekday,
        'price_child_weekend': price_child_weekend,
        'price_qt_weekday': price_qt_weekday,
        'price_qt_weekend': price_qt_weekend,
        # Chuỗi giá đã định dạng dấu chấm + VNĐ để hiển thị trực tiếp trên HTML
        'price_weekday_fmt': _fmt_vnd(price_weekday),
        'price_weekend_fmt': _fmt_vnd(price_weekend),
        'price_child_weekday_fmt': _fmt_vnd(price_child_weekday),
        'price_child_weekend_fmt': _fmt_vnd(price_child_weekend),
        'price_qt_weekday_fmt': _fmt_vnd(price_qt_weekday),
        'price_qt_weekend_fmt': _fmt_vnd(price_qt_weekend),
    }


def _get_all_services() -> list[dict]:
    return [_serialize_service(s) for s in Service.objects.all().order_by('id')]


def _get_available_qty(service_dict: dict, target_date: date) -> int:
    if not service_dict['is_active']:
        return 0

    expire_cutoff = timezone.now() - timedelta(minutes=15)
    booked = (
        OrderItem.objects.filter(
            service_id=service_dict['id'],
            order__visit_date=target_date,
        )
        .exclude(order__ticket_status='VOID')
        .filter(
            Q(order__order_status='Paid')
            | Q(order__order_status='New', order__channel='COUNTER')
            | Q(order__order_status='New', order__channel='ONLINE', order__created_time__gte=expire_cutoff)
        )
        .aggregate(total=Sum('quantity'))['total']
        or 0
    )
    return max(0, int(service_dict['cap']) - int(booked))


def home(request):
    services = _get_all_services()
    active_services = [s for s in services if s['is_active'] and s['price_weekday'] > 0]
    today = timezone.localdate()
    day_type = ServicePrice.get_day_type_for_date(today)
    min_price = min((s['price_weekday'] for s in active_services), default=390000)

    context = {
        'services': services,
        'info_pages': INFO_PAGES,
        'today_iso': today.isoformat(),
        'default_date_iso': today.isoformat(),
        'default_day_label': 'Cuối tuần (T7–CN)' if day_type == 'WEEKEND' else 'Đầu tuần (T2–T6)',
        'min_price': min_price,
        'min_price_fmt': _fmt_vnd(min_price),
    }
    return render(request, 'booking/home.html', context)


def check_availability(request):
    date_str = request.GET.get('date', '').strip()
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return JsonResponse({'error': 'Vui lòng chọn ngày đi hợp lệ.'}, status=400)

    if target_date < timezone.localdate():
        return JsonResponse({'error': 'Vui lòng không chọn ngày trong quá khứ.'}, status=400)

    day_type = ServicePrice.get_day_type_for_date(target_date)
    is_weekend = (day_type == 'WEEKEND')

    results = []
    for s in _get_all_services():
        remain = _get_available_qty(s, target_date)
        results.append({
            'id': s['id'],
            'service_code': s['service_code'],
            'name': s['name'],
            'is_active': s['is_active'],
            'max_capacity': s['cap'],
            'available': remain,
            'inactive_message': '' if s['is_active'] else 'Gói vé này đang tạm ngừng, hãy lựa chọn vé khác',
            'price_adult': s['price_weekend'] if is_weekend else s['price_weekday'],
            'price_child': s['price_child_weekend'] if is_weekend else s['price_child_weekday'],
            'price_qt': s['price_qt_weekend'] if is_weekend else s['price_qt_weekday'],
            'highlights': s['highlights'],
            'image_url': s['image_url'],
        })

    return JsonResponse({
        'date': target_date.isoformat(),
        'date_display': target_date.strftime('%d/%m/%Y'),
        'day_label': 'Cuối tuần (T7–CN)' if is_weekend else 'Đầu tuần (T2–T6)',
        'services': results,
    })


def service_calendar(request, service_id):
    """Trả về lưới lịch theo tuần (T2–CN); các ngày trước hôm nay không trả về số vé."""
    services = _get_all_services()
    service = next((s for s in services if s['id'] == service_id), None)
    if not service:
        return JsonResponse({'error': 'Không tìm thấy gói dịch vụ.'}, status=404)

    weekdays_vi = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
    today = timezone.localdate()
    start_of_week = today - timedelta(days=today.weekday())
    end_date = today + timedelta(days=27)
    end_of_grid = end_date + timedelta(days=(6 - end_date.weekday()))

    days = []
    cur = start_of_week
    while cur <= end_of_grid:
        is_past = cur < today
        days.append({
            'date': cur.isoformat(),
            'short_date': cur.strftime('%d/%m'),
            'weekday': weekdays_vi[cur.weekday()],
            'is_past': is_past,
            'available': None if is_past else _get_available_qty(service, cur),
        })
        cur += timedelta(days=1)

    return JsonResponse({
        'service_id': service['id'],
        'service_name': service['name'],
        'today_iso': today.isoformat(),
        'days': days,
    })


def onsen_detail(request, service_id):
    services = _get_all_services()
    service = next((s for s in services if s['id'] == service_id), services[0] if services else None)
    today = timezone.localdate()
    day_type = ServicePrice.get_day_type_for_date(today)
    return render(request, 'booking/home.html', {
        'services': services,
        'info_pages': INFO_PAGES,
        'today_iso': today.isoformat(),
        'default_date_iso': today.isoformat(),
        'default_day_label': 'Cuối tuần (T7–CN)' if day_type == 'WEEKEND' else 'Đầu tuần (T2–T6)',
        'min_price': 390000,
        'min_price_fmt': _fmt_vnd(390000),
        'selected_detail': service,
    })


def book_form(request):
    return redirect('/#flt')


def lookup_ticket(request):
    return redirect('/#faq-title')


def info_page(request, slug):
    return redirect('/#eco-sec')


def staff_login_redirect(request):
    return redirect('/admin/')