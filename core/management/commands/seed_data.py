from datetime import date, timedelta
from django.core.management.base import BaseCommand
from core.models import User, Service, ServicePrice, Voucher


class Command(BaseCommand):
    help = 'Nạp dữ liệu mẫu cho hệ thống bán vé Bang Onsen'

    def handle(self, *args, **kwargs):
        # 1. Tạo tài khoản lễ tân mẫu
        if not User.objects.filter(username='letan1').exists():
            User.objects.create_user(
                username='letan1', password='12345678',
                full_name='Nguyễn Thị Lễ Tân', role='RECEPTIONIST'
            )

        # 2. Tạo 3 gói dịch vụ Onsen & bảng giá
        services_data = [
            ('ONSEN_1', 'Gói Onsen 1 - Tắm khoáng tiêu chuẩn', 350000, 420000),
            ('ONSEN_2', 'Gói Onsen 2 - Khoáng nóng & Xông hơi', 500000, 600000),
            ('ONSEN_3', 'Gói Onsen 3 - Trọn gói Onsen & Ẩm thực', 750000, 880000),
        ]
        for s_id, s_name, weekday_adult, weekend_adult in services_data:
            service, _ = Service.objects.get_or_create(
                service_id=s_id,
                defaults={'service_name': s_name, 'daily_capacity': 200}
            )
            # Giá ngày thường & cuối tuần cho Người lớn và Trẻ em (70% giá người lớn), ưu đãi QT giảm 20%
            price_matrix = [
                ('ADULT', 'WEEKDAY', weekday_adult, int(weekday_adult * 0.8)),
                ('ADULT', 'WEEKEND', weekend_adult, int(weekend_adult * 0.8)),
                ('CHILD', 'WEEKDAY', int(weekday_adult * 0.7), int(weekday_adult * 0.55)),
                ('CHILD', 'WEEKEND', int(weekend_adult * 0.7), int(weekend_adult * 0.55)),
            ]
            for t_type, d_type, p_std, p_qt in price_matrix:
                ServicePrice.objects.get_or_create(
                    service=service, ticket_type=t_type, day_type=d_type,
                    defaults={'price': p_std, 'quang_tri_price': p_qt}
                )

        # 3. Tạo Voucher mẫu
        Voucher.objects.get_or_create(
            voucher_code='ONSEN10',
            defaults={
                'discount_type': 'Percent',
                'discount_value': 10,
                'valid_from': date.today(),
                'valid_to': date.today() + timedelta(days=90),
            }
        )
        self.stdout.write(self.style.SUCCESS('Đã nạp dữ liệu mẫu thành công!'))