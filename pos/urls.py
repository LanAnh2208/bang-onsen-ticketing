from django.urls import path
from . import views

app_name = 'pos'
urlpatterns = [
    path('', views.pos_home, name='pos_home'),
]