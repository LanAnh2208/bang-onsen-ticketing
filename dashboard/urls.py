from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.overview, name='overview'),
    path('pricing/', views.pricing_matrix, name='pricing_matrix'),
    path('vouchers/', views.voucher_list, name='voucher_list'),
    path('staff/', views.staff_list, name='staff_list'),
]