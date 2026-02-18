# apps/accounts/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Cliente, Farmacia, Repartidor, ObraSocial




# --- 2. ADMIN DE PERFILES (Aquí está la solución) ---

# Registro simple para Cliente y ObraSocial (no pediste filtros para estos)
admin.site.register(Cliente)
admin.site.register(ObraSocial)

# Decorador para registrar el modelo Farmacia con su clase Admin personalizada
@admin.register(Farmacia)
class FarmaciaAdmin(admin.ModelAdmin):
    # Columnas que se ven en la lista
    list_display = ('nombre', 'user', 'cuit', 'valido')
    
    # 💥 AÑADE EL FILTRO POR EL CAMPO 'valido' 💥
    list_filter = ('valido',)
    
    # (Opcional) Para poder buscar farmacias
    search_fields = ('nombre', 'cuit', 'user__email')
    
    # (Opcional) Para poder validar/invalidar desde la lista
    list_editable = ('valido',)

# Decorador para registrar el modelo Repartidor con su clase Admin personalizada
@admin.register(Repartidor)
class RepartidorAdmin(admin.ModelAdmin):
    # Columnas que se ven en la lista
    list_display = ('__str__', 'vehiculo', 'disponible', 'valido')
    
    # 💥 AÑADE EL FILTRO POR EL CAMPO 'valido' (y otros útiles) 💥
    list_filter = ('valido', 'disponible', 'vehiculo')
    
    # (Opcional) Para poder buscar repartidores
    search_fields = ('user__email', 'cuit', 'patente')
    
    # (Opcional) Para poder validar/invalidar y marcar disponible
    list_editable = ('disponible', 'valido')

