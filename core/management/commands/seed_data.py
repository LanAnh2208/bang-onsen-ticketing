from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import (
    User, Customer, Service, ServicePrice, Voucher,
    Order, OrderItem, PaymentTransaction, ShiftReconciliation
)


def get_next_weekday(base_date):
    d = base_date
    while d.weekday() in (5, 6):
        d += timedelta(days=1)
    return d


def get_next_weekend(base_date):
    d = base_date
    while d.weekday() not in (5, 6):
        d += timedelta(days=1)
    return d


class Command(BaseCommand):
    help = 'Nạp bộ dữ liệu mẫu hoàn chỉnh cho hệ thống bán vé Bang Onsen'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        next_wd = get_next_weekday(today + timedelta(days=1))
        next_we = get_next_weekend(today + timedelta(days=1))

        # ======================================================================
        # 1. TÀI KHOẢN QUẢN TRỊ VIÊN & NHÂN VIÊN LỄ TÂN
        # ======================================================================
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'full_name': 'Trần Minh Quản Trị',
                'email': 'admin@bangonsen.vn',
                'role': 'ADMIN',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('12345678')
            admin_user.save()

        letan1, created = User.objects.get_or_create(
            username='letan1',
            defaults={
                'full_name': 'Nguyễn Thị Thanh Hà',
                'email': 'ha.letan@bangonsen.vn',
                'role': 'RECEPTIONIST',
            }
        )
        if created:
            letan1.set_password('12345678')
            letan1.save()

        letan2, created = User.objects.get_or_create(
            username='letan2',
            defaults={
                'full_name': 'Lê Văn Hoàng Nam',
                'email': 'nam.letan@bangonsen.vn',
                'role': 'RECEPTIONIST',
            }
        )
        if created:
            letan2.set_password('12345678')
            letan2.save()

        # ======================================================================
        # 2. GÓI DỊCH VỤ & BẢNG GIÁ THỰC TẾ (ONSEN 3 TẠM NGƯNG HOẠT ĐỘNG)
        # ======================================================================
        catalog = [
            {
                'service_id': 'ONSEN_1',
                'service_name': 'Khu Onsen 1',
                'description': 'Gồm 7 bể tắm khoáng trong nhà, 1 phòng xông hơi tinh dầu, 1 phòng xông hơi khô, 5 bể tắm Onsen ngoài trời.',
                'daily_capacity': 200,
                'service_status': 'Active',
                'prices': [
                    ('ADULT', 'WEEKDAY', 1100000, 801900),
                    ('ADULT', 'WEEKEND', 1300000, 947700),
                    ('CHILD', 'WEEKDAY', 650000, 473850),
                    ('CHILD', 'WEEKEND', 850000, 619650),
                    ('INFANT', 'WEEKDAY', 0, 0),
                    ('INFANT', 'WEEKEND', 0, 0),
                ],
            },
            {
                'service_id': 'ONSEN_2',
                'service_name': 'Khu Onsen 2',
                'description': 'Gồm 5 bể tắm ngâm khoáng trong nhà, 1 phòng xông hơi tinh dầu, 1 xông hơi khô và 5 bể tắm Onsen ngoài trời.',
                'daily_capacity': 250,
                'service_status': 'Active',
                'prices': [
                    ('ADULT', 'WEEKDAY', 690000, 503010),
                    ('ADULT', 'WEEKEND', 750000, 546750),
                    ('CHILD', 'WEEKDAY', 490000, 357210),
                    ('CHILD', 'WEEKEND', 550000, 400950),
                    ('INFANT', 'WEEKDAY', 0, 0),
                    ('INFANT', 'WEEKEND', 0, 0),
                ],
            },
            {
                'service_id': 'ONSEN_3',
                'service_name': 'Khu Onsen 3',
                'description': 'Gồm 4 bể ngâm khoáng trong nhà và công viên nước ngoài trời với các trò chơi cầu trượt nước khổng lồ.',
                'daily_capacity': 300,
                'service_status': 'Inactive',  # Tạm ngưng hoạt động
                'prices': [
                    ('ADULT', 'WEEKDAY', 540000, 393660),
                    ('ADULT', 'WEEKEND', 590000, 430110),
                    ('CHILD', 'WEEKDAY', 390000, 284310),
                    ('CHILD', 'WEEKEND', 420000, 306180),
                    ('INFANT', 'WEEKDAY', 0, 0),
                    ('INFANT', 'WEEKEND', 0, 0),
                ],
            },
        ]

        services = {}
        for item in catalog:
            srv, _ = Service.objects.update_or_create(
                service_id=item['service_id'],
                defaults={
                    'service_name': item['service_name'],
                    'description': item['description'],
                    'daily_capacity': item['daily_capacity'],
                    'service_status': item['service_status'],
                }
            )
            services[item['service_id']] = srv
            for t_type, d_type, p_std, p_qt in item['prices']:
                ServicePrice.objects.update_or_create(
                    service=srv,
                    ticket_type=t_type,
                    day_type=d_type,
                    defaults={
                        'price': Decimal(p_std),
                        'quang_tri_price': Decimal(p_qt),
                    }
                )

        # ======================================================================
        # 3. HAI LOẠI VOUCHER KHUYẾN MÃI (NGOẠI TRỪ ƯU ĐÃI QUẢNG TRỊ)
        # ======================================================================
        v_percent, _ = Voucher.objects.get_or_create(
            voucher_code='ONSEN10',
            defaults={
                'discount_type': 'Percent',
                'discount_value': Decimal('10'),
                'valid_from': today - timedelta(days=7),
                'valid_to': today + timedelta(days=60),
                'usage_limit': 100,
                'used_count': 2,
                'voucher_status': 'Active',
            }
        )

        v_fixed, _ = Voucher.objects.get_or_create(
            voucher_code='CHAOHE100K',
            defaults={
                'discount_type': 'Fixed_Amount',
                'discount_value': Decimal('100000'),
                'valid_from': today - timedelta(days=7),
                'valid_to': today + timedelta(days=45),
                'usage_limit': 50,
                'used_count': 1,
                'voucher_status': 'Active',
            }
        )

        # ======================================================================
        # 4. DỮ LIỆU ĐƠN HÀNG MÔ PHỎNG, KHÁCH HÀNG, THANH TOÁN & CHECK-IN QR
        # ======================================================================
        if Order.objects.exists():
            self.stdout.write(self.style.WARNING('Dữ liệu đơn hàng mẫu đã tồn tại, bỏ qua bước tạo trùng đơn.'))
        else:
            def create_order_with_items(
                customer, channel, visit_date, items_spec, payment_method,
                voucher=None, created_by=None, created_time=None, original_order=None
            ):
                """Hàm trợ giúp tạo hóa đơn và tự động khớp đơn giá từ ServicePrice"""
                order = Order.objects.create(
                    customer=customer,
                    channel=channel,
                    total_quantity=sum(i['qty'] for i in items_spec),
                    visit_date=visit_date,
                    voucher=voucher,
                    discount_amount=Decimal('0'),
                    total_amount=Decimal('0'),
                    payment_method=payment_method,
                    order_status='New',
                    created_time=created_time or now,
                    created_by=created_by,
                    original_order=original_order,
                )
                raw_total = Decimal('0')
                for spec in items_spec:
                    oi = OrderItem.objects.create(
                        order=order,
                        service=spec['service'],
                        ticket_type=spec['ticket_type'],
                        cccd_number=spec.get('cccd'),
                        quantity=spec['qty'],
                    )
                    raw_total += oi.subtotal

                discount = Decimal('0')
                if voucher:
                    if voucher.discount_type == 'Percent':
                        discount = (raw_total * voucher.discount_value / Decimal('100')).quantize(Decimal('1'))
                    else:
                        discount = min(raw_total, voucher.discount_value)

                order.discount_amount = discount
                order.total_amount = max(Decimal('0'), raw_total - discount)
                order.save()
                return order

            # --- Tạo danh sách khách hàng mẫu ---
            c1 = Customer.objects.create(customer_name='Hoàng Minh Tuấn', phone='0905111222', email='tuan.hm@gmail.com', cccd_number='045092001122')
            c2 = Customer.objects.create(customer_name='Nguyễn Thị Mai Anh', phone='0914222333', email='maianh.nt@gmail.com', cccd_number='048195003344')
            c3 = Customer.objects.create(customer_name='Võ Văn Hùng', phone='0983333444', cccd_number='044088005566')
            c4 = Customer.objects.create(customer_name='Phạm Thu Hương', phone='0935444555')
            c5 = Customer.objects.create(customer_name='Đặng Quốc Bảo', phone='0977555666')
            c6 = Customer.objects.create(customer_name='Lê Thị Kim Ngân', phone='0906666777', email='kimngan.le@gmail.com', cccd_number='045198009900')
            c7 = Customer.objects.create(customer_name='Trần Đức Thắng', phone='0918777888', email='thang.td@gmail.com')
            c8 = Customer.objects.create(customer_name='Bùi Ngọc Ánh', phone='0945888999', email='anh.bn@gmail.com')
            c9 = Customer.objects.create(customer_name='Ngô Thanh Tùng', phone='0969999000', email='tung.ngo@gmail.com')

            # ĐƠN 1: Online - Đã thanh toán - Đã quét QR check-in (#1) - Có ưu đãi Quảng Trị + Trẻ em dưới 1m + Voucher
            o1 = create_order_with_items(
                customer=c1, channel='ONLINE', visit_date=today, payment_method='BANK_TRANSFER',
                voucher=v_percent, created_time=now - timedelta(hours=4),
                items_spec=[
                    {'service': services['ONSEN_1'], 'ticket_type': 'ADULT', 'cccd': '045092001122', 'qty': 1},
                    {'service': services['ONSEN_1'], 'ticket_type': 'ADULT', 'cccd': None, 'qty': 1},
                    {'service': services['ONSEN_1'], 'ticket_type': 'INFANT', 'cccd': None, 'qty': 1},
                ]
            )
            o1.issue_qr_ticket()
            o1.ticket_status = 'USED'
            o1.checked_in_at = now - timedelta(hours=2)
            o1.checked_in_by = letan1
            o1.save()
            PaymentTransaction.objects.create(
                order=o1, transaction_type='INITIAL', payment_method='BANK_TRANSFER',
                gateway_transaction_id='VQR-20261120001', bank_ref='FT26324001',
                amount=o1.total_amount, payment_status='Success', completed_time=now - timedelta(hours=4)
            )

            # ĐƠN 2: Online - Đã thanh toán - Đã quét QR check-in (#2)
            o2 = create_order_with_items(
                customer=c2, channel='ONLINE', visit_date=today, payment_method='E_WALLET',
                created_time=now - timedelta(hours=3),
                items_spec=[
                    {'service': services['ONSEN_2'], 'ticket_type': 'ADULT', 'qty': 2},
                    {'service': services['ONSEN_2'], 'ticket_type': 'CHILD', 'qty': 1},
                ]
            )
            o2.issue_qr_ticket()
            o2.ticket_status = 'USED'
            o2.checked_in_at = now - timedelta(hours=1, minutes=15)
            o2.checked_in_by = letan1
            o2.save()
            PaymentTransaction.objects.create(
                order=o2, transaction_type='INITIAL', payment_method='E_WALLET',
                gateway_transaction_id='VNP-20261120002', amount=o2.total_amount,
                payment_status='Success', completed_time=now - timedelta(hours=3)
            )

            # ĐƠN 3: Tại quầy POS - Tiền mặt - Đã xuất vé/check-in (#3) - 2 vé ưu đãi Quảng Trị tách dòng
            o3 = create_order_with_items(
                customer=c3, channel='COUNTER', visit_date=today, payment_method='CASH',
                created_by=letan1, created_time=now - timedelta(minutes=50),
                items_spec=[
                    {'service': services['ONSEN_2'], 'ticket_type': 'ADULT', 'cccd': '044088005566', 'qty': 1},
                    {'service': services['ONSEN_2'], 'ticket_type': 'CHILD', 'cccd': '044215007788', 'qty': 1},
                ]
            )
            o3.issue_qr_ticket()
            o3.ticket_status = 'USED'
            o3.checked_in_at = now - timedelta(minutes=45)
            o3.checked_in_by = letan1
            o3.save()
            PaymentTransaction.objects.create(
                order=o3, transaction_type='INITIAL', payment_method='CASH',
                amount=o3.total_amount, payment_status='Success', completed_time=now - timedelta(minutes=50)
            )

            # ĐƠN 4: Tại quầy POS - Chuyển khoản ngân hàng - Chưa check-in - Dùng Voucher 100k
            o4 = create_order_with_items(
                customer=c4, channel='COUNTER', visit_date=today, payment_method='BANK_TRANSFER',
                voucher=v_fixed, created_by=letan2, created_time=now - timedelta(minutes=30),
                items_spec=[
                    {'service': services['ONSEN_1'], 'ticket_type': 'ADULT', 'qty': 2},
                ]
            )
            o4.issue_qr_ticket()
            o4.save()
            PaymentTransaction.objects.create(
                order=o4, transaction_type='INITIAL', payment_method='BANK_TRANSFER',
                bank_ref='FT26324004', amount=o4.total_amount,
                payment_status='Success', completed_time=now - timedelta(minutes=30)
            )

            # ĐƠN 5: Tại quầy POS - Tiền mặt - Chưa check-in - Có trẻ em dưới 1m
            o5 = create_order_with_items(
                customer=c5, channel='COUNTER', visit_date=today, payment_method='CASH',
                created_by=letan2, created_time=now - timedelta(minutes=20),
                items_spec=[
                    {'service': services['ONSEN_2'], 'ticket_type': 'ADULT', 'qty': 1},
                    {'service': services['ONSEN_2'], 'ticket_type': 'CHILD', 'qty': 1},
                    {'service': services['ONSEN_2'], 'ticket_type': 'INFANT', 'qty': 1},
                ]
            )
            o5.issue_qr_ticket()
            o5.save()
            PaymentTransaction.objects.create(
                order=o5, transaction_type='INITIAL', payment_method='CASH',
                amount=o5.total_amount, payment_status='Success', completed_time=now - timedelta(minutes=20)
            )

            # ĐƠN 6: Online - Đã thanh toán - Vé cuối tuần sắp tới (chưa dùng)
            o6 = create_order_with_items(
                customer=c6, channel='ONLINE', visit_date=next_we, payment_method='BANK_TRANSFER',
                voucher=v_percent, created_time=now - timedelta(hours=5),
                items_spec=[
                    {'service': services['ONSEN_1'], 'ticket_type': 'ADULT', 'cccd': '045198009900', 'qty': 1},
                    {'service': services['ONSEN_1'], 'ticket_type': 'ADULT', 'qty': 1},
                ]
            )
            o6.issue_qr_ticket()
            o6.save()
            PaymentTransaction.objects.create(
                order=o6, transaction_type='INITIAL', payment_method='BANK_TRANSFER',
                gateway_transaction_id='VQR-20261120006', bank_ref='FT26324006',
                amount=o6.total_amount, payment_status='Success', completed_time=now - timedelta(hours=5)
            )

            # ĐƠN 7: Online - Đã thanh toán - Vé đầu tuần sắp tới (chưa dùng)
            o7 = create_order_with_items(
                customer=c7, channel='ONLINE', visit_date=next_wd, payment_method='CARD',
                created_time=now - timedelta(hours=6),
                items_spec=[
                    {'service': services['ONSEN_2'], 'ticket_type': 'ADULT', 'qty': 3},
                ]
            )
            o7.issue_qr_ticket()
            o7.save()
            PaymentTransaction.objects.create(
                order=o7, transaction_type='INITIAL', payment_method='CARD',
                gateway_transaction_id='POS-20261120007', amount=o7.total_amount,
                payment_status='Success', completed_time=now - timedelta(hours=6)
            )

            # ĐƠN 8: Online - Đơn đã HỦY (Cancelled) kèm giao dịch HOÀN TIỀN (REFUND)
            o8 = create_order_with_items(
                customer=c8, channel='ONLINE', visit_date=next_we, payment_method='BANK_TRANSFER',
                created_time=now - timedelta(hours=8),
                items_spec=[
                    {'service': services['ONSEN_1'], 'ticket_type': 'ADULT', 'qty': 2},
                ]
            )
            o8.order_status = 'Cancelled'
            o8.ticket_status = 'VOID'
            o8.cancel_time = now - timedelta(hours=3)
            o8.save()
            PaymentTransaction.objects.create(
                order=o8, transaction_type='INITIAL', payment_method='BANK_TRANSFER',
                gateway_transaction_id='VQR-20261120008', amount=o8.total_amount,
                payment_status='Success', completed_time=now - timedelta(hours=8)
            )
            PaymentTransaction.objects.create(
                order=o8, transaction_type='REFUND', payment_method='BANK_TRANSFER',
                bank_ref='REF26324008', amount=o8.total_amount,
                payment_status='Success', completed_time=now - timedelta(hours=3)
            )

            # ĐƠN 9 & ĐƠN 10: Cặp đơn ĐỔI VÉ (Nâng hạng từ Onsen 2 lên Onsen 1 + Thanh toán bổ sung)
            o9_old = create_order_with_items(
                customer=c9, channel='ONLINE', visit_date=next_wd, payment_method='BANK_TRANSFER',
                created_time=now - timedelta(hours=7),
                items_spec=[
                    {'service': services['ONSEN_2'], 'ticket_type': 'ADULT', 'qty': 2},
                ]
            )
            o9_old.order_status = 'Exchanged'
            o9_old.ticket_status = 'VOID'
            o9_old.exchange_time = now - timedelta(hours=1)
            o9_old.save()
            PaymentTransaction.objects.create(
                order=o9_old, transaction_type='INITIAL', payment_method='BANK_TRANSFER',
                gateway_transaction_id='VQR-20261120009', amount=o9_old.total_amount,
                payment_status='Success', completed_time=now - timedelta(hours=7)
            )

            o10_new = create_order_with_items(
                customer=c9, channel='ONLINE', visit_date=next_wd, payment_method='BANK_TRANSFER',
                created_time=now - timedelta(hours=1), original_order=o9_old,
                items_spec=[
                    {'service': services['ONSEN_1'], 'ticket_type': 'ADULT', 'qty': 2},
                ]
            )
            o10_new.issue_qr_ticket()
            o10_new.save()
            diff_amount = max(Decimal('0'), o10_new.total_amount - o9_old.total_amount)
            PaymentTransaction.objects.create(
                order=o10_new, transaction_type='ADDITIONAL', payment_method='BANK_TRANSFER',
                gateway_transaction_id='VQR-20261120010', bank_ref='FT26324010',
                amount=diff_amount, payment_status='Success', completed_time=now - timedelta(hours=1)
            )

        # ======================================================================
        # 5. LỊCH SỬ ĐỐI SOÁT CUỐI CA SÁNG & CA TỐI
        # ======================================================================
        ShiftReconciliation.objects.get_or_create(
            receptionist=letan1,
            shift_date=yesterday,
            shift_type='MORNING',
            defaults={
                'actual_cash': Decimal('1380000'),
                'cash_revenue': Decimal('1380000'),
                'non_cash_revenue': Decimal('2200000'),
                'note': 'Bàn giao ca sáng đầy đủ, quỹ tiền mặt khớp 100% với hệ thống.',
            }
        )

        ShiftReconciliation.objects.get_or_create(
            receptionist=letan2,
            shift_date=yesterday,
            shift_type='EVENING',
            defaults={
                'actual_cash': Decimal('2050000'),
                'cash_revenue': Decimal('2070000'),
                'non_cash_revenue': Decimal('3150000'),
                'note': 'Lệch thiếu 20.000đ do thối nhầm tiền lẻ khách đoàn lúc cao điểm, nhân viên đã xác nhận bù quỹ.',
            }
        )

        self.stdout.write(self.style.SUCCESS('Đã nạp toàn bộ dữ liệu mẫu Bang Onsen thành công!'))