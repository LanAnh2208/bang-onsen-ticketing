import os
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, quote, quote_plus, urlencode, urlparse
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import (
    Customer,
    Order,
    OrderItem,
    PaymentTransaction,
    Service,
    ServicePrice,
    Voucher,
)

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

DEFAULT_VOUCHERS = {
    'ONSEN10': {'type': 'PERCENT', 'value': 10, 'max_discount': 200000, 'label': 'Giảm 10% tối đa 200.000 VNĐ'},
    'BANG50K': {'type': 'FIXED', 'value': 50000, 'max_discount': 50000, 'label': 'Giảm trực tiếp 50.000 VNĐ'},
    'CHAOBAN': {'type': 'FIXED', 'value': 30000, 'max_discount': 30000, 'label': 'Ưu đãi khách hàng mới 30.000 VNĐ'},
}

PAYMENT_METHOD_LABELS = {
    'CASH': 'Tiền mặt tại quầy',
    'BANK_TRANSFER': 'Chuyển khoản ngân hàng / VietQR',
    'CARD': 'Thẻ ATM nội địa / Visa / Mastercard',
    'E_WALLET': 'Cổng thanh toán VNPAY',
}

ONSEN_DETAIL_PRESETS = {
    1: {
        'summary': '07 bể ngâm khoáng trong nhà · 01 phòng xông hơi tinh dầu · 01 xông hơi khô · 05 bể Onsen ngoài trời · 1 suất ăn Menu Nhật Bản',
        'description': (
            'Gói dịch vụ Onsen 1 mang đến hành trình tắm khoáng trị liệu chuẩn Nhật Bản trọn vẹn nhất tại Bang Onsen Spa & Resort. '
            'Quý khách được tận hưởng toàn bộ hệ thống bể khoáng nóng phân tầng nhiệt độ trong nhà, bể ngâm ngoài trời giữa rừng nguyên sinh, '
            'khu xông hơi tinh dầu – xông khô và thưởng thức 01 suất ăn Set Menu Nhật Bản tinh tế.'
        ),
        'highlights': [
            '07 bể ngâm khoáng trong nhà phân tầng nhiệt độ trị liệu',
            '01 phòng xông hơi tinh dầu thảo mộc tự nhiên',
            '01 phòng xông hơi khô chuẩn Nhật Bản',
            '05 bể Onsen ngoài trời hòa mình giữa thiên nhiên suối Bang',
            '01 suất ăn Set Menu Nhật Bản tại nhà hàng khu nghỉ dưỡng',
        ],
        'fallback_photos': [
            ('images/home/onsen-1.jpg', 'Không gian tắm khoáng Onsen 1'),
            ('images/home/gal-2.jpg', 'Bể Onsen ngoài trời giữa thiên nhiên'),
            ('images/home/gal-6.jpg', 'Suất ăn Set Menu Nhật Bản đi kèm'),
        ],
    },
    2: {
        'summary': '07 bể ngâm khoáng trong nhà · 05 bể Onsen ngoài trời · 01 phòng xông hơi đá muối & tinh dầu · Tự do tham quan vườn Nhật',
        'description': (
            'Gói dịch vụ Onsen 2 được thiết kế dành cho du khách muốn tập trung trải nghiệm trị liệu khoáng nóng tự nhiên 105°C và thư giãn xông hơi chuyên sâu. '
            'Quý khách tự do sử dụng toàn bộ khu tắm khoáng trong nhà, bể khoáng ngoài trời và phòng xông hơi trị liệu trong suốt khung giờ mở cửa.'
        ),
        'highlights': [
            '07 bể ngâm khoáng nóng trong nhà nhiều mức nhiệt độ',
            '05 bể Onsen ngoài trời thoáng đãng giữa núi rừng Quảng Trị',
            '01 phòng xông hơi đá muối Himalaya & xông hơi tinh dầu',
            'Miễn phí khăn tắm, tủ đồ cá nhân & trà thảo mộc nghỉ chân',
            'Tự do tham quan, check-in kiến trúc vườn Nhật tại Bang Onsen',
        ],
        'fallback_photos': [
            ('images/home/onsen-2.jpg', 'Khu tắm khoáng Onsen 2'),
            ('images/home/gal-4.jpg', 'Hệ thống bể ngâm khoáng trong nhà'),
            ('images/home/gal-3.jpg', 'Phòng xông hơi đá muối & tinh dầu'),
        ],
    },
    3: {
        'summary': 'Công viên nước khoáng nóng ngoài trời · Hệ thống bể khoáng ấm gia đình · Khu trượt nước & vận động dưới nước',
        'description': (
            'Gói dịch vụ Onsen 3 kết hợp tắm khoáng ấm ngoài trời cùng khu công viên nước khoáng sôi động, đặc biệt phù hợp cho gia đình có trẻ nhỏ và nhóm bạn trẻ. '
            'Nguồn nước khoáng tự nhiên được điều chỉnh nhiệt độ lý tưởng cho hoạt động vui chơi, giải nhiệt và phục hồi năng lượng.'
        ),
        'highlights': [
            'Trải nghiệm toàn khu Công viên nước khoáng nóng ngoài trời',
            'Hệ thống bể ngâm khoáng ấm ngoài trời dành cho cả gia đình',
            'Khu máng trượt nước & trò chơi vận động dưới nước khoáng',
            'Tủ đồ cá nhân, khăn tắm & khu vực ghế nghỉ ven hồ tiêu chuẩn',
        ],
        'fallback_photos': [
            ('images/home/onsen-3.jpg', 'Công viên nước khoáng Onsen 3'),
            ('images/home/gal-5.jpg', 'Khu vui chơi nước khoáng ngoài trời'),
            ('images/home/gal-1.jpg', 'Toàn cảnh không gian suối Bang'),
        ],
    },
}


def _fmt_vnd(amount: int) -> str:
    return f"{int(amount):,}".replace(",", ".") + " VNĐ"


def _resolve_back_lookup(request, default_query: str) -> tuple[str, str]:
    """Xác định từ khóa tra cứu trước đó (SĐT, Email hoặc Mã đơn) và URL quay lại trang tra cứu."""
    back_q = (request.GET.get('q') or request.POST.get('back_q') or '').strip()
    if not back_q:
        referer = request.META.get('HTTP_REFERER', '')
        if referer:
            ref_q = parse_qs(urlparse(referer).query).get('q', [])
            if ref_q:
                back_q = ref_q[0].strip()
    if not back_q:
        back_q = (default_query or '').strip()
    back_lookup_url = f"{reverse('booking:lookup_ticket')}?{urlencode({'q': back_q})}"
    return back_q, back_lookup_url


# ==============================================================================
# CÁC HÀM XỬ LÝ CỔNG THANH TOÁN VNPAY SANDBOX & GỬI EMAIL VÉ QR
# ==============================================================================
def _get_client_ip(request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or '127.0.0.1'


def _hmac_sha512(secret_key: str, data_str: str) -> str:
    return hmac.new(
        secret_key.encode('utf-8'),
        data_str.encode('utf-8'),
        hashlib.sha512,
    ).hexdigest()


def _build_vnpay_payment_url(request, order_obj: Order, txn_obj: PaymentTransaction) -> str:
    """Tạo URL thanh toán VNPAY v2.1.0 kèm chữ ký HMAC-SHA512."""
    now_local = timezone.localtime()
    expire_local = now_local + timedelta(minutes=15)
    return_url = request.build_absolute_uri(reverse('booking:vnpay_return'))

    vnp_params = {
        'vnp_Version': '2.1.0',
        'vnp_Command': 'pay',
        'vnp_TmnCode': settings.VNPAY_TMN_CODE,
        'vnp_Amount': str(int(txn_obj.amount) * 100),
        'vnp_CurrCode': 'VND',
        'vnp_TxnRef': txn_obj.transaction_id,
        'vnp_OrderInfo': f"Thanh toan ve Bang Onsen {order_obj.order_id}",
        'vnp_OrderType': 'other',
        'vnp_Locale': 'vn',
        'vnp_ReturnUrl': return_url,
        'vnp_IpAddr': _get_client_ip(request),
        'vnp_CreateDate': now_local.strftime('%Y%m%d%H%M%S'),
        'vnp_ExpireDate': expire_local.strftime('%Y%m%d%H%M%S'),
    }

    sorted_items = sorted(vnp_params.items())
    query_string = '&'.join(f"{k}={quote_plus(str(v))}" for k, v in sorted_items)
    secure_hash = _hmac_sha512(settings.VNPAY_HASH_SECRET.strip(), query_string)
    return f"{settings.VNPAY_PAYMENT_URL}?{query_string}&vnp_SecureHash={secure_hash}"


def _verify_vnpay_signature(query_params) -> bool:
    """Kiểm tra tính toàn vẹn chữ ký vnp_SecureHash từ VNPAY gửi về."""
    received_hash = (query_params.get('vnp_SecureHash') or '').strip()
    if not received_hash:
        return False

    filtered = {}
    for k, v in query_params.items():
        if k.startswith('vnp_') and k not in ('vnp_SecureHash', 'vnp_SecureHashType') and v != '':
            filtered[k] = v

    sorted_items = sorted(filtered.items())
    hash_data = '&'.join(f"{k}={quote_plus(str(v))}" for k, v in sorted_items)
    expected_hash = _hmac_sha512(settings.VNPAY_HASH_SECRET.strip(), hash_data)
    return hmac.compare_digest(expected_hash.lower(), received_hash.lower())


def _send_qr_ticket_email(order_obj: Order, request=None) -> bool:
    """Gửi vé điện tử kèm mã QR tới email khách hàng đã đăng ký."""
    customer = order_obj.customer
    if not customer or not customer.email:
        return False

    qr_payload = order_obj.qr_code or order_obj.order_id
    qr_img_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={quote(qr_payload)}"
    lookup_path = f"{reverse('booking:lookup_ticket')}?q={order_obj.order_id}"
    lookup_url = request.build_absolute_uri(lookup_path) if request else f"http://127.0.0.1:8000{lookup_path}"
    visit_disp = order_obj.visit_date.strftime('%d/%m/%Y')
    total_disp = _fmt_vnd(int(order_obj.total_amount))

    items_html = ''
    for it in order_obj.items.select_related('service').all():
        items_html += (
            f"<li><b>{it.service.service_name}</b> – {it.get_ticket_type_display()} "
            f"× {it.quantity} vé ({_fmt_vnd(int(it.subtotal))})</li>"
        )

    subject = f"[Bang Onsen] Vé điện tử & Mã QR check-in – Đơn #{order_obj.order_id}"
    text_body = (
        f"Xin chào {customer.customer_name},\n\n"
        f"Cảm ơn quý khách đã xác nhận vé dịch vụ tại Bang Onsen Spa & Resort.\n"
        f"- Mã đơn hàng: {order_obj.order_id}\n"
        f"- Mã vé điện tử: {order_obj.ticket_id}\n"
        f"- Mã QR check-in: {qr_payload}\n"
        f"- Ngày sử dụng: {visit_disp}\n"
        f"- Tổng thanh toán: {total_disp}\n\n"
        f"Tra cứu vé trực tuyến tại: {lookup_url}\n"
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e3e8ec;border-radius:12px;padding:24px;color:#1e293b">
      <h2 style="color:#b91c1c;margin-top:0">BANG ONSEN SPA & RESORT</h2>
      <p>Xin chào <b>{customer.customer_name}</b>,</p>
      <p>Đơn đặt vé của quý khách đã được xác nhận thành công. Vui lòng xuất trình mã QR bên dưới tại quầy check-in:</p>
      <div style="text-align:center;background:#f8fafc;padding:18px;border-radius:10px;margin:16px 0">
        <img src="{qr_img_url}" alt="Mã QR vé {order_obj.order_id}" width="200" height="200" style="display:block;margin:0 auto 10px">
        <div style="font-size:15px;font-weight:bold;color:#0f172a">Mã vé: {order_obj.ticket_id}</div>
        <div style="font-size:13px;color:#475569">Mã QR: {qr_payload}</div>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:14px">
        <tr><td style="padding:6px 0;color:#64748b">Mã đơn hàng:</td><td style="padding:6px 0;font-weight:bold">{order_obj.order_id}</td></tr>
        <tr><td style="padding:6px 0;color:#64748b">Ngày sử dụng:</td><td style="padding:6px 0;font-weight:bold">{visit_disp}</td></tr>
        <tr><td style="padding:6px 0;color:#64748b">Tổng thanh toán:</td><td style="padding:6px 0;font-weight:bold;color:#b91c1c">{total_disp}</td></tr>
      </table>
      <p style="font-size:14px;margin-bottom:6px"><b>Chi tiết gói dịch vụ:</b></p>
      <ul style="font-size:14px;padding-left:20px;margin-top:0">{items_html}</ul>
      <p style="margin-top:18px">
        <a href="{lookup_url}" style="display:inline-block;background:#b91c1c;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:bold">
          Xem & Quản lý vé trực tuyến
        </a>
      </p>
    </div>
    """

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[customer.email],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send(fail_silently=False)
        return True
    except Exception:
        return False


# ==============================================================================
# CÁC HÀM DỊCH VỤ, GIÁ VÉ & KIỂM TRA TỒN KHO
# ==============================================================================
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
        .exclude(ticket_type='INFANT')
        .exclude(order__ticket_status='VOID')
        .exclude(order__order_status__in=['Cancelled', 'Exchanged'])
        .filter(
            Q(order__order_status='Paid')
            | Q(order__order_status='New', order__channel='COUNTER')
            | Q(order__order_status='New', order__channel='ONLINE', order__created_time__gte=expire_cutoff)
        )
        .aggregate(total=Sum('quantity'))['total']
        or 0
    )
    return max(0, int(service_dict['cap']) - int(booked))


def _evaluate_voucher(code: str, subtotal: int) -> dict:
    clean_code = (code or '').strip().upper()
    if not clean_code:
        return {'valid': False, 'message': 'Vui lòng nhập mã ưu đãi.'}

    v_obj = Voucher.objects.filter(voucher_code__iexact=clean_code).first()
    if v_obj:
        if not v_obj.is_valid_today():
            return {
                'valid': False,
                'message': 'Mã giảm giá đã hết hạn, hết lượt sử dụng hoặc không còn hiệu lực.',
            }

        if v_obj.discount_type == 'Percent':
            pct = float(v_obj.discount_value)
            discount = min(subtotal, int(round(subtotal * pct / 100)))
            return {
                'valid': True,
                'voucher_id': v_obj.id,
                'code': v_obj.voucher_code,
                'discount': discount,
                'discount_type': 'PERCENT',
                'discount_value': pct,
                'max_discount': 0,
                'label': f'Áp dụng thành công mã {v_obj.voucher_code} (-{pct:g}%)',
            }

        val = int(v_obj.discount_value)
        discount = min(subtotal, val)
        return {
            'valid': True,
            'voucher_id': v_obj.id,
            'code': v_obj.voucher_code,
            'discount': discount,
            'discount_type': 'FIXED',
            'discount_value': val,
            'max_discount': val,
            'label': f'Áp dụng thành công mã {v_obj.voucher_code} (-{_fmt_vnd(val)})',
        }

    rule = DEFAULT_VOUCHERS.get(clean_code)
    if not rule:
        return {'valid': False, 'message': 'Mã giảm giá không tồn tại hoặc đã hết hạn.'}

    if rule['type'] == 'PERCENT':
        discount = min(rule['max_discount'], int(subtotal * rule['value'] / 100))
    else:
        discount = min(subtotal, rule['value'])

    return {
        'valid': True,
        'voucher_id': None,
        'code': clean_code,
        'discount': discount,
        'discount_type': rule['type'],
        'discount_value': rule['value'],
        'max_discount': rule['max_discount'],
        'label': rule['label'],
    }


def _calculate_inherited_discount(order_obj: Order, new_subtotal: int) -> dict:
    """
    Tính toán ưu đãi kế thừa từ đơn cũ khi đổi vé:
    - Nếu đơn cũ có Voucher: kế thừa nguyên tỷ lệ (%) hoặc mức giảm cố định (VNĐ) của đơn cũ,
      không hoàn mã về kho, không cho phép áp thêm hay đổi sang mã khác.
    - Nếu đơn cũ không có mã giảm giá: mức giảm = 0, không cho phép nhập mã mới.
    """
    old_discount = int(order_obj.discount_amount or 0)
    v_obj = order_obj.voucher

    if v_obj:
        if v_obj.discount_type == 'Percent':
            pct = float(v_obj.discount_value)
            discount = min(new_subtotal, int(round(new_subtotal * pct / 100.0)))
            max_disc = int(getattr(v_obj, 'max_discount', 0) or 0)
            if max_disc > 0:
                discount = min(discount, max_disc)
            return {
                'has_voucher': True,
                'code': v_obj.voucher_code,
                'type': 'PERCENT',
                'value': pct,
                'max_discount': max_disc,
                'fixed_discount': 0,
                'discount_amount': discount,
                'short_badge': f"{v_obj.voucher_code} (-{pct:g}%)",
                'row_label': f"Giảm giá kế thừa ({v_obj.voucher_code} -{pct:g}%)",
            }

        val = int(v_obj.discount_value)
        discount = min(new_subtotal, val)
        return {
            'has_voucher': True,
            'code': v_obj.voucher_code,
            'type': 'FIXED',
            'value': float(val),
            'max_discount': val,
            'fixed_discount': val,
            'discount_amount': discount,
            'short_badge': f"{v_obj.voucher_code} (-{_fmt_vnd(val)})",
            'row_label': f"Giảm giá kế thừa ({v_obj.voucher_code})",
        }

    if old_discount > 0:
        discount = min(new_subtotal, old_discount)
        return {
            'has_voucher': True,
            'code': 'ƯU ĐÃI ĐƠN CŨ',
            'type': 'FIXED',
            'value': float(old_discount),
            'max_discount': old_discount,
            'fixed_discount': old_discount,
            'discount_amount': discount,
            'short_badge': f"Ưu đãi đơn cũ (-{_fmt_vnd(old_discount)})",
            'row_label': "Giảm giá kế thừa từ đơn cũ",
        }

    return {
        'has_voucher': False,
        'code': '',
        'type': 'NONE',
        'value': 0.0,
        'max_discount': 0,
        'fixed_discount': 0,
        'discount_amount': 0,
        'short_badge': '',
        'row_label': '',
    }


# ==============================================================================
# CÁC VIEW TRANG CHỦ, CHI TIẾT ONSEN, ĐẶT VÉ & THANH TOÁN VNPAY
# ==============================================================================
def _fresh_static_url(rel_path: str) -> str:
    """
    Đọc trực tiếp file ảnh từ thư mục static và gắn ?v=<mtime> theo thời điểm lưu file thực tế
    để trình duyệt luôn tải ảnh mới nhất khi lưu đè file trong thư mục, không dùng cache cũ.
    """
    base_no_ext, orig_ext = os.path.splitext(rel_path)
    exts = [orig_ext] if orig_ext else []
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        if ext.lower() not in [e.lower() for e in exts]:
            exts.append(ext)

    candidates = []
    for ext in exts:
        cand_rel = f"{base_no_ext}{ext}"
        abs_path = finders.find(cand_rel)
        if not abs_path:
            direct_path = os.path.join(settings.BASE_DIR, 'static', *cand_rel.split('/'))
            if os.path.isfile(direct_path):
                abs_path = direct_path
        if abs_path and os.path.isfile(abs_path):
            try:
                mtime = int(os.path.getmtime(abs_path))
            except OSError:
                mtime = 0
            candidates.append((mtime, cand_rel))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        newest_mtime, newest_rel = candidates[0]
        return f"{static(newest_rel)}?v={newest_mtime}"

    return static(rel_path)


def home(request):
    services = _get_all_services()
    active_services = [s for s in services if s['is_active'] and s['price_weekday'] > 0]
    today = timezone.localdate()
    day_type = ServicePrice.get_day_type_for_date(today)
    min_price = min((s['price_weekday'] for s in active_services), default=390000)

    home_images = {
        'hero_banner': _fresh_static_url('images/home/hero-banner.jpg'),
        'onsen_1': _fresh_static_url('images/home/onsen-1.jpg'),
        'onsen_2': _fresh_static_url('images/home/onsen-2.jpg'),
        'onsen_3': _fresh_static_url('images/home/onsen-3.jpg'),
        'eco_rooms': _fresh_static_url('images/home/eco-rooms.jpg'),
        'eco_spa': _fresh_static_url('images/home/eco-spa.jpg'),
        'eco_dining': _fresh_static_url('images/home/eco-dining.jpg'),
        'gal_1': _fresh_static_url('images/home/gal-1.jpg'),
        'gal_2': _fresh_static_url('images/home/gal-2.jpg'),
        'gal_3': _fresh_static_url('images/home/gal-3.jpg'),
        'gal_4': _fresh_static_url('images/home/gal-4.jpg'),
        'gal_5': _fresh_static_url('images/home/gal-5.jpg'),
        'gal_6': _fresh_static_url('images/home/gal-6.jpg'),
        'gal_7': _fresh_static_url('images/home/gal-7.jpg'),
    }

    context = {
        'services': services,
        'info_pages': INFO_PAGES,
        'home_images': home_images,
        'today_iso': today.isoformat(),
        'default_date_iso': today.isoformat(),
        'default_day_label': 'Cuối tuần (T7–CN)' if day_type == 'WEEKEND' else 'Đầu tuần (T2–T6)',
        'min_price': min_price,
        'min_price_fmt': _fmt_vnd(min_price),
    }
    response = render(request, 'booking/home.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

def onsen_detail(request, service_id):
    services = _get_all_services()
    service = next((s for s in services if s['id'] == service_id), None)
    if not service:
        raise Http404("Không tìm thấy gói dịch vụ Onsen.")

    preset = ONSEN_DETAIL_PRESETS.get(service['id'], ONSEN_DETAIL_PRESETS[1])

    pub_wd_adult = int(service.get('price_weekday') or 650000)
    pub_we_adult = int(service.get('price_weekend') or pub_wd_adult)
    qt_wd_adult = int(service.get('price_qt_weekday') or pub_wd_adult)
    qt_we_adult = int(service.get('price_qt_weekend') or pub_we_adult)

    pub_wd_child = int(service.get('price_child_weekday') or (pub_wd_adult // 2))
    pub_we_child = int(service.get('price_child_weekend') or (pub_we_adult // 2))

    child_prices = {
        sp.day_type: sp
        for sp in ServicePrice.objects.filter(service_id=service['id'], ticket_type='CHILD')
    }
    sp_child_wd = child_prices.get('WEEKDAY')
    sp_child_we = child_prices.get('WEEKEND')

    qt_wd_child = (
        int(sp_child_wd.quang_tri_price)
        if (sp_child_wd and sp_child_wd.quang_tri_price is not None)
        else (qt_wd_adult // 2)
    )
    qt_we_child = (
        int(sp_child_we.quang_tri_price)
        if (sp_child_we and sp_child_we.quang_tri_price is not None)
        else (qt_we_adult // 2)
    )

    pricing = {
        'pub_wd_adult': _fmt_vnd(pub_wd_adult),
        'pub_wd_child': _fmt_vnd(pub_wd_child),
        'pub_we_adult': _fmt_vnd(pub_we_adult),
        'pub_we_child': _fmt_vnd(pub_we_child),
        'qt_wd_adult': _fmt_vnd(qt_wd_adult),
        'qt_wd_child': _fmt_vnd(qt_wd_child),
        'qt_we_adult': _fmt_vnd(qt_we_adult),
        'qt_we_child': _fmt_vnd(qt_we_child),
    }

    gallery_items = []
    for idx, (fb_rel, caption) in enumerate(preset['fallback_photos'], start=1):
        gallery_items.append({
            'primary': f"images/home/onsen-{service['id']}-{idx}.jpg",
            'fallback_url': static(fb_rel),
            'caption': caption,
        })

    other_services = []
    for s in services:
        if s['id'] == service['id']:
            continue
        s_preset = ONSEN_DETAIL_PRESETS.get(s['id'], ONSEN_DETAIL_PRESETS[1])
        other_services.append({
            'id': s['id'],
            'name': s['name'],
            'is_active': s['is_active'],
            'price_weekday_fmt': s.get('price_weekday_fmt', _fmt_vnd(0)),
            'short_desc': s_preset['summary'],
            'thumb_primary': f"images/home/onsen-{s['id']}.jpg",
            'thumb_fallback': static('images/home/gal-1.jpg'),
        })

    return render(request, 'booking/onsen_detail.html', {
        'services': services,
        'info_pages': INFO_PAGES,
        'service': service,
        'hero_image_path': f"images/home/onsen-{service['id']}.jpg",
        'summary_line': preset['summary'],
        'description_text': preset['description'],
        'highlights_list': list(preset['highlights']),
        'gallery_items': gallery_items,
        'pricing': pricing,
        'other_services': other_services,
    })


def check_availability(request):
    date_str = request.GET.get('date', '').strip()
    exclude_order_code = request.GET.get('exclude_order', '').strip().upper()
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return JsonResponse({'error': 'Vui lòng chọn ngày đi hợp lệ.'}, status=400)

    if target_date < timezone.localdate():
        return JsonResponse({'error': 'Vui lòng không chọn ngày trong quá khứ.'}, status=400)

    held_by_order = {}
    if exclude_order_code:
        ex_order = _find_order_by_code(exclude_order_code)
        if ex_order and ex_order.visit_date == target_date:
            for it in ex_order.items.exclude(ticket_type='INFANT'):
                held_by_order[it.service_id] = held_by_order.get(it.service_id, 0) + int(it.quantity or 0)

    day_type = ServicePrice.get_day_type_for_date(target_date)
    is_weekend = (day_type == 'WEEKEND')

    results = []
    for s in _get_all_services():
        remain = _get_available_qty(s, target_date) + held_by_order.get(s['id'], 0)
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


def apply_voucher_api(request):
    code = request.GET.get('code', '')
    try:
        subtotal = max(0, int(request.GET.get('subtotal', 0)))
    except ValueError:
        subtotal = 0

    result = _evaluate_voucher(code, subtotal)
    status_code = 200 if result.get('valid') else 400
    return JsonResponse(result, status=status_code)


def order_payment_status_api(request, order_code):
    """API kiểm tra trạng thái thanh toán thực tế của đơn hàng."""
    order_obj = _find_order_by_code(order_code)
    if not order_obj:
        return JsonResponse({'ok': False, 'error': 'Không tìm thấy đơn hàng.'}, status=404)

    lookup_url = f"{reverse('booking:lookup_ticket')}?q={quote(order_obj.order_id)}"
    latest_txn = PaymentTransaction.objects.filter(order=order_obj).order_by('-id').first()
    txn_status = latest_txn.payment_status if latest_txn else 'Pending'
    customer_email = (order_obj.customer.email or '') if order_obj.customer else ''

    if order_obj.order_status == 'Paid':
        state = 'success'
        message = f"Thanh toán thành công đơn {order_obj.order_id}! Vé điện tử kèm mã QR đã được gửi tới email của quý khách."
    elif order_obj.order_status == 'Cancelled' or order_obj.is_expired:
        state = 'expired'
        message = f"Đơn hàng {order_obj.order_id} đã hết thời gian giữ vé 15 phút hoặc đã bị hủy."
    elif txn_status == 'Failed':
        state = 'failed'
        message = 'Giao dịch thanh toán qua VNPAY chưa thành công hoặc đã bị hủy trên cổng thanh toán.'
    else:
        state = 'pending'
        message = 'Đang chờ quý khách hoàn tất thanh toán trên cổng VNPAY.'

    return JsonResponse({
        'ok': True,
        'order_code': order_obj.order_id,
        'qr_code': order_obj.qr_code or '',
        'visit_date_display': order_obj.visit_date.strftime('%d/%m/%Y'),
        'total_amount_fmt': _fmt_vnd(int(order_obj.total_amount or 0)),
        'email': customer_email,
        'expires_at_ts': int(order_obj.expires_at.timestamp()) if order_obj.expires_at else 0,
        'order_status': order_obj.order_status,
        'txn_status': txn_status,
        'state': state,
        'is_paid': (state == 'success'),
        'is_expired': order_obj.is_expired,
        'message': message,
        'lookup_url': lookup_url,
    })


def book_form(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    today = timezone.localdate()
    date_str = (request.GET.get('date') or request.POST.get('visit_date') or today.isoformat()).strip()
    try:
        visit_date = date.fromisoformat(date_str)
    except ValueError:
        visit_date = today

    if visit_date < today:
        visit_date = today

    day_type = ServicePrice.get_day_type_for_date(visit_date)
    is_weekend = (day_type == 'WEEKEND')

    raw_items = (request.GET.get('items') or '').strip()
    initial_qty_map = {}
    if raw_items:
        for pair in raw_items.split(','):
            if ':' in pair:
                sid_part, qty_part = pair.split(':', 1)
                if sid_part.isdigit() and qty_part.isdigit():
                    initial_qty_map[int(sid_part)] = max(0, int(qty_part))

    raw_service = (request.GET.get('service') or '').strip()
    if not initial_qty_map and raw_service.isdigit():
        initial_qty_map[int(raw_service)] = 1

    all_services = _get_all_services()
    service_packages = []
    for s in all_services:
        avail = _get_available_qty(s, visit_date)
        init_qty = min(avail, initial_qty_map.get(s['id'], 0)) if s['is_active'] else 0
        p_adult = s['price_weekend'] if is_weekend else s['price_weekday']
        p_child = s['price_child_weekend'] if is_weekend else s['price_child_weekday']
        p_qt = s['price_qt_weekend'] if is_weekend else s['price_qt_weekday']

        service_packages.append({
            'id': s['id'],
            'service_code': s['service_code'],
            'name': s['name'],
            'is_active': s['is_active'],
            'cap': s['cap'],
            'available': avail,
            'highlights': s['highlights'],
            'image_url': s['image_url'],
            'price_adult': p_adult,
            'price_child': p_child,
            'price_qt': p_qt,
            'price_adult_fmt': _fmt_vnd(p_adult),
            'price_child_fmt': _fmt_vnd(p_child),
            'price_qt_fmt': _fmt_vnd(p_qt),
            'init_qty': init_qty,
        })

    if sum(p['init_qty'] for p in service_packages) == 0:
        first_open = next((p for p in service_packages if p['is_active'] and p['available'] > 0), None)
        if first_open:
            first_open['init_qty'] = 1

    error_msg = ''
    form_data = {
        'full_name': '',
        'phone': '',
        'email': '',
        'cccd': '',
        'note': '',
        'voucher_code': '',
        'payment_method': 'E_WALLET',
    }

    if request.method == 'POST':
        form_data = {
            'full_name': request.POST.get('full_name', '').strip(),
            'phone': request.POST.get('phone', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'cccd': request.POST.get('cccd', '').strip(),
            'note': request.POST.get('note', '').strip(),
            'voucher_code': request.POST.get('voucher_code', '').strip().upper(),
            'payment_method': 'E_WALLET',
        }

        raw_cccd_tokens = [form_data['cccd']] + request.POST.get('qt_cccd_list', '').split(',')
        unique_qt_cccds = []
        for token in raw_cccd_tokens:
            clean_c = token.strip()
            if ServicePrice.is_quang_tri_cccd(clean_c) and clean_c not in unique_qt_cccds:
                unique_qt_cccds.append(clean_c)

        remaining_qt_quota = len(unique_qt_cccds)
        qt_cursor = 0

        if not form_data['full_name']:
            error_msg = 'Vui lòng nhập họ và tên khách hàng.'
        elif not (len(form_data['phone']) == 10 and form_data['phone'].isdigit() and form_data['phone'].startswith('0')):
            error_msg = 'Số điện thoại phải gồm đúng 10 chữ số và bắt đầu bằng số 0.'
        elif '@' not in form_data['email'] or '.' not in form_data['email']:
            error_msg = 'Địa chỉ email không hợp lệ để nhận mã vé QR.'
        elif form_data['cccd'] and not (len(form_data['cccd']) == 12 and form_data['cccd'].isdigit()):
            error_msg = 'Số CCCD phải gồm đúng 12 chữ số.'

        has_any_cccd = bool(form_data['cccd']) or any(
            t.strip() for t in request.POST.get('qt_cccd_list', '').split(',')
        )
        if not error_msg and has_any_cccd and request.POST.get('cccd_confirmed') != '1':
            error_msg = 'Vui lòng tick xác nhận số CCCD đã nhập là chính xác và sẵn sàng xuất trình để nhân viên kiểm tra khi check-in.'

        parsed_lines = []
        total_paid_tickets = 0
        subtotal_amount = 0

        if not error_msg:
            for pkg in service_packages:
                sid = pkg['id']
                adult_qty = max(0, int(request.POST.get(f'adult_qty_{sid}', 0) or 0))
                child_qty = max(0, int(request.POST.get(f'child_qty_{sid}', 0) or 0))
                infant_qty = max(0, int(request.POST.get(f'infant_qty_{sid}', 0) or 0))
                requested_qt = max(0, int(request.POST.get(f'qt_adult_qty_{sid}', 0) or 0))

                pkg_paid_qty = adult_qty + child_qty
                if pkg_paid_qty == 0 and infant_qty == 0:
                    continue
                if pkg_paid_qty == 0 and infant_qty > 0:
                    error_msg = 'Trẻ em dưới 1m miễn phí vé cần đi kèm ít nhất 01 vé có tính phí.'
                    break

                if not pkg['is_active']:
                    error_msg = f"Gói {pkg['name']} hiện đang tạm ngừng phục vụ."
                    break
                if pkg_paid_qty > pkg['available']:
                    error_msg = f"Gói {pkg['name']} chỉ còn {pkg['available']} vé trống trong ngày {visit_date.strftime('%d/%m/%Y')}."
                    break

                effective_requested_qt = requested_qt if requested_qt > 0 else len(unique_qt_cccds)
                qt_adult_qty = min(adult_qty, effective_requested_qt, remaining_qt_quota)
                remaining_qt_quota -= qt_adult_qty
                assigned_qt_cccds = unique_qt_cccds[qt_cursor:qt_cursor + qt_adult_qty]
                qt_cursor += qt_adult_qty

                regular_adult_qty = adult_qty - qt_adult_qty
                line_total = (
                    regular_adult_qty * pkg['price_adult']
                    + qt_adult_qty * pkg['price_qt']
                    + child_qty * pkg['price_child']
                )

                total_paid_tickets += pkg_paid_qty
                subtotal_amount += line_total
                parsed_lines.append({
                    'pkg': pkg,
                    'adult_qty': adult_qty,
                    'regular_adult_qty': regular_adult_qty,
                    'qt_adult_qty': qt_adult_qty,
                    'assigned_qt_cccds': assigned_qt_cccds,
                    'child_qty': child_qty,
                    'infant_qty': infant_qty,
                    'pkg_paid_qty': pkg_paid_qty,
                    'line_total': line_total,
                })

        if not error_msg and total_paid_tickets == 0:
            error_msg = 'Vui lòng chọn ít nhất 1 vé có tính phí để tiếp tục đặt vé.'

        if error_msg and is_ajax:
            return JsonResponse({'ok': False, 'error': error_msg}, status=400)

        if not error_msg:
            discount_amount = 0
            voucher_obj = None
            if form_data['voucher_code']:
                v_res = _evaluate_voucher(form_data['voucher_code'], subtotal_amount)
                if v_res.get('valid'):
                    discount_amount = v_res['discount']
                    if v_res.get('voucher_id'):
                        voucher_obj = Voucher.objects.filter(pk=v_res['voucher_id']).first()

            final_amount = max(0, subtotal_amount - discount_amount)

            with transaction.atomic():
                customer_obj = Customer.objects.filter(phone=form_data['phone']).first()
                if customer_obj:
                    customer_obj.customer_name = form_data['full_name']
                    if form_data['email']:
                        customer_obj.email = form_data['email']
                    if form_data['cccd']:
                        customer_obj.cccd_number = form_data['cccd']
                    customer_obj.save(update_fields=['customer_name', 'email', 'cccd_number'])
                else:
                    customer_obj = Customer.objects.create(
                        customer_name=form_data['full_name'],
                        phone=form_data['phone'],
                        email=form_data['email'] or None,
                        cccd_number=form_data['cccd'] or None,
                    )

                order_obj = Order.objects.create(
                    customer=customer_obj,
                    channel='ONLINE',
                    total_quantity=total_paid_tickets,
                    visit_date=visit_date,
                    voucher=voucher_obj,
                    discount_amount=Decimal(discount_amount),
                    total_amount=Decimal(final_amount),
                    payment_method='E_WALLET',
                    order_status='New',
                    ticket_status='UNUSED',
                )

                if voucher_obj:
                    Voucher.objects.filter(pk=voucher_obj.pk).update(used_count=F('used_count') + 1)

                for line in parsed_lines:
                    service_id = line['pkg']['id']
                    if line['regular_adult_qty'] > 0:
                        OrderItem.objects.create(
                            order=order_obj,
                            service_id=service_id,
                            ticket_type='ADULT',
                            cccd_number=None,
                            quantity=line['regular_adult_qty'],
                            unit_price=Decimal(line['pkg']['price_adult']),
                        )

                    for qt_cccd in line['assigned_qt_cccds']:
                        OrderItem.objects.create(
                            order=order_obj,
                            service_id=service_id,
                            ticket_type='ADULT',
                            cccd_number=qt_cccd,
                            quantity=1,
                            unit_price=Decimal(line['pkg']['price_qt']),
                        )

                    if line['child_qty'] > 0:
                        OrderItem.objects.create(
                            order=order_obj,
                            service_id=service_id,
                            ticket_type='CHILD',
                            cccd_number=None,
                            quantity=line['child_qty'],
                            unit_price=Decimal(line['pkg']['price_child']),
                        )

                    if line['infant_qty'] > 0:
                        OrderItem.objects.create(
                            order=order_obj,
                            service_id=service_id,
                            ticket_type='INFANT',
                            cccd_number=None,
                            quantity=line['infant_qty'],
                            unit_price=Decimal(0),
                        )

                txn_obj = PaymentTransaction.objects.create(
                    order=order_obj,
                    transaction_type='INITIAL',
                    payment_method='E_WALLET',
                    amount=Decimal(final_amount),
                    payment_status='Pending',
                )

            lookup_url = f"{reverse('booking:lookup_ticket')}?q={quote(order_obj.order_id)}"

            if final_amount == 0:
                txn_obj.payment_status = 'Success'
                txn_obj.completed_time = timezone.now()
                txn_obj.save(update_fields=['payment_status', 'completed_time'])
                order_obj.issue_qr_ticket()
                order_obj.save(update_fields=['ticket_id', 'qr_code', 'order_status', 'ticket_status'])
                _send_qr_ticket_email(order_obj, request=request)

                msg = f"Đặt vé thành công! Mã vé QR của đơn {order_obj.order_id} đã được gửi tới email."
                if is_ajax:
                    return JsonResponse({
                        'ok': True,
                        'zero_amount': True,
                        'order_code': order_obj.order_id,
                        'qr_code': order_obj.qr_code or '',
                        'visit_date_display': order_obj.visit_date.strftime('%d/%m/%Y'),
                        'total_amount_fmt': _fmt_vnd(0),
                        'email': customer_obj.email or '',
                        'message': msg,
                        'lookup_url': lookup_url,
                    })
                messages.success(request, msg)
                return redirect(lookup_url)

            vnpay_url = _build_vnpay_payment_url(request, order_obj, txn_obj)
            if is_ajax:
                return JsonResponse({
                    'ok': True,
                    'zero_amount': False,
                    'order_code': order_obj.order_id,
                    'visit_date_display': order_obj.visit_date.strftime('%d/%m/%Y'),
                    'total_amount_fmt': _fmt_vnd(final_amount),
                    'email': customer_obj.email or '',
                    'expires_at_ts': int(order_obj.expires_at.timestamp()) if order_obj.expires_at else 0,
                    'vnpay_url': vnpay_url,
                    'lookup_url': lookup_url,
                })
            return redirect(vnpay_url)

    context = {
        'services': all_services,
        'info_pages': INFO_PAGES,
        'today_iso': today.isoformat(),
        'visit_date_iso': visit_date.isoformat(),
        'visit_date_display': visit_date.strftime('%d/%m/%Y'),
        'day_label': 'Cuối tuần (T7–CN)' if is_weekend else 'Đầu tuần (T2–T6)',
        'service_packages': service_packages,
        'packages_json': json.dumps(service_packages),
        'error_msg': error_msg,
        'form_data': form_data,
    }
    return render(request, 'booking/book_form.html', context)


def retry_vnpay_payment(request, order_code):
    """Tạo giao dịch VNPAY mới cho đơn chưa thanh toán (hỗ trợ cả AJAX mở tab mới lẫn redirect)."""
    is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1')
    order_obj = _find_order_by_code(order_code)
    if not order_obj:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Không tìm thấy đơn hàng.'}, status=404)
        return redirect('booking:home')

    lookup_url = f"{reverse('booking:lookup_ticket')}?q={quote(order_obj.order_id)}"

    if order_obj.order_status == 'Paid':
        if is_ajax:
            return JsonResponse({'ok': True, 'already_paid': True, 'order_code': order_obj.order_id, 'lookup_url': lookup_url})
        return redirect(lookup_url)

    if order_obj.is_expired or order_obj.order_status == 'Cancelled':
        err = f"Đơn hàng {order_obj.order_id} đã hết hạn giữ vé 15 phút. Quý khách vui lòng bấm Thanh toán lại để tạo đơn mới."
        if is_ajax:
            return JsonResponse({'ok': False, 'expired': True, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(lookup_url)

    txn_obj = PaymentTransaction.objects.create(
        order=order_obj,
        transaction_type='INITIAL',
        payment_method='E_WALLET',
        amount=order_obj.total_amount,
        payment_status='Pending',
    )
    vnpay_url = _build_vnpay_payment_url(request, order_obj, txn_obj)
    if is_ajax:
        return JsonResponse({
            'ok': True,
            'order_code': order_obj.order_id,
            'vnpay_url': vnpay_url,
            'lookup_url': lookup_url,
        })
    return redirect(vnpay_url)


def _apply_reschedule_customer_update(order_obj: Order, customer_data: dict):
    """Cập nhật thông tin khách hàng cho đơn vé khi đổi vé."""
    if not customer_data:
        return

    new_name = (customer_data.get('full_name') or '').strip()
    new_phone = (customer_data.get('phone') or '').strip()
    new_email = (customer_data.get('email') or '').strip()
    new_cccd = (customer_data.get('rep_cccd') or '').strip()

    if not new_name or not new_phone:
        return

    existing_cust = Customer.objects.filter(phone=new_phone).first()
    if existing_cust:
        existing_cust.customer_name = new_name
        if new_email:
            existing_cust.email = new_email
        if new_cccd:
            existing_cust.cccd_number = new_cccd
        existing_cust.save(update_fields=['customer_name', 'email', 'cccd_number'])
        if order_obj.customer_id != existing_cust.id:
            order_obj.customer = existing_cust
            order_obj.save(update_fields=['customer'])
        return

    cur_cust = order_obj.customer
    if cur_cust and not Order.objects.filter(customer=cur_cust).exclude(pk=order_obj.pk).exists():
        cur_cust.customer_name = new_name
        cur_cust.phone = new_phone
        cur_cust.email = new_email or None
        if new_cccd:
            cur_cust.cccd_number = new_cccd
        cur_cust.save(update_fields=['customer_name', 'phone', 'email', 'cccd_number'])
    else:
        new_cust = Customer.objects.create(
            customer_name=new_name,
            phone=new_phone,
            email=new_email or None,
            cccd_number=new_cccd or None,
        )
        order_obj.customer = new_cust
        order_obj.save(update_fields=['customer'])


def vnpay_return(request):
    params = request.GET
    if not params:
        return redirect('booking:home')

    def _render_callback(status: str, order_code: str, message: str, lookup_url: str, fallback_url: str):
        payload = {
            'type': 'VNPAY_RESULT',
            'status': status,
            'order_code': order_code,
            'message': message,
            'lookup_url': lookup_url,
            'fallback_url': fallback_url,
            'ts': int(timezone.now().timestamp() * 1000),
        }
        return render(request, 'booking/vnpay_callback.html', {
            'status': status,
            'order_code': order_code,
            'message': message,
            'lookup_url': lookup_url,
            'fallback_url': fallback_url,
            'payload_json': json.dumps(payload, ensure_ascii=False).replace('</', '<\\/'),
        })

    if not _verify_vnpay_signature(params):
        return _render_callback(
            status='failed',
            order_code='',
            message='Chữ ký xác thực giao dịch từ VNPAY không hợp lệ.',
            lookup_url=reverse('booking:lookup_ticket'),
            fallback_url=reverse('booking:home'),
        )

    txn_ref = (params.get('vnp_TxnRef') or '').strip()
    response_code = (params.get('vnp_ResponseCode') or '').strip()
    txn_status = (params.get('vnp_TransactionStatus') or '').strip()
    vnp_txn_no = (params.get('vnp_TransactionNo') or '').strip()
    vnp_bank_ref = (params.get('vnp_BankTranNo') or params.get('vnp_BankCode') or '').strip()

    try:
        paid_amount_vnd = int(params.get('vnp_Amount', 0)) // 100
    except ValueError:
        paid_amount_vnd = 0

    txn_obj = PaymentTransaction.objects.select_related('order__customer').filter(transaction_id=txn_ref).first()
    if not txn_obj:
        return _render_callback(
            status='failed',
            order_code='',
            message='Không tìm thấy giao dịch thanh toán tương ứng trên hệ thống.',
            lookup_url=reverse('booking:lookup_ticket'),
            fallback_url=reverse('booking:home'),
        )

    order_obj = txn_obj.order
    default_lookup_url = f"{reverse('booking:lookup_ticket')}?q={quote(order_obj.order_id)}"

    cache_key = f'pending_exchange_{txn_ref}'
    pending_exchange = request.session.pop(cache_key, None)
    if pending_exchange is None:
        pending_exchange = cache.get(cache_key)
    cache.delete(cache_key)

    is_exchange_txn = bool(pending_exchange and pending_exchange.get('order_id') == order_obj.order_id)

    saved_back_url = cache.get(f'exchange_back_{txn_ref}')
    exchange_lookup_url = (
        ((pending_exchange.get('back_lookup_url') or '').strip() if is_exchange_txn else '')
        or saved_back_url
        or default_lookup_url
    )
    back_q_from_exchange = (pending_exchange.get('back_q') or '').strip() if is_exchange_txn else ''

    if is_exchange_txn or saved_back_url:
        reschedule_base = reverse('booking:reschedule_page', kwargs={'order_code': order_obj.order_id})
        fallback_url = (
            f"{reschedule_base}?{urlencode({'q': back_q_from_exchange})}"
            if back_q_from_exchange
            else reschedule_base
        )
    else:
        fallback_url = reverse('booking:payment_page', kwargs={'order_code': order_obj.order_id})

    if txn_obj.payment_status == 'Success' and order_obj.order_status == 'Paid':
        return _render_callback(
            status='success',
            order_code=order_obj.order_id,
            message=f"Thanh toán VNPAY thành công cho đơn {order_obj.order_id}! Đang chuyển sang trang tra cứu vé...",
            lookup_url=exchange_lookup_url,
            fallback_url=exchange_lookup_url,
        )

    if response_code != '00' or txn_status != '00':
        txn_obj.payment_status = 'Failed'
        if vnp_bank_ref:
            txn_obj.bank_ref = vnp_bank_ref
        txn_obj.save(update_fields=['payment_status', 'bank_ref'])

        reason_msg = (
            'Quý khách đã hủy giao dịch trên cổng thanh toán VNPAY.'
            if response_code == '24'
            else f'Giao dịch VNPAY chưa hoàn tất (Mã phản hồi: {response_code}).'
        )
        return _render_callback(
            status='failed',
            order_code=order_obj.order_id,
            message=reason_msg,
            lookup_url=exchange_lookup_url,
            fallback_url=fallback_url,
        )

    if paid_amount_vnd != int(txn_obj.amount):
        txn_obj.payment_status = 'Failed'
        txn_obj.save(update_fields=['payment_status'])
        return _render_callback(
            status='failed',
            order_code=order_obj.order_id,
            message='Số tiền thanh toán từ VNPAY không khớp với giá trị giao dịch.',
            lookup_url=exchange_lookup_url,
            fallback_url=fallback_url,
        )

    # TRƯỜNG HỢP A: THANH TOÁN BỔ SUNG CHO YÊU CẦU ĐỔI VÉ
    if is_exchange_txn:
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order_obj.pk)
            if locked_order.has_been_exchanged:
                txn_obj.payment_status = 'Failed'
                txn_obj.save(update_fields=['payment_status'])
                return _render_callback(
                    status='failed',
                    order_code=locked_order.order_id,
                    message=f'Đơn hàng {locked_order.order_id} đã hoàn tất đổi vé 1 lần trước đó. Theo quy định, mỗi đơn chỉ được đổi vé tối đa 01 lần.',
                    lookup_url=exchange_lookup_url,
                    fallback_url=exchange_lookup_url,
                )

            txn_obj.payment_status = 'Success'
            txn_obj.completed_time = timezone.now()
            if vnp_txn_no and not PaymentTransaction.objects.filter(gateway_transaction_id=vnp_txn_no).exclude(pk=txn_obj.pk).exists():
                txn_obj.gateway_transaction_id = vnp_txn_no
            if vnp_bank_ref:
                txn_obj.bank_ref = vnp_bank_ref
            txn_obj.save(update_fields=['payment_status', 'completed_time', 'gateway_transaction_id', 'bank_ref'])

            _apply_reschedule_customer_update(locked_order, pending_exchange.get('customer_data'))

            locked_order.items.all().delete()
            for ln in pending_exchange.get('lines', []):
                sid = ln['service_id']
                if ln['reg_adult_qty'] > 0:
                    OrderItem.objects.create(
                        order=locked_order,
                        service_id=sid,
                        ticket_type='ADULT',
                        cccd_number=None,
                        quantity=ln['reg_adult_qty'],
                        unit_price=Decimal(ln['price_adult']),
                    )
                for q_cccd in ln['assigned_qt_cccds']:
                    OrderItem.objects.create(
                        order=locked_order,
                        service_id=sid,
                        ticket_type='ADULT',
                        cccd_number=q_cccd,
                        quantity=1,
                        unit_price=Decimal(ln['price_qt']),
                    )
                if ln['child_qty'] > 0:
                    OrderItem.objects.create(
                        order=locked_order,
                        service_id=sid,
                        ticket_type='CHILD',
                        cccd_number=None,
                        quantity=ln['child_qty'],
                        unit_price=Decimal(ln['price_child']),
                    )
                if ln['infant_qty'] > 0:
                    OrderItem.objects.create(
                        order=locked_order,
                        service_id=sid,
                        ticket_type='INFANT',
                        cccd_number=None,
                        quantity=ln['infant_qty'],
                        unit_price=Decimal(0),
                    )

            locked_order.visit_date = date.fromisoformat(pending_exchange['visit_date'])
            locked_order.total_quantity = int(pending_exchange['total_quantity'])
            locked_order.discount_amount = Decimal(pending_exchange['discount_amount'])
            locked_order.total_amount = Decimal(pending_exchange['new_total'])
            locked_order.exchange_time = timezone.now()
            locked_order.qr_code = f"BOS-{locked_order.order_id}-{uuid.uuid4().hex[:6].upper()}"
            locked_order.save(update_fields=[
                'visit_date', 'total_quantity', 'discount_amount', 'total_amount', 'exchange_time', 'qr_code'
            ])
            order_obj = locked_order

        _send_qr_ticket_email(order_obj, request=request)
        exchange_msg = (
            f"Thanh toán bổ sung {_fmt_vnd(pending_exchange['diff_amount'])} & Đổi vé đơn {order_obj.order_id} thành công! "
            f"Mã QR mới đã được cấp và gửi qua email."
        )
        messages.success(request, exchange_msg)
        return _render_callback(
            status='success',
            order_code=order_obj.order_id,
            message=exchange_msg,
            lookup_url=exchange_lookup_url,
            fallback_url=exchange_lookup_url,
        )

    # TRƯỜNG HỢP B: THANH TOÁN ĐƠN ĐẶT VÉ BAN ĐẦU
    with transaction.atomic():
        txn_obj.payment_status = 'Success'
        txn_obj.completed_time = timezone.now()
        if vnp_txn_no and not PaymentTransaction.objects.filter(gateway_transaction_id=vnp_txn_no).exclude(pk=txn_obj.pk).exists():
            txn_obj.gateway_transaction_id = vnp_txn_no
        if vnp_bank_ref:
            txn_obj.bank_ref = vnp_bank_ref
        txn_obj.save(update_fields=['payment_status', 'completed_time', 'gateway_transaction_id', 'bank_ref'])

        order_obj.payment_method = 'E_WALLET'
        order_obj.issue_qr_ticket()
        order_obj.save(update_fields=['payment_method', 'ticket_id', 'qr_code', 'order_status', 'ticket_status'])

    email_sent = _send_qr_ticket_email(order_obj, request=request)
    customer_email = order_obj.customer.email if order_obj.customer else ''
    success_msg = (
        f"Thanh toán thành công đơn {order_obj.order_id}! Vé điện tử kèm mã QR đã được gửi tới email {customer_email}."
        if (email_sent and customer_email)
        else f"Thanh toán thành công đơn {order_obj.order_id}! Mã vé điện tử QR đã sẵn sàng."
    )

    return _render_callback(
        status='success',
        order_code=order_obj.order_id,
        message=success_msg,
        lookup_url=default_lookup_url,
        fallback_url=default_lookup_url,
    )


def payment_page(request, order_code):
    order_obj = _find_order_by_code(order_code)
    if not order_obj:
        return redirect('booking:home')

    if order_obj.order_status == 'Paid':
        return redirect(f"{reverse('booking:lookup_ticket')}?q={quote(order_obj.order_id)}")

    order_detail = _serialize_order_detail(order_obj)
    return render(request, 'booking/payment.html', {
        'services': _get_all_services(),
        'info_pages': INFO_PAGES,
        'order': order_detail,
    })


# ==============================================================================
# CÁC HÀM & VIEW TRA CỨU, ĐỔI VÉ & HỦY VÉ
# ==============================================================================
def _normalize_phone_digits(raw: str) -> str:
    digits = ''.join(ch for ch in (raw or '') if ch.isdigit())
    if digits.startswith('84') and len(digits) == 11:
        digits = '0' + digits[2:]
    return digits


def _find_order_by_code(order_code: str):
    clean_code = (order_code or '').strip().upper()
    if not clean_code:
        return None
    return (
        Order.objects.select_related('customer', 'voucher')
        .filter(Q(order_id__iexact=clean_code) | Q(ticket_id__iexact=clean_code))
        .first()
    )


def _evaluate_48h_policy(order_obj: Order) -> dict:
    now = timezone.localtime()
    tz = timezone.get_current_timezone()
    checkin_dt = timezone.make_aware(datetime.combine(order_obj.visit_date, time(9, 0)), tz)
    hours_left = (checkin_dt - now).total_seconds() / 3600.0
    checkin_disp = checkin_dt.strftime('09:00 ngày %d/%m/%Y')

    if order_obj.channel == 'COUNTER':
        msg = 'Vé mua trực tiếp tại quầy Lễ tân không áp dụng đổi/hủy trực tuyến. Quý khách vui lòng liên hệ quầy Lễ tân hoặc hotline 1900 8888 (09:00 – 21:00).'
        return {
            'can_modify': False,
            'can_exchange': False,
            'can_cancel': False,
            'exchange_count': order_obj.exchange_count,
            'hours_left': 0,
            'checkin_display': checkin_disp,
            'reason': msg,
            'exchange_reason': msg,
            'cancel_reason': msg,
        }

    if order_obj.ticket_status == 'VOID' or order_obj.order_status == 'Cancelled':
        msg = 'Vé thuộc đơn hàng này đã được hủy và không còn hiệu lực sử dụng.'
        return {
            'can_modify': False,
            'can_exchange': False,
            'can_cancel': False,
            'exchange_count': order_obj.exchange_count,
            'hours_left': 0,
            'checkin_display': checkin_disp,
            'reason': msg,
            'exchange_reason': msg,
            'cancel_reason': msg,
        }

    if order_obj.ticket_status == 'USED':
        msg = 'Vé đã được check-in sử dụng tại khu nghỉ dưỡng, không thể đổi hoặc hủy.'
        return {
            'can_modify': False,
            'can_exchange': False,
            'can_cancel': False,
            'exchange_count': order_obj.exchange_count,
            'hours_left': 0,
            'checkin_display': checkin_disp,
            'reason': msg,
            'exchange_reason': msg,
            'cancel_reason': msg,
        }

    if hours_left < 48:
        if hours_left <= 0:
            msg = 'Đã quá thời điểm mở cửa check-in (09:00 ngày sử dụng), không thể thực hiện đổi hoặc hủy vé.'
        else:
            msg = (
                f'Chỉ còn {int(hours_left)} giờ {int((hours_left % 1) * 60)} phút trước giờ mở cửa check-in '
                f'(09:00 ngày {order_obj.visit_date.strftime("%d/%m/%Y")}). Hệ thống chỉ hỗ trợ đổi/hủy trực tuyến trước tối thiểu 48 giờ.'
            )
        return {
            'can_modify': False,
            'can_exchange': False,
            'can_cancel': False,
            'exchange_count': order_obj.exchange_count,
            'hours_left': max(0.0, hours_left),
            'checkin_display': checkin_disp,
            'reason': msg,
            'exchange_reason': msg,
            'cancel_reason': msg,
        }

    has_exchanged = order_obj.has_been_exchanged
    exchanged_at_disp = (
        timezone.localtime(order_obj.exchange_time).strftime('%H:%M ngày %d/%m/%Y')
        if order_obj.exchange_time
        else ''
    )
    exchange_reason = ''
    if has_exchanged:
        time_note = f' (vào lúc {exchanged_at_disp})' if exchanged_at_disp else ''
        exchange_reason = (
            f'Đơn hàng {order_obj.order_id} đã thực hiện đổi vé 1 lần{time_note}. '
            f'Theo quy định của Bang Onsen, mỗi đơn chỉ được hỗ trợ đổi vé tối đa 01 lần.'
        )

    days_part = int(hours_left // 24)
    rem_hours = int(hours_left % 24)
    return {
        'can_modify': True,
        'can_exchange': not has_exchanged,
        'can_cancel': True,
        'exchange_count': 1 if has_exchanged else 0,
        'hours_left': hours_left,
        'checkin_display': checkin_disp,
        'time_left_label': f'Còn {days_part} ngày {rem_hours} giờ ({int(hours_left)} giờ) trước hạn 48h',
        'reason': exchange_reason,
        'exchange_reason': exchange_reason,
        'cancel_reason': '',
    }

def _recalculate_order_for_date(order_obj: Order, target_date: date) -> dict:
    services_map = {s['id']: s for s in _get_all_services()}
    day_type = ServicePrice.get_day_type_for_date(target_date)
    is_weekend = (day_type == 'WEEKEND')

    items = list(order_obj.items.select_related('service').all())
    if not items:
        return {'ok': False, 'error': 'Đơn hàng không có chi tiết gói dịch vụ để chuyển đổi.'}

    required_by_service = {}
    for it in items:
        if it.ticket_type != 'INFANT':
            required_by_service[it.service_id] = required_by_service.get(it.service_id, 0) + int(it.quantity or 0)

    for sid, needed_qty in required_by_service.items():
        srv = services_map.get(sid)
        if not srv or not srv['is_active']:
            srv_name = srv['name'] if srv else f'Gói #{sid}'
            return {'ok': False, 'error': f'{srv_name} hiện đang tạm ngừng phục vụ.'}

        avail = _get_available_qty(srv, target_date)
        if target_date == order_obj.visit_date:
            avail += needed_qty
        if avail < needed_qty:
            return {
                'ok': False,
                'error': f'{srv["name"]} chỉ còn {avail} vé trống vào ngày {target_date.strftime("%d/%m/%Y")} (đơn cần {needed_qty} vé).',
            }

    new_subtotal = 0
    item_updates = []

    for it in items:
        srv = services_map[it.service_id]
        if it.ticket_type == 'ADULT':
            is_qt = it.is_quang_tri_local or ServicePrice.is_quang_tri_cccd(it.cccd_number)
            if is_qt:
                new_unit_price = srv['price_qt_weekend'] if is_weekend else srv['price_qt_weekday']
            else:
                new_unit_price = srv['price_weekend'] if is_weekend else srv['price_weekday']
        elif it.ticket_type == 'CHILD':
            new_unit_price = srv['price_child_weekend'] if is_weekend else srv['price_child_weekday']
        else:
            new_unit_price = 0

        new_line_total = new_unit_price * int(it.quantity or 0)
        new_subtotal += new_line_total
        item_updates.append({
            'item_obj': it,
            'new_unit_price': new_unit_price,
            'new_line_total': new_line_total,
        })

    inherited = _calculate_inherited_discount(order_obj, new_subtotal)
    applied_discount = inherited['discount_amount']
    new_total = max(0, new_subtotal - applied_discount)
    old_total = int(order_obj.total_amount or 0)
    diff_amount = new_total - old_total

    return {
        'ok': True,
        'target_date_iso': target_date.isoformat(),
        'target_date_display': target_date.strftime('%d/%m/%Y'),
        'day_label': 'Cuối tuần (T7–CN)' if is_weekend else 'Đầu tuần (T2–T6)',
        'old_total': old_total,
        'old_total_fmt': _fmt_vnd(old_total),
        'new_subtotal': new_subtotal,
        'new_discount': applied_discount,
        'new_total': new_total,
        'new_total_fmt': _fmt_vnd(new_total),
        'diff_amount': diff_amount,
        'diff_abs_fmt': _fmt_vnd(abs(diff_amount)),
        'items': item_updates,
    }

def _serialize_order_detail(order_obj: Order) -> dict:
    order_code = order_obj.order_id
    customer = order_obj.customer

    customer_name = customer.customer_name if customer else 'Khách hàng'
    customer_phone = customer.phone if customer else ''
    customer_email = (customer.email or '') if customer else ''

    is_counter = (order_obj.channel == 'COUNTER')
    channel_code = 'COUNTER' if is_counter else 'ONLINE'
    channel_label = 'Mua tại quầy' if is_counter else 'Mua Online'

    order_status = order_obj.order_status
    ticket_status = order_obj.ticket_status

    is_cancelled = (ticket_status == 'VOID' or order_status == 'Cancelled')
    is_checked_in = (ticket_status == 'USED')

    rescheduled_at = (
        timezone.localtime(order_obj.exchange_time).strftime('%H:%M %d/%m/%Y')
        if order_obj.exchange_time
        else ''
    )
    cancelled_at = (
        timezone.localtime(order_obj.cancel_time).strftime('%H:%M %d/%m/%Y')
        if order_obj.cancel_time
        else ''
    )

    day_type = ServicePrice.get_day_type_for_date(order_obj.visit_date)
    day_label = 'Cuối tuần (T7–CN)' if day_type == 'WEEKEND' else 'Đầu tuần (T2–T6)'

    grouped_services = {}
    computed_sum = 0
    total_tickets = 0
    has_qt_discount = False
    order_cccds = []

    for it in order_obj.items.select_related('service').all():
        sid = it.service_id
        if sid not in grouped_services:
            grouped_services[sid] = {
                'service_name': it.service.service_name,
                'quantity': 0,
                'total_guests': 0,
                'reg_adult_qty': 0,
                'reg_adult_total': 0,
                'qt_adult_qty': 0,
                'qt_adult_total': 0,
                'child_qty': 0,
                'child_total': 0,
                'infant_qty': 0,
                'line_total': 0,
            }

        grp = grouped_services[sid]
        qty = int(it.quantity or 0)
        sub = int(it.subtotal or 0)
        computed_sum += sub
        total_tickets += qty
        grp['line_total'] += sub

        c_val = (it.cccd_number or '').strip()
        if c_val and c_val not in order_cccds:
            order_cccds.append(c_val)

        if it.ticket_type == 'ADULT':
            grp['quantity'] += qty
            grp['total_guests'] += qty
            if it.is_quang_tri_local or ServicePrice.is_quang_tri_cccd(c_val):
                grp['qt_adult_qty'] += qty
                grp['qt_adult_total'] += sub
                has_qt_discount = True
            else:
                grp['reg_adult_qty'] += qty
                grp['reg_adult_total'] += sub
        elif it.ticket_type == 'CHILD':
            grp['quantity'] += qty
            grp['total_guests'] += qty
            grp['child_qty'] += qty
            grp['child_total'] += sub
        elif it.ticket_type == 'INFANT':
            grp['total_guests'] += qty
            grp['infant_qty'] += qty

    cccd = ', '.join(order_cccds)

    lines = []
    summary_parts = []
    for grp in grouped_services.values():
        pkg_guests = grp['total_guests']
        summary_parts.append(f"{grp['service_name']} ({pkg_guests} vé)")
        lines.append({
            'service_name': grp['service_name'],
            'quantity': grp['quantity'],
            'total_guests': pkg_guests,
            'reg_adult_qty': grp['reg_adult_qty'],
            'reg_adult_total_fmt': _fmt_vnd(grp['reg_adult_total']),
            'qt_adult_qty': grp['qt_adult_qty'],
            'qt_adult_total_fmt': _fmt_vnd(grp['qt_adult_total']),
            'child_qty': grp['child_qty'],
            'child_total_fmt': _fmt_vnd(grp['child_total']),
            'infant_qty': grp['infant_qty'],
            'infant_total_fmt': _fmt_vnd(0),
            'line_total_fmt': _fmt_vnd(grp['line_total']),
        })

    total_amount = int(order_obj.total_amount or 0)
    discount_amount = int(order_obj.discount_amount or 0)
    policy = _evaluate_48h_policy(order_obj)

    checkin_time_display = (
        timezone.localtime(order_obj.checked_in_at).strftime('%H:%M %d/%m/%Y')
        if order_obj.checked_in_at
        else ''
    )

    if is_cancelled:
        status_label = 'Đã hủy vé'
        status_badge_cls = 'no'
        checkin_state = 'cancelled'
        checkin_label = 'Đã hủy vé'
        checkin_badge_cls = 'no'
    elif is_checked_in:
        status_label = 'Đã check-in'
        status_badge_cls = ''
        checkin_state = 'checked_in'
        checkin_label = f'Đã check-in ({checkin_time_display})' if checkin_time_display else 'Đã check-in'
        checkin_badge_cls = 'ok'
    elif order_status == 'Paid' or is_counter:
        status_label = 'Đã thanh toán'
        status_badge_cls = 'ok'
        checkin_state = 'pending_checkin'
        checkin_label = 'Chờ check-in'
        checkin_badge_cls = 'warn'
    else:
        status_label = 'Chờ thanh toán'
        status_badge_cls = ''
        checkin_state = 'unpaid'
        checkin_label = 'Chưa thanh toán'
        checkin_badge_cls = ''

    qr_payload = order_obj.qr_code or order_code
    qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=160x160&data={quote(qr_payload)}"
    created_display = timezone.localtime(order_obj.created_time).strftime('%H:%M · %d/%m/%Y')
    expires_at_ts = int(order_obj.expires_at.timestamp()) if order_obj.expires_at else 0

    return {
        'id': order_obj.pk,
        'order_id': order_code,
        'order_code': order_code,
        'ticket_id': order_obj.ticket_id or '',
        'channel': channel_code,
        'channel_label': channel_label,
        'qr_payload': qr_payload,
        'qr_image_url': qr_image_url,
        'is_cancelled': is_cancelled,
        'is_checked_in': is_checked_in,
        'reschedule_count': order_obj.exchange_count,
        'rescheduled_at': rescheduled_at,
        'cancelled_at': cancelled_at,
        'checkin_state': checkin_state,
        'checkin_label': checkin_label,
        'checkin_badge_cls': checkin_badge_cls,
        'customer_name': customer_name,
        'full_name': customer_name,
        'customer_phone': customer_phone,
        'phone': customer_phone,
        'customer_email': customer_email,
        'email': customer_email,
        'cccd': cccd,
        'is_qt_cccd': has_qt_discount,
        'voucher_code': order_obj.voucher.voucher_code if order_obj.voucher else '',
        'payment_method': order_obj.payment_method,
        'payment_method_label': PAYMENT_METHOD_LABELS.get(order_obj.payment_method, order_obj.get_payment_method_display()),
        'visit_date_iso': order_obj.visit_date.isoformat(),
        'visit_date_display': order_obj.visit_date.strftime('%d/%m/%Y'),
        'visit_day': order_obj.visit_date.day,
        'visit_month': order_obj.visit_date.month,
        'visit_year': order_obj.visit_date.year,
        'day_label': day_label,
        'created_display': created_display,
        'expires_at_ts': expires_at_ts,
        'is_expired': order_obj.is_expired,
        'order_status': order_status,
        'ticket_status': ticket_status,
        'status_label': status_label,
        'status_badge_cls': status_badge_cls,
        'is_qr_active': (ticket_status == 'UNUSED' and (order_status == 'Paid' or is_counter)),
        'total_tickets': total_tickets,
        'service_summary': ', '.join(summary_parts) if summary_parts else 'Gói dịch vụ Onsen',
        'subtotal_amount': computed_sum,
        'subtotal_fmt': _fmt_vnd(computed_sum),
        'discount_amount': discount_amount,
        'discount_fmt': _fmt_vnd(discount_amount),
        'total_amount': total_amount,
        'total_raw': total_amount,
        'total_fmt': _fmt_vnd(total_amount),
        'lines': lines,
        'policy': policy,
    }

def _execute_ticket_lookup(raw_query: str) -> dict:
    q = (raw_query or '').strip()
    if not q:
        return {
            'ok': False,
            'search_type': '',
            'query': '',
            'error': 'Vui lòng nhập Mã đơn vé, Số điện thoại hoặc Email để tra cứu.',
        }

    base_qs = Order.objects.select_related('customer', 'voucher').prefetch_related('items__service')
    norm_digits = _normalize_phone_digits(q)
    is_phone_pattern = (
        '@' not in q
        and len(norm_digits) == 10
        and all(ch.isdigit() or ch in ' +-.()' for ch in q)
    )

    if '@' in q:
        search_type = 'email'
        raw_orders = list(base_qs.filter(customer__email__iexact=q).order_by('-created_time', '-pk'))
    elif is_phone_pattern:
        search_type = 'phone'
        raw_orders = list(base_qs.filter(customer__phone=norm_digits).order_by('-created_time', '-pk'))
    else:
        search_type = 'order_code'
        clean_code = q.upper()
        single = base_qs.filter(Q(order_id__iexact=clean_code) | Q(ticket_id__iexact=clean_code)).first()
        raw_orders = [single] if single else []

    if not raw_orders:
        type_hint = {
            'email': 'địa chỉ email',
            'phone': 'số điện thoại',
            'order_code': 'mã đơn vé',
        }[search_type]
        return {
            'ok': False,
            'search_type': search_type,
            'query': q,
            'error': f'Không tìm thấy đơn vé nào khớp với {type_hint} "{q}". Vui lòng kiểm tra lại thông tin.',
        }

    serialized = [_serialize_order_detail(o) for o in raw_orders]
    online_orders = [o for o in serialized if o['channel'] != 'COUNTER']
    counter_orders = [o for o in serialized if o['channel'] == 'COUNTER']

    return {
        'ok': True,
        'search_type': search_type,
        'query': q,
        'total_count': len(serialized),
        'single_order': serialized[0] if search_type == 'order_code' else None,
        'online_orders': online_orders,
        'counter_orders': counter_orders,
    }


def lookup_ticket(request):
    query_str = (request.GET.get('q') or request.POST.get('q') or '').strip()
    today = timezone.localdate()
    min_reschedule_date = (today + timedelta(days=2)).isoformat()

    initial_payload = _execute_ticket_lookup(query_str) if query_str else None
    initial_json = json.dumps(initial_payload, ensure_ascii=False).replace('</', '<\\/') if initial_payload else 'null'

    return render(request, 'booking/lookup.html', {
        'services': _get_all_services(),
        'info_pages': INFO_PAGES,
        'query_str': query_str,
        'initial_payload_json': initial_json,
        'today_iso': today.isoformat(),
        'min_reschedule_date': min_reschedule_date,
    })


def lookup_ticket_api(request):
    query_str = (request.GET.get('q') or '').strip()
    try:
        payload = _execute_ticket_lookup(query_str)
        status_code = 200 if payload.get('ok') else 404
        return JsonResponse(payload, status=status_code)
    except Exception as exc:
        return JsonResponse({
            'ok': False,
            'query': query_str,
            'error': f'Lỗi xử lý dữ liệu tra cứu ({type(exc).__name__}: {exc})',
        }, status=500)


def check_reschedule_api(request):
    order_code = (request.GET.get('order_code') or '').strip().upper()
    new_date_str = (request.GET.get('new_date') or '').strip()

    order_obj = _find_order_by_code(order_code)
    if not order_obj:
        return JsonResponse({'ok': False, 'error': 'Không tìm thấy đơn hàng.'}, status=404)

    policy = _evaluate_48h_policy(order_obj)
    if not policy['can_exchange']:
        return JsonResponse({'ok': False, 'error': policy['exchange_reason']}, status=400)

    try:
        target_date = date.fromisoformat(new_date_str)
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Ngày sử dụng mới không hợp lệ.'}, status=400)

    if target_date == order_obj.visit_date:
        return JsonResponse({'ok': False, 'error': 'Vui lòng chọn ngày khác với ngày sử dụng hiện tại của đơn.'}, status=400)

    now = timezone.localtime()
    new_checkin_dt = timezone.make_aware(datetime.combine(target_date, time(9, 0)), timezone.get_current_timezone())
    if (new_checkin_dt - now).total_seconds() < 48 * 3600:
        return JsonResponse({
            'ok': False,
            'error': 'Ngày sử dụng mới phải cách thời điểm hiện tại tối thiểu 48 giờ.',
        }, status=400)

    calc = _recalculate_order_for_date(order_obj, target_date)
    if not calc['ok']:
        return JsonResponse({'ok': False, 'error': calc['error']}, status=400)

    if calc['diff_amount'] < 0:
        return JsonResponse({
            'ok': False,
            'error': f"Vé chỉ được đổi ngang giá hoặc cao hơn giá đơn cũ ({calc['old_total_fmt']}).",
        }, status=400)

    return JsonResponse({
        'ok': True,
        'target_date_display': calc['target_date_display'],
        'day_label': calc['day_label'],
        'old_total_fmt': calc['old_total_fmt'],
        'new_total_fmt': calc['new_total_fmt'],
        'diff_amount': calc['diff_amount'],
        'diff_abs_fmt': calc['diff_abs_fmt'],
    })


def _extract_order_qt_cccds(order_obj: Order) -> list[str]:
    """Chỉ lấy danh sách CCCD Quảng Trị thực sự đã áp dụng trên các dòng vé của đơn gốc."""
    cccds = []
    for it in order_obj.items.all():
        c = (it.cccd_number or '').strip()
        if ServicePrice.is_quang_tri_cccd(c) and c not in cccds:
            cccds.append(c)
    return cccds


def reschedule_page(request, order_code):
    policy = _evaluate_48h_policy(order_obj)
    if not policy['can_exchange']:
        messages.error(request, policy['exchange_reason'])
        return redirect(back_lookup_url)
    
    order_obj = _find_order_by_code(order_code)
    if not order_obj:
        messages.error(request, 'Không tìm thấy đơn vé cần đổi.')
        return redirect('booking:lookup_ticket')

    back_q, back_lookup_url = _resolve_back_lookup(request, order_obj.order_id)

    policy = _evaluate_48h_policy(order_obj)
    if not policy['can_modify']:
        messages.error(request, policy['reason'])
        return redirect(back_lookup_url)

    today = timezone.localdate()
    min_reschedule_date = today + timedelta(days=2)
    default_target_date = order_obj.visit_date if order_obj.visit_date >= min_reschedule_date else min_reschedule_date

    if request.method == 'POST':
        date_str = (request.POST.get('visit_date') or '').strip()
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = default_target_date
    else:
        target_date = default_target_date

    day_type = ServicePrice.get_day_type_for_date(target_date)
    is_weekend = (day_type == 'WEEKEND')

    orig_qty_map = {}
    held_paid_by_service = {}
    orig_qt_items = []
    orig_qt_alloc = {}
    for it in order_obj.items.all().order_by('id'):
        sid = it.service_id
        if sid not in orig_qty_map:
            orig_qty_map[sid] = {'adult': 0, 'child': 0, 'infant': 0}
        qty = int(it.quantity or 0)
        if it.ticket_type == 'ADULT':
            orig_qty_map[sid]['adult'] += qty
            held_paid_by_service[sid] = held_paid_by_service.get(sid, 0) + qty
            c_val = (it.cccd_number or '').strip()
            if ServicePrice.is_quang_tri_cccd(c_val) and not any(x['cccd'] == c_val for x in orig_qt_items):
                orig_qt_items.append({'cccd': c_val, 'service_id': sid})
                orig_qt_alloc[str(sid)] = orig_qt_alloc.get(str(sid), 0) + 1
        elif it.ticket_type == 'CHILD':
            orig_qty_map[sid]['child'] += qty
            held_paid_by_service[sid] = held_paid_by_service.get(sid, 0) + qty
        elif it.ticket_type == 'INFANT':
            orig_qty_map[sid]['infant'] += qty

    all_services = _get_all_services()
    service_packages = []
    for s in all_services:
        avail = _get_available_qty(s, target_date)
        if target_date == order_obj.visit_date:
            avail += held_paid_by_service.get(s['id'], 0)

        p_adult = s['price_weekend'] if is_weekend else s['price_weekday']
        p_child = s['price_child_weekend'] if is_weekend else s['price_child_weekday']
        p_qt = s['price_qt_weekend'] if is_weekend else s['price_qt_weekday']
        cur_q = orig_qty_map.get(s['id'], {'adult': 0, 'child': 0, 'infant': 0})

        service_packages.append({
            'id': s['id'],
            'service_code': s['service_code'],
            'name': s['name'],
            'is_active': s['is_active'],
            'cap': s['cap'],
            'available': avail,
            'highlights': s['highlights'],
            'price_adult': p_adult,
            'price_child': p_child,
            'price_qt': p_qt,
            'price_adult_fmt': _fmt_vnd(p_adult),
            'price_child_fmt': _fmt_vnd(p_child),
            'price_qt_fmt': _fmt_vnd(p_qt),
            'init_adult': cur_q['adult'],
            'init_child': cur_q['child'],
            'init_infant': cur_q['infant'],
        })

    orig_qt_cccds = [x['cccd'] for x in orig_qt_items]
    orig_customer = {
        'full_name': (order_obj.customer.customer_name or '').strip() if order_obj.customer else '',
        'phone': (order_obj.customer.phone or '').strip() if order_obj.customer else '',
        'email': (order_obj.customer.email or '').strip() if order_obj.customer else '',
        'cccd': orig_qt_items[0]['cccd'] if orig_qt_items else '',
    }
    rep_cccd_service_id = orig_qt_items[0]['service_id'] if orig_qt_items else 0
    extra_qt_items = orig_qt_items[1:] if len(orig_qt_items) > 1 else []

    form_customer = dict(orig_customer)
    cccd_confirmed_checked = bool(orig_qt_items)

    old_total = int(order_obj.total_amount or 0)
    inherited_meta = _calculate_inherited_discount(order_obj, old_total + int(order_obj.discount_amount or 0))
    voucher_info = {
        'has_voucher': inherited_meta['has_voucher'],
        'code': inherited_meta['code'],
        'type': inherited_meta['type'],
        'value': inherited_meta['value'],
        'max_discount': inherited_meta['max_discount'],
        'fixed_discount': inherited_meta['fixed_discount'],
        'short_badge': inherited_meta['short_badge'],
        'row_label': inherited_meta['row_label'],
    }

    error_msg = ''
    reason_note = ''
    active_tab = 'tickets'

    if request.method == 'POST':
        is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest')
        reason_note = (request.POST.get('exchange_reason') or '').strip()
        form_customer = {
            'full_name': (request.POST.get('full_name') or '').strip(),
            'phone': (request.POST.get('phone') or '').strip(),
            'email': (request.POST.get('email') or '').strip(),
            'cccd': (request.POST.get('cccd') or '').strip(),
        }
        raw_rep_sid = (request.POST.get('rep_cccd_service_id') or '').strip()
        rep_cccd_service_id = int(raw_rep_sid) if raw_rep_sid.isdigit() else 0

        posted_adult_sum = sum(
            max(0, int(request.POST.get(f"adult_qty_{p['id']}", 0) or 0))
            for p in service_packages
        )
        posted_all_sum = sum(
            max(0, int(request.POST.get(f"adult_qty_{p['id']}", 0) or 0))
            + max(0, int(request.POST.get(f"child_qty_{p['id']}", 0) or 0))
            + max(0, int(request.POST.get(f"infant_qty_{p['id']}", 0) or 0))
            for p in service_packages
        )

        parsed_extra_pairs = []
        if posted_all_sum > 1 and posted_adult_sum > 1:
            for raw_tok in (request.POST.get('qt_cccd_list') or '').split(','):
                tok = raw_tok.strip()
                if not tok:
                    continue
                if ':' in tok:
                    c_part, s_part = tok.split(':', 1)
                    parsed_extra_pairs.append({
                        'cccd': c_part.strip(),
                        'service_id': int(s_part) if s_part.strip().isdigit() else 0,
                    })
                else:
                    parsed_extra_pairs.append({'cccd': tok, 'service_id': 0})
            parsed_extra_pairs = parsed_extra_pairs[:max(0, posted_adult_sum - 1)]

        extra_qt_items = parsed_extra_pairs
        cccd_confirmed_checked = (request.POST.get('cccd_confirmed') == '1')

        if not form_customer['full_name']:
            error_msg = 'Vui lòng nhập họ và tên khách hàng.'
            active_tab = 'info'
        elif not (len(form_customer['phone']) == 10 and form_customer['phone'].isdigit() and form_customer['phone'].startswith('0')):
            error_msg = 'Số điện thoại phải gồm đúng 10 chữ số và bắt đầu bằng số 0.'
            active_tab = 'info'
        elif '@' not in form_customer['email'] or '.' not in form_customer['email']:
            error_msg = 'Địa chỉ email không hợp lệ để nhận mã vé QR mới.'
            active_tab = 'info'
        elif form_customer['cccd'] and not (len(form_customer['cccd']) == 12 and form_customer['cccd'].isdigit()):
            error_msg = 'Số CCCD người đại diện phải gồm đúng 12 chữ số.'
            active_tab = 'info'
        elif any(not (len(item['cccd']) == 12 and item['cccd'].isdigit()) for item in parsed_extra_pairs):
            error_msg = 'Mỗi số CCCD người đi cùng phải gồm đúng 12 chữ số.'
            active_tab = 'info'

        has_any_cccd = bool(form_customer['cccd']) or bool(parsed_extra_pairs)
        if not error_msg and has_any_cccd and not cccd_confirmed_checked:
            error_msg = 'Vui lòng tick xác nhận số CCCD đã nhập là chính xác và sẵn sàng xuất trình khi check-in.'
            active_tab = 'info'

        now = timezone.localtime()
        new_checkin_dt = timezone.make_aware(datetime.combine(target_date, time(9, 0)), timezone.get_current_timezone())

        if not error_msg and (new_checkin_dt - now).total_seconds() < 48 * 3600:
            error_msg = 'Ngày sử dụng mới phải cách thời điểm hiện tại tối thiểu 48 giờ.'
        elif not error_msg and request.POST.get('confirm_exchange') != '1':
            error_msg = 'Vui lòng tick xác nhận đồng ý đổi vé trước khi tiếp tục.'

        pkg_quantities = {}
        total_paid_tickets = 0
        if not error_msg:
            for pkg in service_packages:
                sid = pkg['id']
                adult_qty = max(0, int(request.POST.get(f'adult_qty_{sid}', 0) or 0))
                child_qty = max(0, int(request.POST.get(f'child_qty_{sid}', 0) or 0))
                infant_qty = max(0, int(request.POST.get(f'infant_qty_{sid}', 0) or 0))
                pkg_paid_qty = adult_qty + child_qty

                if pkg_paid_qty == 0 and infant_qty == 0:
                    continue
                if pkg_paid_qty == 0 and infant_qty > 0:
                    error_msg = 'Trẻ em dưới 1m miễn phí vé cần đi kèm ít nhất 01 vé có tính phí.'
                    break
                if not pkg['is_active']:
                    error_msg = f"Gói {pkg['name']} hiện đang tạm ngừng phục vụ."
                    break
                if pkg_paid_qty > pkg['available']:
                    error_msg = f"Gói {pkg['name']} chỉ còn {pkg['available']} vé trống trong ngày {target_date.strftime('%d/%m/%Y')}."
                    break

                total_paid_tickets += pkg_paid_qty
                pkg_quantities[sid] = {
                    'pkg': pkg,
                    'adult_qty': adult_qty,
                    'rem_adult': adult_qty,
                    'child_qty': child_qty,
                    'infant_qty': infant_qty,
                    'assigned_qt_cccds': [],
                }

        if not error_msg and total_paid_tickets == 0:
            error_msg = 'Vui lòng chọn ít nhất 01 vé có tính phí.'

        valid_qt_cccds = []
        new_qt_alloc = {}
        if not error_msg:
            seen_cccds = set()
            rep_c = form_customer['cccd']
            if ServicePrice.is_quang_tri_cccd(rep_c):
                rep_target_sid = (
                    rep_cccd_service_id
                    if (rep_cccd_service_id in pkg_quantities and pkg_quantities[rep_cccd_service_id]['rem_adult'] > 0)
                    else next((s for s, inf in pkg_quantities.items() if inf['rem_adult'] > 0), None)
                )
                if rep_target_sid is not None:
                    pkg_quantities[rep_target_sid]['rem_adult'] -= 1
                    pkg_quantities[rep_target_sid]['assigned_qt_cccds'].append(rep_c)
                    seen_cccds.add(rep_c)
                    valid_qt_cccds.append(rep_c)
                    new_qt_alloc[str(rep_target_sid)] = new_qt_alloc.get(str(rep_target_sid), 0) + 1

            for item in parsed_extra_pairs:
                c_code = item['cccd']
                if not ServicePrice.is_quang_tri_cccd(c_code) or c_code in seen_cccds:
                    continue
                pref_sid = item['service_id']
                target_sid = pref_sid if (pref_sid in pkg_quantities and pkg_quantities[pref_sid]['rem_adult'] > 0) else None
                if target_sid is None:
                    target_sid = next((s for s, inf in pkg_quantities.items() if inf['rem_adult'] > 0), None)
                if target_sid is not None:
                    pkg_quantities[target_sid]['rem_adult'] -= 1
                    pkg_quantities[target_sid]['assigned_qt_cccds'].append(c_code)
                    seen_cccds.add(c_code)
                    valid_qt_cccds.append(c_code)
                    new_qt_alloc[str(target_sid)] = new_qt_alloc.get(str(target_sid), 0) + 1

        parsed_lines = []
        new_subtotal = 0
        if not error_msg:
            for sid, info in pkg_quantities.items():
                pkg = info['pkg']
                qt_adult_qty = len(info['assigned_qt_cccds'])
                reg_adult_qty = info['adult_qty'] - qt_adult_qty
                line_total = (
                    reg_adult_qty * pkg['price_adult']
                    + qt_adult_qty * pkg['price_qt']
                    + info['child_qty'] * pkg['price_child']
                )
                new_subtotal += line_total
                parsed_lines.append({
                    'service_id': sid,
                    'reg_adult_qty': reg_adult_qty,
                    'price_adult': pkg['price_adult'],
                    'assigned_qt_cccds': info['assigned_qt_cccds'],
                    'price_qt': pkg['price_qt'],
                    'child_qty': info['child_qty'],
                    'price_child': pkg['price_child'],
                    'infant_qty': info['infant_qty'],
                })

            new_qty_sig = {
                ln['service_id']: (ln['reg_adult_qty'] + len(ln['assigned_qt_cccds']), ln['child_qty'], ln['infant_qty'])
                for ln in parsed_lines
            }
            old_qty_sig = {
                sid: (v['adult'], v['child'], v['infant'])
                for sid, v in orig_qty_map.items()
                if (v['adult'] + v['child'] + v['infant']) > 0
            }
            customer_changed = (
                form_customer['full_name'] != orig_customer['full_name']
                or form_customer['phone'] != orig_customer['phone']
                or form_customer['email'].lower() != orig_customer['email'].lower()
                or valid_qt_cccds != orig_qt_cccds
                or new_qt_alloc != orig_qt_alloc
            )
            if target_date == order_obj.visit_date and new_qty_sig == old_qty_sig and not customer_changed:
                error_msg = 'Bạn chưa thay đổi ngày sử dụng, gói dịch vụ, số lượng vé hoặc thông tin khách hàng nào so với đơn hiện tại.'

        if not error_msg:
            # Kế thừa ưu đãi từ đơn cũ (không cho phép nhập hoặc áp mã mới)
            inherited_calc = _calculate_inherited_discount(order_obj, new_subtotal)
            new_discount = inherited_calc['discount_amount']
            new_total = max(0, new_subtotal - new_discount)
            diff_amount = new_total - old_total

            if diff_amount < 0:
                if inherited_calc['has_voucher']:
                    error_msg = (
                        f"Vé chỉ được đổi ngang giá hoặc cao hơn số tiền đã thanh toán ở đơn cũ ({_fmt_vnd(old_total)}). "
                        f"Sau khi áp dụng giảm giá kế thừa ({inherited_calc['short_badge']}: -{_fmt_vnd(new_discount)}), "
                        f"giá trị đơn mới sau giảm là {_fmt_vnd(new_total)}, thấp hơn {_fmt_vnd(abs(diff_amount))}."
                    )
                else:
                    error_msg = (
                        f"Vé chỉ được đổi ngang giá hoặc cao hơn giá trị đơn đã thanh toán ({_fmt_vnd(old_total)}). "
                        f"Giá trị đơn mới hiện tại là {_fmt_vnd(new_total)}, thấp hơn {_fmt_vnd(abs(diff_amount))}."
                    )

        if error_msg and is_ajax:
            return JsonResponse({
                'ok': False,
                'error': error_msg,
                'active_tab': active_tab,
            }, status=400)

        if not error_msg:
            customer_payload = {
                'full_name': form_customer['full_name'],
                'phone': form_customer['phone'],
                'email': form_customer['email'],
                'rep_cccd': form_customer['cccd'],
            }

            if diff_amount > 0:
                txn_obj = PaymentTransaction.objects.create(
                    order=order_obj,
                    transaction_type='INITIAL',
                    payment_method='E_WALLET',
                    amount=Decimal(diff_amount),
                    payment_status='Pending',
                )
                exchange_payload = {
                    'order_id': order_obj.order_id,
                    'visit_date': target_date.isoformat(),
                    'total_quantity': total_paid_tickets,
                    'discount_amount': new_discount,
                    'new_total': new_total,
                    'diff_amount': diff_amount,
                    'back_q': back_q,
                    'back_lookup_url': back_lookup_url,
                    'lines': parsed_lines,
                    'customer_data': customer_payload,
                }
                cache_key = f'pending_exchange_{txn_obj.transaction_id}'
                request.session[cache_key] = exchange_payload
                request.session.modified = True
                cache.set(cache_key, exchange_payload, timeout=3600)
                cache.set(f'exchange_back_{txn_obj.transaction_id}', back_lookup_url, timeout=3600)

                vnpay_url = _build_vnpay_payment_url(request, order_obj, txn_obj)
                if is_ajax:
                    return JsonResponse({
                        'ok': True,
                        'requires_payment': True,
                        'transaction_id': txn_obj.transaction_id,
                        'payment_url': vnpay_url,
                        'diff_amount': diff_amount,
                        'diff_amount_fmt': _fmt_vnd(diff_amount),
                        'target_date_display': target_date.strftime('%d/%m/%Y'),
                        'email': form_customer['email'],
                        'lookup_url': back_lookup_url,
                    })
                return redirect(vnpay_url)

            with transaction.atomic():
                locked_order = Order.objects.select_for_update().get(pk=order_obj.pk)
                if locked_order.has_been_exchanged:
                    dup_msg = f'Đơn hàng {locked_order.order_id} đã thực hiện đổi vé 1 lần trước đó. Mỗi đơn chỉ được đổi vé tối đa 01 lần.'
                    if is_ajax:
                        return JsonResponse({'ok': False, 'error': dup_msg}, status=400)
                    messages.error(request, dup_msg)
                    return redirect(back_lookup_url)

                _apply_reschedule_customer_update(locked_order, customer_payload)

                locked_order.items.all().delete()
                for ln in parsed_lines:
                    sid = ln['service_id']
                    if ln['reg_adult_qty'] > 0:
                        OrderItem.objects.create(
                            order=locked_order,
                            service_id=sid,
                            ticket_type='ADULT',
                            cccd_number=None,
                            quantity=ln['reg_adult_qty'],
                            unit_price=Decimal(ln['price_adult']),
                        )
                    for q_cccd in ln['assigned_qt_cccds']:
                        OrderItem.objects.create(
                            order=locked_order,
                            service_id=sid,
                            ticket_type='ADULT',
                            cccd_number=q_cccd,
                            quantity=1,
                            unit_price=Decimal(ln['price_qt']),
                        )
                    if ln['child_qty'] > 0:
                        OrderItem.objects.create(
                            order=locked_order,
                            service_id=sid,
                            ticket_type='CHILD',
                            cccd_number=None,
                            quantity=ln['child_qty'],
                            unit_price=Decimal(ln['price_child']),
                        )
                    if ln['infant_qty'] > 0:
                        OrderItem.objects.create(
                            order=locked_order,
                            service_id=sid,
                            ticket_type='INFANT',
                            cccd_number=None,
                            quantity=ln['infant_qty'],
                            unit_price=Decimal(0),
                        )

                locked_order.visit_date = target_date
                locked_order.total_quantity = total_paid_tickets
                locked_order.discount_amount = Decimal(new_discount)
                locked_order.total_amount = Decimal(new_total)
                locked_order.exchange_time = timezone.now()
                if locked_order.order_status == 'Paid':
                    locked_order.qr_code = f"BOS-{locked_order.order_id}-{uuid.uuid4().hex[:6].upper()}"
                locked_order.save(update_fields=[
                    'visit_date', 'total_quantity', 'discount_amount', 'total_amount', 'exchange_time', 'qr_code'
                ])
                order_obj = locked_order

            _send_qr_ticket_email(order_obj, request=request)
            ok_msg = f"Đổi vé đơn {order_obj.order_id} thành công! Mã QR mới đã được cấp và gửi về email {form_customer['email']}."
            if is_ajax:
                return JsonResponse({
                    'ok': True,
                    'requires_payment': False,
                    'redirect_url': back_lookup_url,
                    'message': ok_msg,
                })
            messages.success(request, ok_msg)
            return redirect(back_lookup_url)

    order_detail = _serialize_order_detail(order_obj)
    context = {
        'services': all_services,
        'info_pages': INFO_PAGES,
        'order': order_detail,
        'policy': policy,
        'min_date_iso': min_reschedule_date.isoformat(),
        'orig_date_iso': order_obj.visit_date.isoformat(),
        'target_date_iso': target_date.isoformat(),
        'target_date_display': target_date.strftime('%d/%m/%Y'),
        'day_label': 'Cuối tuần (T7–CN)' if is_weekend else 'Đầu tuần (T2–T6)',
        'service_packages': service_packages,
        'packages_json': json.dumps(service_packages),
        'orig_qt_cccds_json': json.dumps(orig_qt_cccds),
        'orig_qt_alloc_json': json.dumps(orig_qt_alloc),
        'rep_cccd_service_id': rep_cccd_service_id,
        'extra_qt_items_json': json.dumps(extra_qt_items),
        'orig_customer_json': json.dumps(orig_customer, ensure_ascii=False),
        'form_customer': form_customer,
        'cccd_confirmed_checked': cccd_confirmed_checked,
        'voucher_info': voucher_info,
        'voucher_json': json.dumps(voucher_info, ensure_ascii=False),
        'old_total': old_total,
        'old_total_fmt': _fmt_vnd(old_total),
        'error_msg': error_msg,
        'reason_note': reason_note,
        'active_tab': active_tab,
        'back_q': back_q,
        'back_lookup_url': back_lookup_url,
    }
    return render(request, 'booking/reschedule_form.html', context)


def reschedule_ticket(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method != 'POST':
        return redirect('booking:lookup_ticket')

    order_code = (request.POST.get('order_code') or '').strip().upper()
    new_date_str = (request.POST.get('new_date') or '').strip()
    _, back_lookup_url = _resolve_back_lookup(request, order_code)

    def _err(msg):
        if is_ajax:
            return JsonResponse({'ok': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect(back_lookup_url)

    order_obj = _find_order_by_code(order_code)
    if not order_obj:
        return _err('Không tìm thấy thông tin đơn vé cần đổi.')

    policy = _evaluate_48h_policy(order_obj)
    if not policy['can_exchange']:
        return _err(policy['exchange_reason'])

    try:
        target_date = date.fromisoformat(new_date_str)
    except ValueError:
        return _err('Ngày sử dụng mới không hợp lệ.')

    now = timezone.localtime()
    new_checkin_dt = timezone.make_aware(datetime.combine(target_date, time(9, 0)), timezone.get_current_timezone())
    if target_date == order_obj.visit_date or (new_checkin_dt - now).total_seconds() < 48 * 3600:
        return _err('Ngày sử dụng mới không hợp lệ hoặc chưa đảm bảo cách hiện tại tối thiểu 48 giờ.')

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order_obj.pk)
        if locked_order.has_been_exchanged:
            return _err(f'Đơn hàng {locked_order.order_id} đã thực hiện đổi vé 1 lần trước đó. Mỗi đơn chỉ được đổi vé tối đa 01 lần.')

        calc = _recalculate_order_for_date(locked_order, target_date)
        if not calc['ok']:
            return _err(calc['error'])

        if calc['diff_amount'] < 0:
            return _err(f"Vé chỉ được đổi ngang giá hoặc cao hơn giá đơn cũ ({calc['old_total_fmt']}).")

        for row in calc['items']:
            item_obj = row['item_obj']
            item_obj.unit_price = Decimal(row['new_unit_price'])
            item_obj.save()

        locked_order.visit_date = target_date
        locked_order.discount_amount = Decimal(calc['new_discount'])
        locked_order.total_amount = Decimal(calc['new_total'])
        locked_order.exchange_time = now
        if locked_order.order_status == 'Paid':
            locked_order.qr_code = f"BOS-{locked_order.order_id}-{uuid.uuid4().hex[:6].upper()}"
        locked_order.save(update_fields=['visit_date', 'discount_amount', 'total_amount', 'exchange_time', 'qr_code'])
        
    ok_msg = (
        f"Đổi ngày đơn {order_code} thành công sang {calc['target_date_display']} ({calc['day_label']}). "
        f"Hệ thống đã cập nhật mã vé QR và gửi thông báo về email đăng ký."
    )
    if is_ajax:
        return JsonResponse({'ok': True, 'message': ok_msg, 'order_code': order_code, 'redirect_url': back_lookup_url})
    messages.success(request, ok_msg)
    return redirect(back_lookup_url)


def cancel_ticket(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method != 'POST':
        return redirect('booking:lookup_ticket')

    order_code = (request.POST.get('order_code') or '').strip().upper()
    _, back_lookup_url = _resolve_back_lookup(request, order_code)

    def _err(msg):
        if is_ajax:
            return JsonResponse({'ok': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect(back_lookup_url)

    order_obj = _find_order_by_code(order_code)
    if not order_obj:
        return _err('Không tìm thấy thông tin đơn vé cần hủy.')

    is_unpaid_online = (
        order_obj.channel == 'ONLINE'
        and order_obj.order_status == 'New'
        and order_obj.ticket_status == 'UNUSED'
    )
    if not is_unpaid_online:
        policy = _evaluate_48h_policy(order_obj)
        if not policy['can_modify']:
            return _err(policy['reason'])

    with transaction.atomic():
        was_paid = (order_obj.order_status == 'Paid')
        order_obj.ticket_status = 'VOID'
        order_obj.order_status = 'Cancelled'
        order_obj.cancel_time = timezone.now()
        order_obj.save(update_fields=['ticket_status', 'order_status', 'cancel_time'])

        if was_paid and order_obj.total_amount > 0:
            PaymentTransaction.objects.create(
                order=order_obj,
                transaction_type='REFUND',
                payment_method=order_obj.payment_method,
                amount=order_obj.total_amount,
                payment_status='Pending',
            )

    ok_msg = (
        f"Đã hủy đơn vé {order_code} thành công. Mã QR cũ đã vô hiệu hóa và lệnh hoàn tiền 100% đã được ghi nhận."
        if was_paid else
        f"Đã hủy đơn đặt vé {order_code} thành công và giải phóng số lượng vé trên hệ thống."
    )
    if is_ajax:
        return JsonResponse({'ok': True, 'message': ok_msg, 'order_code': order_code})
    messages.success(request, ok_msg)
    return redirect(back_lookup_url)


def info_page(request, slug):
    return redirect('/#eco-sec')


@require_GET
def api_exchange_status(request, txn_id):
    """API kiểm tra trạng thái giao dịch thanh toán bổ sung (PENDING / SUCCESS / FAILED)."""
    order_code = (request.GET.get('order_code') or '').strip()
    txn_key = str(txn_id).strip()
    txn = (
        PaymentTransaction.objects.select_related('order', 'order__customer')
        .filter(transaction_id=txn_key)
        .first()
    )
    if not txn and txn_key.isdigit():
        txn = (
            PaymentTransaction.objects.select_related('order', 'order__customer')
            .filter(pk=int(txn_key))
            .first()
        )

    if not txn:
        return JsonResponse({'status': 'FAILED', 'message': 'Không tìm thấy giao dịch thanh toán.'}, status=404)

    order_obj = txn.order
    if order_code and order_obj.order_id != order_code:
        return JsonResponse({'status': 'FAILED', 'message': 'Mã đơn hàng không khớp.'}, status=403)

    st = (txn.payment_status or '').strip()
    if st in ('Completed', 'Paid', 'Success'):
        saved_back_url = cache.get(f'exchange_back_{txn.transaction_id}')
        req_q = (request.GET.get('q') or '').strip()
        lookup_url = (
            saved_back_url
            or (f"{reverse('booking:lookup_ticket')}?{urlencode({'q': req_q})}" if req_q else None)
            or f"{reverse('booking:lookup_ticket')}?q={quote(order_obj.order_id)}"
        )
        return JsonResponse({
            'status': 'SUCCESS',
            'order_code': order_obj.order_id,
            'qr_code': order_obj.qr_code or '',
            'visit_date_display': order_obj.visit_date.strftime('%d/%m/%Y'),
            'total_tickets': order_obj.total_quantity,
            'total_amount_fmt': _fmt_vnd(int(order_obj.total_amount or 0)),
            'email': (order_obj.customer.email or '') if order_obj.customer else '',
            'lookup_url': lookup_url,
        })

    if st in ('Failed', 'Cancelled', 'Expired'):
        return JsonResponse({
            'status': 'FAILED',
            'message': 'Giao dịch thanh toán bổ sung không thành công hoặc đã bị hủy trên cổng VNPAY.',
        })

    return JsonResponse({'status': 'PENDING'})