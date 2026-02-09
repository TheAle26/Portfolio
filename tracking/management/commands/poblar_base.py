# tracking/management/commands/poblar_base.py
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from tracking.models import Company, FuelType, Device, Employee, Telemetry, DailyReport

class Command(BaseCommand):
    help = 'Carga datos de prueba iniciales para el sistema de tracking'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('--- INICIANDO CARGA DE DATOS ---'))

        # 1. LIMPIEZA (Opcional: borramos datos viejos para no duplicar)
        self.stdout.write("Limpiando base de datos antigua...")
        DailyReport.objects.all().delete()
        Telemetry.objects.all().delete()
        Device.objects.all().delete()
        FuelType.objects.all().delete()
        Employee.objects.all().delete()
        Company.objects.all().delete()
        # No borramos usuarios para no borrar al superuser actual si ya existe

        # 2. CREAR USUARIOS
        # Admin
        admin_user, created = User.objects.get_or_create(username='admin_test')
        if created:
            admin_user.set_password('admin123')
            admin_user.is_superuser = True
            admin_user.is_staff = True
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Usuario Admin creado: admin_test / admin123"))

        # Empleado (Alejo)
        alejo_user, created = User.objects.get_or_create(username='alejo')
        if created:
            alejo_user.set_password('alejo123')
            alejo_user.save()
            self.stdout.write(self.style.SUCCESS("Usuario Alejo creado: alejo / alejo123"))

        # 3. CREAR EMPRESA
        empresa = Company.objects.create(name="Logistica La Plata S.A.")
        
        # Asignar Alejo a la empresa
        Employee.objects.create(user=alejo_user, company=empresa, can_assign=True)
        self.stdout.write(f"Empresa creada: {empresa.name}")

        # 4. CREAR COMBUSTIBLES
        diesel = FuelType.objects.create(
            name="Diesel Premium YPF",
            price_per_liter=1150.50,
            company=empresa
        )
        nafta = FuelType.objects.create(
            name="Nafta Super Shell",
            price_per_liter=980.00,
            company=empresa
        )

        # 5. CREAR DISPOSITIVOS
        # Camión (Asociado a Diesel)
        camion = Device.objects.create(
            name="Camión Scania 450",
            imei="123456789012345",
            device_type="truck",
            company=empresa,
            fuel_type=diesel,
            is_online=True,
            last_update=timezone.now()
        )
        camion.allowed_users.add(alejo_user)

        # Auto (Asociado a Nafta)
        auto = Device.objects.create(
            name="Flota Gol Trend",
            imei="987654321098765",
            device_type="car",
            company=empresa,
            fuel_type=nafta,
            is_online=False,
            last_update=timezone.now() - timedelta(hours=2)
        )
        auto.allowed_users.add(alejo_user)

        self.stdout.write(self.style.SUCCESS(f"Dispositivos creados: {camion.name} y {auto.name}"))

        # 6. GENERAR TELEMETRÍA (Simular viaje en La Plata)
        # Centro de La Plata aprox: -34.9214, -57.9545
        lat_base = -34.9214
        lon_base = -57.9545
        
        # Generar 50 puntos para el camión (últimas 2 horas)
        now = timezone.now()
        
        self.stdout.write("Generando ruta simulada...")
        for i in range(50):
            # Vamos retrocediendo en el tiempo
            timestamp = now - timedelta(minutes=i*2)
            
            # Simulamos movimiento (pequeña variación en lat/lon)
            lat = lat_base + (i * 0.01) 
            lon = lon_base + (random.uniform(-0.01, 0.01))
            
            speed = random.randint(20, 80) if i < 40 else 0 # Los últimos 10 puntos parado
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

        # 7. GENERAR REPORTE DIARIO (Para probar costos)
        DailyReport.objects.create(
            device=camion,
            date=now.date(),
            distance_km=120.5,
            max_speed=85.0,
            avg_speed=60.0,
            total_fuel_liters=40.0,
            idle_fuel_liters=5.0, # 5 litros desperdiciados
            # Calculamos costo: 5 litros * 1150.50
            wasted_cost=5.0 * float(diesel.price_per_liter)
        )

        self.stdout.write(self.style.SUCCESS('--- CARGA COMPLETA EXITOSA ---'))
        self.stdout.write(self.style.SUCCESS('Usuarios disponibles:'))
        self.stdout.write('1. alejo / alejo123')
        self.stdout.write('2. admin_test / admin123')