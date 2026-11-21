from datetime import date, timedelta
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from core.models import OrderItem, Service

DEFAULT_TARIFF = {
    1: {'weekday': 650000, 'weekend': 780000, 'child_wd': 325000, 'child_we': 390000, 'qt_wd': 520000, 'qt_we': 624000},
    2: {'weekday': 490000, 'weekend': 588000, 'child_wd': 245000, 'child_we': 294000, 'qt_wd': 392000, 'qt_we': 470000},
    3: {'weekday': 390000, 'weekend': 468000, 'child_wd': 195000, 'child_we': 234000, 'qt_wd': 312000, 'qt_we': 374000},
}

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


def _is_weekend(target_date: date) -> bool:
    return target_date.weekday() in (5, 6)


def _serialize_service(service_obj) -> dict:
    sid = getattr(service_obj, 'service_id', None) or service_obj.pk
    idx = sid if isinstance(sid, int) else int(''.join(filter(str.isdigit, str(sid))) or 1)
    tariff = DEFAULT_TARIFF.get(idx, DEFAULT_TARIFF[3])

    status_raw = str(getattr(service_obj, 'service_status', 'Active')).strip().lower()
    is_active = status_raw == 'active'

    price_wd = getattr(service_obj, 'price_weekday', None) or getattr(service_obj, 'base_price', None) or tariff['weekday']
    price_we = getattr(service_obj, 'price_weekend', None) or int(price_wd * 1.2)

    return {
        'id': idx,
        'db_id': sid,
        'name': getattr(service_obj, 'service_name', f'Khu Onsen {idx}'),
        'cap': getattr(service_obj, 'daily_capacity', 60),
        'is_active': is_active,
        'highlights': getattr(service_obj, 'description', '') or 'Trải nghiệm tắm khoáng nóng Onsen chuẩn Nhật Bản kèm 1 suất ăn.',
        'image_url': service_obj.image.url if getattr(service_obj, 'image', None) else '',
        'price_weekday': int(price_wd),
        'price_weekend': int(price_we),
        'price_child_weekday': int(getattr(service_obj, 'price_child_weekday', None) or tariff['child_wd']),
        'price_child_weekend': int(getattr(service_obj, 'price_child_weekend', None) or tariff['child_we']),
        'price_qt_weekday': int(getattr(service_obj, 'price_qt_weekday', None) or tariff['qt_wd']),
        'price_qt_weekend': int(getattr(service_obj, 'price_qt_weekend', None) or tariff['qt_we']),
    }


def _get_all_services() -> list[dict]:
    """Lấy tất cả gói dịch vụ (cả Active lẫn Inactive) để hiển thị thông tin quảng bá."""
    qs = Service.objects.all().order_by('pk')
    return [_serialize_service(s) for s in qs]


def _get_available_qty(service_dict: dict, target_date: date) -> int:
    if not service_dict['is_active']:
        return 0
    booked = (
        OrderItem.objects.filter(
            service_id=service_dict['db_id'],
            order__visit_date=target_date,
        )
        .exclude(order__payment_status__in=['Cancelled', 'Expired', 'Đã hủy', 'Hết hạn'])
        .aggregate(total=Sum('quantity'))['total']
        or 0
    )
    return max(0, service_dict['cap'] - booked)


def home(request):
    services = _get_all_services()
    active_services = [s for s in services if s['is_active']]
    today = date.today()
    tomorrow = today + timedelta(days=1)
    min_price = min((s['price_weekday'] for s in active_services), default=390000)

    context = {
        'services': services,
        'info_pages': INFO_PAGES,
        'today_iso': today.isoformat(),
        'default_date_iso': tomorrow.isoformat(),
        'default_day_label': 'Cuối tuần (T7–CN)' if _is_weekend(tomorrow) else 'Đầu tuần (T2–T6)',
        'min_price': min_price,
    }
    return render(request, 'booking/home.html', context)


def check_availability(request):
    """API trả về toàn bộ gói dịch vụ kèm trạng thái hoạt động và tồn kho ngày khách chọn."""
    date_str = request.GET.get('date', '')
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return JsonResponse({'error': 'Vui lòng chọn ngày đi hợp lệ.'}, status=400)

    if target_date < date.today():
        return JsonResponse({'error': 'Vui lòng không chọn ngày trong quá khứ.'}, status=400)

    weekend = _is_weekend(target_date)
    results = []
    for s in _get_all_services():
        remain = _get_available_qty(s, target_date)
        results.append({
            'id': s['id'],
            'name': s['name'],
            'is_active': s['is_active'],
            'available': remain,
            'inactive_message': '' if s['is_active'] else 'Gói vé này đang tạm ngừng, hãy lựa chọn vé khác',
            'price_adult': s['price_weekend'] if weekend else s['price_weekday'],
            'price_child': s['price_child_weekend'] if weekend else s['price_child_weekday'],
            'price_qt': s['price_qt_weekend'] if weekend else s['price_qt_weekday'],
            'highlights': s['highlights'],
        })

    return JsonResponse({
        'date': target_date.isoformat(),
        'date_display': target_date.strftime('%d/%m/%Y'),
        'day_label': 'Cuối tuần (T7–CN)' if weekend else 'Đầu tuần (T2–T6)',
        'services': results,
    })


def service_calendar(request, service_id):
    services = _get_all_services()
    service = next((s for s in services if s['id'] == service_id), None)
    if not service:
        return JsonResponse({'error': 'Không tìm thấy gói dịch vụ.'}, status=404)

    weekdays_vi = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
    today = date.today()
    days = []
    for offset in range(28):
        d = today + timedelta(days=offset)
        days.append({
            'date': d.isoformat(),
            'short_date': d.strftime('%d/%m'),
            'weekday': weekdays_vi[d.weekday()],
            'available': _get_available_qty(service, d),
        })

    return JsonResponse({'service_id': service['id'], 'service_name': service['name'], 'days': days})


def onsen_detail(request, service_id):
    services = _get_all_services()
    service = next((s for s in services if s['id'] == service_id), services[0] if services else None)
    return render(request, 'booking/home.html', {
        'services': services,
        'info_pages': INFO_PAGES,
        'today_iso': date.today().isoformat(),
        'default_date_iso': (date.today() + timedelta(days=1)).isoformat(),
        'default_day_label': 'Đầu tuần (T2–T6)',
        'min_price': 390000,
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