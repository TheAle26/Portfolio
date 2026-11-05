from django.urls import path, include

from . import cart, comparador, views, tracker

app_name = 'changomas'

urlpatterns = [
    # Rutas historicas: siguen apuntando a ChangoMas.
    path('', tracker.catalog, name='product_list'),
    path('ofertas/', tracker.offers, name='tracker_offers'),
    path('', include('changomas.personal_urls')),
    path('escanear/', views.scan_page, name='scan'),
    path('producto/<str:code>/', tracker.detail, name='product_detail'),
    # Comparador entre tiendas. Debe declararse ANTES que <slug:store>/
    # para que 'comparador' no se interprete como slug de supermercado.
    path('comparador/', comparador.product_list, name='comparador_list'),
    path('comparador/escanear/', comparador.scan_page, name='comparador_scan'),
    path(
        'comparador/producto/<str:code>/',
        comparador.product_detail,
        name='comparador_detail',
    ),
    # Carrito. Igual que 'comparador', antes que <slug:store>/.
    path('api/quote-html/', tracker.cart_quote, name='tracker_quote'),
    path('carrito/', tracker.cart_page, name='cart'),
    path('carrito/cotizar/', cart.cart_quote, name='cart_quote'),
    # Rutas explicitas por supermercado para evitar EAN ambiguos.
    path('<slug:store>/', views.product_list, name='store_product_list'),
    path('<slug:store>/escanear/', views.scan_page, name='store_scan'),
    path(
        '<slug:store>/producto/<str:code>/',
        views.product_detail,
        name='store_product_detail',
    ),
]
