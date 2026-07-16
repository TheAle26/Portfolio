from django.urls import path

from . import views

app_name = 'changomas'

urlpatterns = [
    # Rutas historicas: siguen apuntando a ChangoMas.
    path('', views.product_list, name='product_list'),
    path('escanear/', views.scan_page, name='scan'),
    path('producto/<str:code>/', views.product_detail, name='product_detail'),
    # Rutas explicitas por supermercado para evitar EAN ambiguos.
    path('<slug:store>/', views.product_list, name='store_product_list'),
    path('<slug:store>/escanear/', views.scan_page, name='store_scan'),
    path(
        '<slug:store>/producto/<str:code>/',
        views.product_detail,
        name='store_product_detail',
    ),
]
