from django.contrib import admin
from .models import Empresa, Dispositivo, Empleado

class EmpleadoInline(admin.StackedInline):
    model = Empleado
    can_delete = False
    verbose_name_plural = 'Datos de Empresa'

# Esto nos permite ver a qué empresa pertenece el usuario desde la pantalla de Users
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

class UserAdmin(BaseUserAdmin):
    inlines = (EmpleadoInline,)

# Re-registramos el User admin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(Dispositivo)
class DispositivoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'imei', 'empresa')
    list_filter = ('empresa',)
    filter_horizontal = ('usuarios_permitidos',) # Interfaz linda para seleccionar muchos usuarios

admin.site.register(Empresa)