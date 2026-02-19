# tracking/management/commands/poblar_base.py
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
User = get_user_model()
from tracking.models import Company, FuelType, Device, Employee, Telemetry, DailyReport

class Command(BaseCommand):
    help = 'Carga datos de prueba iniciales de forma segura (sin duplicar)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('--- INICIANDO CARGA DE DATOS ---'))

        # 1. CREAR USUARIOS
        # Admin
        admin_user, created = User.objects.get_or_create(
            username='admin_test', 
            defaults={'email': 'admin@test.com'}
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.is_superuser = True
            admin_user.is_staff = True
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Usuario Admin creado: admin_test / admin123"))
        else:
            self.stdout.write("Usuario Admin ya existe. Omitiendo...")

        # Empleado (Alejo)
        alejo_user, created = User.objects.get_or_create(username='test',defaults={'email': 'test@test.com'})
        if created:
            alejo_user.set_password('test123')
            alejo_user.save()
            self.stdout.write(self.style.SUCCESS("User Ale creado: test / test123"))
        else:
            self.stdout.write("Usuario Alejo ya existe. Omitiendo...")

        # 2. CREAR EMPRESA
        empresa, created = Company.objects.get_or_create(name="Logistica La Plata S.A.")
        if created:
            self.stdout.write(f"Empresa creada: {empresa.name}")
        
        # Asignar Alejo a la empresa
        Employee.objects.get_or_create(
            user=alejo_user, 
            company=empresa, 
            defaults={'can_assign': True}
        )

        # 3. CREAR COMBUSTIBLES
        diesel, created = FuelType.objects.get_or_create(
            name="Diesel Premium YPF",
            company=empresa,
            defaults={'price_per_liter': 1150.50}
        )
        nafta, created = FuelType.objects.get_or_create(
            name="Nafta Super Shell",
            company=empresa,
            defaults={'price_per_liter': 980.00}
        )

        # 4. CREAR DISPOSITIVOS
        # Camión (Buscamos por IMEI que es único)
        camion, camion_creado = Device.objects.get_or_create(
            imei="123456789012345",
            defaults={
                'name': "Camión Scania 450",
                'device_type': "truck",
                'company': empresa,
                'fuel_type': diesel,
            }
        )
        if camion_creado:
            camion.allowed_users.add(alejo_user)
            self.stdout.write(self.style.SUCCESS(f"Dispositivo creado: {camion.name}"))

        # Auto
        auto, auto_creado = Device.objects.get_or_create(
            imei="987654321098765",
            defaults={
                'name': "Flota Gol Trend",
                'device_type': "car",
                'company': empresa,
                'fuel_type': nafta,
            }
        )
        if auto_creado:
            auto.allowed_users.add(alejo_user)
            self.stdout.write(self.style.SUCCESS(f"Dispositivo creado: {auto.name}"))

        # 5. GENERAR TELEMETRÍA (Solo si el camión es nuevo)
        now = timezone.now()
        
        if camion_creado:
            self.stdout.write("Generando ruta simulada para el camión nuevo...")
            lat_base = -34.9214
            lon_base = -57.9545
            
            for i in range(50):
                timestamp = now - timedelta(minutes=i*2)
                lat = lat_base + (i * 0.01) 
                lon = lon_base + (random.uniform(-0.01, 0.01))
                speed = random.randint(20, 80) if i < 40 else 0
                ignition = True if i < 40 else False
                
                Telemetry.objects.create(
                    device=camion,
                    timestamp=timestamp,
                    latitude=lat,
                    longitude=lon,
                    speed=speed,
                    ignition=ignition,
                    odometer=10000 + (i*2),
                    fuel_level=75.5
                )
        else:
            self.stdout.write("El camión ya existía. Omitiendo generación de telemetría histórica...")

        # 6. GENERAR REPORTE DIARIO (get_or_create por dispositivo y fecha)
        DailyReport.objects.get_or_create(
            device=camion,
            date=now.date(),
            defaults={
                'distance_km': 120.5,
                'max_speed': 85.0,
                'avg_speed': 60.0,
                'total_fuel_liters': 40.0,
                'idle_fuel_liters': 5.0,
                'wasted_cost': 5.0 * float(diesel.price_per_liter)
            }
        )

        self.stdout.write(self.style.SUCCESS('--- VERIFICACIÓN/CARGA COMPLETA ---'))