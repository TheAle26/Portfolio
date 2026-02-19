# tracking/management/commands/simular_viaje.py
import time
import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from tracking.models import Device, Telemetry

class Command(BaseCommand):
    help = 'Simula un viaje en tiempo real para un dispositivo específico'

    def add_arguments(self, parser):
        # Permitimos pasar el IMEI como argumento
        parser.add_argument('imei', type=str, help='IMEI del dispositivo a mover')

    def handle(self, *args, **kwargs):
        device_imei = kwargs['imei']
        
        try:
            device = Device.objects.get(imei=device_imei)
        except Device.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"No existe el dispositivo con IMEI {device_imei}"))
            return

        self.stdout.write(self.style.SUCCESS(f"--- INICIANDO SIMULACIÓN PARA: {device.name} (IMEI: {device_imei}) ---"))
        self.stdout.write("Presiona CTRL+C para detener.")

        # Coordenadas iniciales (Plaza Moreno, La Plata)
        lat = -40.9214 + random.uniform(-5, 5) 
        lon = -67.9545 + random.uniform(-5, 5) 
        
        # Valores iniciales
        odometer = 150000
        fuel = 95.0
        
        while True:
            # 1. Simular Movimiento (Avanza un poco al Noroeste)
            # Variación aleatoria para que no sea una línea recta perfecta
            lat += 0.0005 + random.uniform(-0.0001, 0.0001) 
            lon -= 0.0005 + random.uniform(-0.0001, 0.0001)
            
            # 2. Simular Datos de Sensores
            speed = random.randint(40, 80)
            odometer += 0.5 # Sumar medio km
            fuel -= 0.1     # Gastar combustible
            battery = 24.0 + random.uniform(-0.5, 0.5) # Fluctuación de voltaje
            
            # 3. Crear registro en Base de Datos
            now = timezone.now()
            
            Telemetry.objects.create(
                device=device,
                timestamp=now,
                latitude=lat,
                longitude=lon,
                speed=speed,
                ignition=True, # Motor encendido
                odometer=odometer,
                fuel_level=fuel,
                battery_voltage=round(battery, 2)
            )

            # 4. Actualizar el dispositivo (importante para que aparezca ONLINE)
            device.last_update = now
            device.is_online = True
            device.save()

            self.stdout.write(f"[{now.strftime('%H:%M:%S')}] {device.name} se movió a {lat:.4f}, {lon:.4f} - {speed}km/h")

            # 5. Esperar 5 segundos antes del siguiente punto
            # (El mapa se actualiza cada 10s, así que generamos datos más rápido que el mapa)
            time.sleep(10)