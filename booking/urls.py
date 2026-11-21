from django.urls import path
from . import views

app_name = 'booking'

urlpatterns = [
    # Trang chủ & API kiểm tra tồn kho / lịch vé
    path('', views.home, name='home'),
    path('api/availability/', views.check_availability, name='check_availability'),
    path('api/calendar/<int:service_id>/', views.service_calendar, name='service_calendar'),

    # Các trang chức năng liên kết từ Trang chủ (đảm bảo không lỗi 404 khi bấm nút)
    path('onsen-<int:service_id>/', views.onsen_detail, name='onsen_detail'),
    path('khai-bao-thong-tin/', views.book_form, name='book_form'),
    path('tra-cuu-ve/', views.lookup_ticket, name='lookup'),
    path('dich-vu/<slug:slug>/', views.info_page, name='info_page'),
    path('cong-noi-bo/', views.staff_login_redirect, name='staff_login'),
]