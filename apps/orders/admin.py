from django.contrib import admin
from .models import Medicamento, StockMedicamento, Pedido, DetallePedido

@admin.register(Medicamento)
class MedicamentoAdmin(admin.ModelAdmin):
    list_display = ('nombre_comercial', 'concentracion', 'principio_activo', 'categoria', 'requiere_receta')
    search_fields = ('nombre_comercial', 'principio_activo', 'codigo_barra')
    list_filter = ('requiere_receta', 'categoria')
    ordering = ('nombre_comercial',)

@admin.register(StockMedicamento)
class StockMedicamentoAdmin(admin.ModelAdmin):
    list_display = ('medicamento', 'farmacia', 'stock_actual', 'precio')
    search_fields = ('medicamento__nombre_comercial', 'farmacia__nombre') 
    list_filter = ('farmacia',)
    

    autocomplete_fields = ['medicamento'] 



class DetallePedidoInline(admin.TabularInline):
    model = DetallePedido
    extra = 0  
    readonly_fields = ('subtotal',) 
    autocomplete_fields = ['medicamento']


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'farmacia', 'estado', 'total', 'metodo_pago', 'creado')
    list_filter = ('estado', 'metodo_pago', 'creado', 'farmacia')
    
    search_fields = ('id', 'cliente__user__email', 'farmacia__nombre', 'codigo_seguridad')
    
    inlines = [DetallePedidoInline]
    readonly_fields = ('creado', 'total', 'codigo_seguridad')

    fieldsets = (
        ('Información Principal', {
            'fields': ('cliente', 'farmacia', 'repartidor', 'estado')
        }),
        ('Detalles de Entrega y Pago', {
            'fields': ('direccion', 'metodo_pago', 'total', 'codigo_seguridad')
        }),
        ('Gestión de Rechazos', {
            'fields': ('motivo_rechazo', 'comentario_rechazo'),
            'classes': ('collapse',), # 
        }),
        ('Notas y Fechas', {
            'fields': ('detalles', 'creado')
        }),
    )