from django.urls import path

from . import comparador, views

app_name = 'changomas'

urlpatterns = [
    # Rutas historicas: siguen apuntando a ChangoMas.
    path('', views.product_list, name='product_list'),
    path('escanear/', views.scan_page, name='scan'),
    path('producto/<str:code>/', views.product_detail, name='product_detail'),
    # Comparador entre tiendas. Debe declararse ANTES que <slug:store>/
    # para que 'comparador' no se interprete como slug de supermercado.
    path('comparador/', comparador.product_list, name='comparador_list'),
    path('comparador/escanear/', comparador.scan_page, name='comparador_scan'),
    path(
        'comparador/producto/<str:code>/',
        comparador.product_detail,
        name='comparador_detail',
    ),
    # Rutas explicitas por supermercado para evitar EAN ambiguos.
    path('<slug:store>/', views.product_list, name='store_product_list'),
    path('<slug:store>/escanear/', views.scan_page, name='store_scan'),
    path(
        '<slug:store>/producto/<str:code>/',
        views.product_detail,
        name='store_product_detail',
    ),
]
