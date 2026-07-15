from django.urls import path

from . import views

app_name = 'changomas'

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('escanear/', views.scan_page, name='scan'),
    path('producto/<str:code>/', views.product_detail, name='product_detail'),
]
