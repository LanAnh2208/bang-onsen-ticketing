from django.urls import path
from . import views

app_name = 'booking'

urlpatterns = [
    path('', views.home, name='home'),
    path('api/availability/', views.check_availability, name='check_availability'),
    path('api/calendar/<int:service_id>/', views.service_calendar, name='service_calendar'),
    path('api/apply-voucher/', views.apply_voucher_api, name='apply_voucher_api'),
    path('api/lookup/', views.lookup_ticket_api, name='lookup_ticket_api'),
    path('api/check-reschedule/', views.check_reschedule_api, name='check_reschedule'),
    path('api/order-payment-status/<str:order_code>/', views.order_payment_status_api, name='order_payment_status_api'),
    path('api/exchange-status/<str:txn_id>/', views.api_exchange_status, name='api_exchange_status'),
    path('dat-ve/', views.book_form, name='book_form'),
    path('thanh-toan/<str:order_code>/', views.payment_page, name='payment_page'),
    path('thanh-toan/<str:order_code>/vnpay/', views.retry_vnpay_payment, name='retry_vnpay'),
    path('vnpay-return/', views.vnpay_return, name='vnpay_return'),
    path('onsen-<int:service_id>/', views.onsen_detail, name='onsen_detail'),
    path('tra-cuu/', views.lookup_ticket, name='lookup_ticket'),
    path('tra-cuu/doi-ngay/', views.reschedule_ticket, name='reschedule_ticket'),
    path('tra-cuu/huy-ve/', views.cancel_ticket, name='cancel_ticket'),
    path('doi-ve/<str:order_code>/', views.reschedule_page, name='reschedule_page'),
    path('thong-tin/<slug:slug>/', views.info_page, name='info_page'),
]