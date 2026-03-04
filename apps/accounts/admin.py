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
    list_filter = ('valido',)
    search_fields = ('nombre', 'cuit', 'user__email')
    list_editable = ('valido',)


@admin.register(Repartidor)
class RepartidorAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'vehiculo', 'disponible', 'valido')
    list_filter = ('valido', 'disponible', 'vehiculo')
    search_fields = ('user__email', 'cuit', 'patente')
    list_editable = ('disponible', 'valido')

