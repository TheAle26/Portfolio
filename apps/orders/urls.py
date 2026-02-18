from django.urls import path
from . import views
from .views import MedicamentoDetailView

urlpatterns = [
    # Cliente
    path("cliente/", views.cliente_panel, name="cliente_panel"),
    path("cliente/pedido/<int:pedido_id>/", views.cliente_ver_pedido, name="cliente_ver_pedido"),
    
    path("cliente/carrito/finalizar_compra", views.finalizar_compra_view, name="finalizar_compra"),
    path('buscar/medicamentos/', views.buscar_medicamentos, name='buscar_medicamentos'),
    path('medicamento/<int:pk>/', MedicamentoDetailView.as_view(), name='medicamento_detalle'),
    
    
    # Farmacia
    path("farmacia/", views.farmacia_panel, name="farmacia_panel"),
    path("farmacia/pedidos/", views.farmacia_pedidos_entrantes, name="farmacia_pedidos"),
    path("farmacia/aceptar/<int:pedido_id>/", views.farmacia_aceptar, name="farmacia_aceptar"),
    path("farmacia/rechazar/<int:pedido_id>/", views.farmacia_rechazar, name="farmacia_rechazar"),
    path("farmacia/inventario/", views.farmacia_gestionar_inventario, name="gestionar_inventario"),
    path("farmacia/inventario/modificar/<int:stock_id>/", views.farmacia_editar_stock, name="editar_stock"),

    # Repartidor
    path("repartidor/", views.repartidor_panel, name="repartidor_panel"),
    path("repartidor/pedidos/", views.repartidor_ver_pedidos, name="repartidor_pedidos"),
    path("repartidor/tomar/<int:pedido_id>/", views.repartidor_tomar, name="repartidor_tomar"),
    path("repartidor/entregado/<int:pedido_id>/", views.repartidor_entregado, name="repartidor_entregado"),
    path("repartidor/entregar/<int:pedido_id>/", views.repartidor_entregar_pedido, name="repartidor_entregar_pedido"),
    path("repartidor/aceptar/<int:pedido_id>/", views.repartidor_aceptar, name="repartidor_aceptar"),
    path("repartidor/pedido_actual/", views.repartidor_ver_pedido_actual, name="repartidor_ver_pedido_actual"),
    
    # Panel principal (redirige según tipo de perfil)
    path("panel/", views.panel_principal, name="panel_principal"),
    
    #carrito
    path("cliente/carrito/", views.ver_carrito, name="ver_carrito"),
    path('carrito/actualizar/<str:stock_id_str>/', views.update_cart_item, name='update_cart_item'),
    path('carrito/eliminar/<str:stock_id_str>/', views.remove_cart_item, name='remove_cart_item'),

]
