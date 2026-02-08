# tracking/models.py
from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

# 1. COMPANY
class Company(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# 2. FUEL TYPE (NUEVO)
class FuelType(models.Model):
    name = models.CharField(max_length=50, help_text="e.g.: Diesel Premium YPF")
    price_per_liter = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price in $")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='fuel_types')

    def __str__(self):
        return f"{self.name} (${self.price_per_liter})"

# 3. DEVICE
class Device(models.Model):
    DEVICE_TYPES = [
        ('truck', 'Truck'),
        ('car', 'Car'),
        ('motorcycle', 'Motorcycle'),
        ('van', 'Van'),
    ]
    
    name = models.CharField(max_length=100)
    imei = models.CharField(max_length=50, unique=True)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES, default='car')
    
    # Relaciones
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='devices')
    
    # CAMBIO IMPORTANTE: related_name='assigned_devices' (Inglés)
    allowed_users = models.ManyToManyField(User, related_name='assigned_devices', blank=True)
    
    # NUEVO: Tipo de combustible
    fuel_type = models.ForeignKey(FuelType, on_delete=models.SET_NULL, null=True, blank=True, related_name='devices')
    
    # Estado
    is_online = models.BooleanField(default=False)
    last_update = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.imei})"

# 4. EMPLOYEE (Opcional, si lo usas)
class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    can_assign = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

# 5. TELEMETRY
class Telemetry(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='telemetries')
    timestamp = models.DateTimeField(db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    speed = models.FloatField(default=0)
    ignition = models.BooleanField(default=False)
    odometer = models.FloatField(default=0)
    
    fuel_level = models.FloatField(null=True, blank=True)
    battery_voltage = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['device', 'timestamp']),
        ]

# 6. DAILY REPORT
class DailyReport(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='reports')
    date = models.DateField(db_index=True)
    
    # Estadísticas
    distance_km = models.FloatField(default=0)
    max_speed = models.FloatField(default=0)
    avg_speed = models.FloatField(default=0)
    engine_hours = models.DurationField(null=True)
    
    # NOMBRES CORREGIDOS (Para que coincidan con admin.py)
    total_fuel_liters = models.FloatField(default=0)
    idle_fuel_liters = models.FloatField(default=0)
    
    # Dinero
    wasted_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ('device', 'date')