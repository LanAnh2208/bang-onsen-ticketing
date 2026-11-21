from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    path('', views.counter_sale_view, name='counter_sale'),
    path('checkin/', views.qr_checkin_view, name='qr_checkin'),
    path('shift/', views.shift_reconciliation_view, name='shift_reconciliation'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]