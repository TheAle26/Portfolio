# tracking/admin.py
from django.contrib import admin
from .models import Company, Device, Employee, Telemetry, DailyReport, FuelType

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')

@admin.register(FuelType)
class FuelTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_per_liter', 'company')
    list_filter = ('company',)

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    # Agregamos 'fuel_type' a la lista
    list_display = ('name', 'imei', 'device_type', 'company', 'fuel_type', 'is_online')
    list_filter = ('company', 'device_type', 'is_online')
    search_fields = ('name', 'imei')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'can_assign')

@admin.register(Telemetry)
class TelemetryAdmin(admin.ModelAdmin):
    list_display = ('device', 'timestamp', 'speed', 'ignition')
    list_filter = ('device', 'timestamp')
    # Optimización para tablas grandes
    show_full_result_count = False 

@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    # Usamos los nombres correctos que definimos en models.py
    list_display = ('date', 'device', 'distance_km', 'total_fuel_liters', 'idle_fuel_liters', 'wasted_cost')
    list_filter = ('date', 'device')