import time
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from tracking.models import Device, Telemetry
import os
from dotenv import load_dotenv 
load_dotenv() 
FLESPI_TOKEN = os.getenv('FLESPI_TOKEN')

class Command(BaseCommand):
    help = 'Worker: Sincroniza datos de Flespi a la BD local cada 10s'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("--- INICIANDO WORKER DE SINCRONIZACIÓN ---"))
        self.stdout.write(self.style.WARNING("Presiona CTRL+C para detenerlo"))
        
       
        headers = {'Authorization': f'FlespiToken {FLESPI_TOKEN}'}

        while True:
            try:
               
                devices = Device.objects.all() 
                
                for device in devices:
                    # 2. Consultamos la API de Flespi para este dispositivo
                    # Pedimos el último mensaje de telemetría
                    url = f'https://flespi.io/gw/devices/{device.imei}/messages?limit=1&reverse=true'
                    
                    try:
                        response = requests.get(url, headers=headers, timeout=5)
                        
                        if response.status_code == 200:
                            data = response.json()
                            if 'result' in data and len(data['result']) > 0:
                                item = data['result'][0]
                                
                                # El timestamp de Flespi viene en formato Unix (float/int)
                                timestamp_flespi = item.get('timestamp')
                                
                                # Convertimos a formato fecha de Django
                                dt_object = timezone.datetime.fromtimestamp(timestamp_flespi, tz=timezone.utc)
                                
                                # 3. VALIDACIÓN CRÍTICA: ¿Ya tenemos este dato?
                               
                                last_telemetry = Telemetry.objects.filter(device=device).order_by('-timestamp').first()
                                
                                if not last_telemetry or last_telemetry.timestamp != dt_object:
                                    
                                    
                                    Telemetry.objects.create(
                                        device=device,
                                        timestamp=dt_object,
                                        latitude=item.get('position.latitude'),
                                        longitude=item.get('position.longitude'),
                                        speed=item.get('position.speed', 0),
                                        ignition=item.get('engine.ignition.status', False),
                                        odometer=item.get('vehicle.mileage', 0),
                                        fuel_level=item.get('can.fuel.level', 0),
                                        battery_voltage=item.get('battery.voltage', 0)
                                    )
                                    
                                    # Actualizamos el dispositivo también
                                    device.last_update = dt_object
                                    device.is_online = True 
                                    device.save()
                                    
                                    self.stdout.write(f"[{timezone.now().time()}] {device.name}: Nuevo dato guardado.")
                                else:
                                    
                                    pass
                            else:
                                
                                pass
                        elif response.status_code == 403:
                            self.stdout.write(self.style.ERROR(f"Error 403 en {device.name}: IMEI incorrecto o Token inválido"))

                    except requests.exceptions.RequestException:
                        self.stdout.write(self.style.ERROR(f"Error de conexión al consultar {device.name}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error general en el worker: {e}"))

            
            time.sleep(5)