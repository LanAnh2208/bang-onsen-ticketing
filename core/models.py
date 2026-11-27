import uuid
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator, MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone

phone_validator = RegexValidator(
    regex=r'^0\d{9}$',
    message='Số điện thoại phải gồm đúng 10 chữ số và bắt đầu bằng số 0.'
)
cccd_validator = RegexValidator(
    regex=r'^\d{12}$',
    message='Số CCCD phải gồm đúng 12 chữ số.'
)

TICKET_TYPE_CHOICES = [
    ('ADULT', 'Người lớn và trẻ em trên 1.4m'),
    ('CHILD', 'Trẻ em từ 1m – 1.4m'),
    ('INFANT', 'Trẻ em dưới 1m (Miễn phí vé)'),
]

PAYMENT_METHOD_CHOICES = [
    ('CASH', 'Tiền mặt'),
    ('BANK_TRANSFER', 'Chuyển khoản ngân hàng / VietQR'),
    ('CARD', 'Thẻ ngân hàng / Máy POS'),
    ('E_WALLET', 'Cổng thanh toán VNPAY'),
]


# ==============================================================================
# 1. TÀI KHOẢN PHÂN QUYỀN
# ==============================================================================
class User(AbstractUser):
    ROLE_CHOICES = [
        ('ADMIN', 'Quản trị viên'),
        ('RECEPTIONIST', 'Nhân viên lễ tân'),
    ]
    STATUS_CHOICES = [
        ('Active', 'Đang hoạt động'),
        ('Inactive', 'Ngừng hoạt động'),
    ]

    account_id = models.CharField(max_length=15, unique=True, editable=False, verbose_name='Mã tài khoản')
    full_name = models.CharField(max_length=100, verbose_name='Họ và tên')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='RECEPTIONIST', verbose_name='Vai trò')
    account_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active', verbose_name='Trạng thái')

    def save(self, *args, **kwargs):
        if not self.account_id:
            self.account_id = f"ACC-{uuid.uuid4().hex[:8].upper()}"
        self.is_active = (self.account_status == 'Active')
        if self.is_superuser:
            self.role = 'ADMIN'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.username} - {self.role})"


# ==============================================================================
# 2. KHÁCH HÀNG
# ==============================================================================
class Customer(models.Model):
    customer_id = models.CharField(max_length=15, unique=True, editable=False, verbose_name='Mã khách hàng')
    customer_name = models.CharField(max_length=100, verbose_name='Họ tên khách hàng')
    phone = models.CharField(max_length=10, validators=[phone_validator], db_index=True, verbose_name='Số điện thoại')
    email = models.EmailField(max_length=100, null=True, blank=True, verbose_name='Email')
    cccd_number = models.CharField(max_length=12, validators=[cccd_validator], null=True, blank=True, verbose_name='Số CCCD')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')

    def save(self, *args, **kwargs):
        if not self.customer_id:
            self.customer_id = f"CUS-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer_name} - {self.phone}"


# ==============================================================================
# 3. DỊCH VỤ & BẢNG GIÁ
# ==============================================================================
class Service(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Đang kinh doanh'),
        ('Inactive', 'Tạm ngưng hoạt động'),
    ]

    service_id = models.CharField(max_length=10, unique=True, verbose_name='Mã gói dịch vụ')
    service_name = models.CharField(max_length=100, verbose_name='Tên gói dịch vụ')
    description = models.TextField(blank=True, verbose_name='Mô tả tiện ích bể khoáng')
    image = models.ImageField(upload_to='services/', null=True, blank=True, verbose_name='Hình ảnh minh họa')
    daily_capacity = models.PositiveIntegerField(default=200, verbose_name='Sức chứa vé tối đa/ngày')
    service_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active', verbose_name='Trạng thái')

    @classmethod
    def get_active_services(cls):
        return cls.objects.filter(service_status='Active')

    def __str__(self):
        return f"{self.service_id} - {self.service_name} ({self.get_service_status_display()})"


class ServicePrice(models.Model):
    DAY_TYPE_CHOICES = [
        ('WEEKDAY', 'Đầu tuần (T2 - T6)'),
        ('WEEKEND', 'Cuối tuần (T7 - CN)'),
    ]

    QUANG_TRI_CCCD_PREFIXES = ('044', '045')

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='prices', verbose_name='Gói dịch vụ')
    ticket_type = models.CharField(max_length=20, choices=TICKET_TYPE_CHOICES, default='ADULT', verbose_name='Loại vé')
    day_type = models.CharField(max_length=20, choices=DAY_TYPE_CHOICES, default='WEEKDAY', verbose_name='Khung ngày áp dụng')
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='Giá công bố')
    quang_tri_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True, verbose_name='Giá ưu đãi người Quảng Trị')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Cập nhật lần cuối')

    class Meta:
        unique_together = ('service', 'ticket_type', 'day_type')

    @staticmethod
    def get_day_type_for_date(target_date) -> str:
        return 'WEEKEND' if target_date.weekday() in (5, 6) else 'WEEKDAY'

    @classmethod
    def is_quang_tri_cccd(cls, cccd_number: str) -> bool:
        if not cccd_number:
            return False
        clean_cccd = str(cccd_number).strip()
        return (
            len(clean_cccd) == 12
            and clean_cccd.isdigit()
            and clean_cccd.startswith(cls.QUANG_TRI_CCCD_PREFIXES)
        )

    def get_applicable_price(self, cccd_number: str = None):
        if self.quang_tri_price is not None and self.is_quang_tri_cccd(cccd_number):
            return self.quang_tri_price
        return self.price

    def __str__(self):
        qt_str = f" | Ưu đãi QT: {self.quang_tri_price:,.0f}đ" if self.quang_tri_price is not None else ""
        return f"{self.service.service_name} - {self.get_ticket_type_display()} ({self.get_day_type_display()}): {self.price:,.0f}đ{qt_str}"


class PriceAuditLog(models.Model):
    service_price = models.ForeignKey(ServicePrice, on_delete=models.CASCADE, related_name='audit_logs', verbose_name='Cấu hình giá')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Người cập nhật')
    old_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Giá niêm yết cũ')
    new_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Giá niêm yết mới')
    old_quang_tri_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Giá ưu đãi QT cũ')
    new_quang_tri_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Giá ưu đãi QT mới')
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm cập nhật')


# ==============================================================================
# 4. VOUCHER
# ==============================================================================
class Voucher(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('Percent', 'Phần trăm (%)'),
        ('Fixed_Amount', 'Số tiền cố định (VNĐ)'),
    ]
    STATUS_CHOICES = [
        ('Active', 'Đang hiệu lực'),
        ('Inactive', 'Vô hiệu hóa'),
    ]

    voucher_code = models.CharField(max_length=20, unique=True, verbose_name='Mã Voucher')
    discount_type = models.CharField(max_length=15, choices=DISCOUNT_TYPE_CHOICES, verbose_name='Hình thức giảm')
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name='Mức giảm')
    valid_from = models.DateField(verbose_name='Ngày bắt đầu')
    valid_to = models.DateField(verbose_name='Ngày hết hạn')
    usage_limit = models.PositiveIntegerField(default=100, verbose_name='Số lượt dùng tối đa')
    used_count = models.PositiveIntegerField(default=0, verbose_name='Số lượt đã dùng')
    voucher_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active', verbose_name='Trạng thái')

    def clean(self):
        if self.valid_to and self.valid_from and self.valid_to < self.valid_from:
            raise ValidationError('Ngày hết hiệu lực phải lớn hơn hoặc bằng ngày bắt đầu.')
        if self.discount_type == 'Percent' and self.discount_value > 100:
            raise ValidationError('Mức giảm theo phần trăm không được vượt quá 100%.')

    def save(self, *args, **kwargs):
        if self.voucher_code:
            self.voucher_code = self.voucher_code.strip().upper()
        super().save(*args, **kwargs)

    def is_valid_today(self):
        today = timezone.localdate()
        return (
            self.voucher_status == 'Active'
            and self.valid_from <= today <= self.valid_to
            and self.used_count < self.usage_limit
        )

    def __str__(self):
        return f"{self.voucher_code} ({self.discount_value:,.0f} - {self.get_discount_type_display()})"


# ==============================================================================
# 5. HÓA ĐƠN & CHI TIẾT HÓA ĐƠN
# ==============================================================================
class Order(models.Model):
    CHANNEL_CHOICES = [
        ('COUNTER', 'Tại quầy (POS)'),
        ('ONLINE', 'Đặt trực tuyến (Website)'),
    ]
    ORDER_STATUS_CHOICES = [
        ('New', 'Chờ thanh toán'),
        ('Paid', 'Đã thanh toán'),
        ('Cancelled', 'Đã hủy'),
        ('Exchanged', 'Đã đổi vé'),
    ]
    TICKET_STATUS_CHOICES = [
        ('UNUSED', 'Chưa sử dụng'),
        ('USED', 'Đã check-in / Đã xuất vé giấy'),
        ('EXPIRED', 'Quá hạn check-in'),
        ('VOID', 'Đã hủy / Vô hiệu'),
    ]

    order_id = models.CharField(max_length=20, unique=True, editable=False, verbose_name='Mã đơn hàng')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders', verbose_name='Khách hàng')
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, verbose_name='Kênh bán')
    total_quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], verbose_name='Tổng số lượng vé')
    visit_date = models.DateField(verbose_name='Ngày sử dụng dịch vụ')

    voucher = models.ForeignKey(Voucher, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Voucher áp dụng')
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Số tiền được giảm')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='Tổng thanh toán')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name='Phương thức thanh toán')
    order_status = models.CharField(max_length=10, choices=ORDER_STATUS_CHOICES, default='New', verbose_name='Trạng thái đơn')

    ticket_id = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name='Mã vé điện tử hóa đơn')
    qr_code = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name='Chuỗi mã QR hóa đơn')
    ticket_status = models.CharField(max_length=10, choices=TICKET_STATUS_CHOICES, default='UNUSED', verbose_name='Trạng thái sử dụng vé')

    created_time = models.DateTimeField(default=timezone.now, verbose_name='Thời điểm tạo đơn')
    cancel_time = models.DateTimeField(null=True, blank=True, verbose_name='Thời điểm hủy đơn')
    exchange_time = models.DateTimeField(null=True, blank=True, verbose_name='Thời điểm đổi vé')
    checked_in_at = models.DateTimeField(null=True, blank=True, verbose_name='Thời điểm quét QR check-in')

    original_order = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='exchanged_orders', verbose_name='Đơn gốc trước khi đổi')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_orders', verbose_name='Nhân viên tạo đơn')
    checked_in_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='checked_in_orders', verbose_name='Nhân viên quét QR check-in')

    @property
    def expires_at(self):
        if self.channel == 'ONLINE':
            return self.created_time + timedelta(minutes=15)
        return None

    @property
    def is_expired(self):
        if self.channel == 'ONLINE' and self.order_status == 'New':
            return timezone.now() > self.expires_at
        return False

    @property
    def is_checkin_overdue(self):
        """Đơn online đã thanh toán nhưng đã qua ngày sử dụng mà chưa check-in."""
        if self.channel == 'COUNTER':
            return False
        if self.ticket_status == 'EXPIRED':
            return True
        return (
            self.order_status == 'Paid'
            and self.ticket_status == 'UNUSED'
            and self.visit_date < timezone.localdate()
        )

    @property
    def effective_ticket_status(self):
        if self.channel == 'COUNTER':
            return 'USED'
        if self.is_checkin_overdue:
            return 'EXPIRED'
        return self.ticket_status

    @property
    def can_cancel_or_exchange(self):
        return (
            self.channel == 'ONLINE'
            and self.order_status == 'Paid'
            and self.effective_ticket_status == 'UNUSED'
            and self.visit_date >= timezone.localdate()
        )

    @classmethod
    def sync_overdue_tickets(cls):
        """Đồng bộ hàng loạt các đơn online đã thanh toán nhưng quá ngày sử dụng sang trạng thái EXPIRED."""
        today = timezone.localdate()
        return cls.objects.filter(
            channel='ONLINE',
            order_status='Paid',
            ticket_status='UNUSED',
            visit_date__lt=today
        ).update(ticket_status='EXPIRED')

    def issue_qr_ticket(self):
        if not self.ticket_id:
            self.ticket_id = f"TKT-{uuid.uuid4().hex[:10].upper()}"
        if not self.qr_code:
            self.qr_code = f"BOS-{self.order_id}-{uuid.uuid4().hex[:6].upper()}"
        self.order_status = 'Paid'
        self.ticket_status = 'USED' if self.channel == 'COUNTER' else 'UNUSED'

    def save(self, *args, **kwargs):
        if not self.order_id:
            date_part = timezone.localtime().strftime('%y%m%d')
            self.order_id = f"ORD-{date_part}-{uuid.uuid4().hex[:6].upper()}"
        if self.channel == 'COUNTER':
            self.ticket_status = 'USED'
            if not self.checked_in_at:
                self.checked_in_at = self.created_time or timezone.now()
        elif (
            self.order_status == 'Paid'
            and self.ticket_status == 'UNUSED'
            and self.visit_date
            and self.visit_date < timezone.localdate()
        ):
            self.ticket_status = 'EXPIRED'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_id} ({self.get_channel_display()} - {self.order_status} / {self.effective_ticket_status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='Hóa đơn')
    service = models.ForeignKey(Service, on_delete=models.PROTECT, limit_choices_to={'service_status': 'Active'}, verbose_name='Gói dịch vụ Onsen')
    ticket_type = models.CharField(max_length=20, choices=TICKET_TYPE_CHOICES, default='ADULT', verbose_name='Loại vé')

    cccd_number = models.CharField(
        max_length=12, validators=[cccd_validator], null=True, blank=True,
        verbose_name='Số CCCD áp dụng ưu đãi'
    )
    is_quang_tri_local = models.BooleanField(default=False, editable=False, verbose_name='Được hưởng ưu đãi Quảng Trị')

    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], verbose_name='Số lượng vé')
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)],
        null=True, blank=True, verbose_name='Đơn giá lúc mua'
    )
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)],
        editable=False, default=0, verbose_name='Thành tiền'
    )

    def clean(self):
        if not self.pk and self.service_id and self.service.service_status != 'Active':
            raise ValidationError({'service': 'Gói dịch vụ này đang tạm ngưng hoạt động, vui lòng chọn gói khác.'})
        if self.cccd_number and self.quantity > 1:
            raise ValidationError({'quantity': 'Mỗi số CCCD ưu đãi Quảng Trị chỉ áp dụng cho 1 vé (Số lượng = 1). Vui lòng tách dòng riêng.'})

    def save(self, *args, **kwargs):
        self.clean()
        self.is_quang_tri_local = ServicePrice.is_quang_tri_cccd(self.cccd_number)

        if self.unit_price is None and self.order_id and self.service_id:
            day_type = ServicePrice.get_day_type_for_date(self.order.visit_date)
            price_rule = ServicePrice.objects.filter(
                service=self.service,
                ticket_type=self.ticket_type,
                day_type=day_type
            ).first()
            self.unit_price = price_rule.get_applicable_price(self.cccd_number) if price_rule else 0

        self.subtotal = (self.unit_price or 0) * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_id} | {self.service.service_name} - {self.get_ticket_type_display()} x{self.quantity}"


# ==============================================================================
# 6. GIAO DỊCH THANH TOÁN & HOÀN TIỀN
# ==============================================================================
class PaymentTransaction(models.Model):
    TXN_TYPE_CHOICES = [
        ('INITIAL', 'Thanh toán mua vé ban đầu'),
        ('ADDITIONAL', 'Thanh toán bổ sung chênh lệch đổi vé'),
        ('REFUND', 'Hoàn tiền hủy vé'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Đang xử lý'),
        ('Success', 'Thành công'),
        ('Failed', 'Thất bại'),
    ]

    transaction_id = models.CharField(max_length=30, unique=True, editable=False, verbose_name='Mã giao dịch nội bộ')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='transactions', verbose_name='Đơn hàng')
    transaction_type = models.CharField(max_length=15, choices=TXN_TYPE_CHOICES, default='INITIAL', verbose_name='Loại giao dịch')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='BANK_TRANSFER', verbose_name='Phương thức giao dịch')

    gateway_transaction_id = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name='Mã giao dịch cổng thanh toán')
    bank_ref = models.CharField(max_length=50, null=True, blank=True, verbose_name='Mã tham chiếu ngân hàng')

    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='Số tiền giao dịch')
    payment_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending', verbose_name='Trạng thái giao dịch')
    completed_time = models.DateTimeField(null=True, blank=True, verbose_name='Thời điểm hoàn tất')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm khởi tạo')

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            date_part = timezone.localtime().strftime('%y%m%d%H%M')
            self.transaction_id = f"TXN-{date_part}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_id} | {self.order.order_id} | {self.amount:,.0f}đ ({self.payment_status})"


# ==============================================================================
# 7. ĐỐI SOÁT CUỐI CA
# ==============================================================================
class ShiftReconciliation(models.Model):
    SHIFT_CHOICES = [
        ('MORNING', 'Ca sáng'),
        ('EVENING', 'Ca tối'),
    ]

    shift_id = models.CharField(max_length=15, unique=True, editable=False, verbose_name='Mã ca đối soát')
    receptionist = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='shift_reports',
        limit_choices_to={'role': 'RECEPTIONIST', 'account_status': 'Active'},
        verbose_name='Nhân viên lễ tân'
    )
    shift_date = models.DateField(default=timezone.localdate, verbose_name='Ngày làm việc')
    shift_type = models.CharField(max_length=10, choices=SHIFT_CHOICES, default='MORNING', verbose_name='Ca làm việc')

    actual_cash = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], verbose_name='Tiền mặt thực nhận cuối ca')
    cash_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Doanh thu tiền mặt hệ thống')
    non_cash_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Doanh thu không tiền mặt')
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Tổng doanh thu ca')
    cash_variance = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Chênh lệch tiền mặt')

    note = models.TextField(blank=True, verbose_name='Ghi chú giải trình chênh lệch')
    reconciled_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm chốt ca')

    class Meta:
        unique_together = ('receptionist', 'shift_date', 'shift_type')

    def save(self, *args, **kwargs):
        if not self.shift_id:
            shift_tag = 'S' if self.shift_type == 'MORNING' else 'T'
            date_part = self.shift_date.strftime('%y%m%d')
            self.shift_id = f"SHF-{date_part}-{shift_tag}{uuid.uuid4().hex[:3].upper()}"
        self.total_revenue = self.cash_revenue + self.non_cash_revenue
        self.cash_variance = self.actual_cash - self.cash_revenue
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.shift_id} - {self.receptionist.full_name} ({self.get_shift_type_display()} - {self.shift_date})"