import time
import random
import math
import xml.etree.ElementTree as ET
import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from tracking.models import Device, Telemetry

def calcular_distancia(lat1, lon1, lat2, lon2):
    """Calcula la distancia real en kilómetros entre dos coordenadas (Fórmula de Haversine)"""
    R = 6371.0  # Radio de la Tierra en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class Command(BaseCommand):
    help = 'Simula un viaje en tiempo real usando una ruta GPX real'

    def add_arguments(self, parser):
        parser.add_argument('imei', type=str, help='IMEI del dispositivo a mover')
        

    def handle(self, *args, **kwargs):
        device_imei = kwargs['imei']
        
        directorio_actual = os.path.dirname(os.path.abspath(__file__))
        archivo_gpx = os.path.join(directorio_actual, f"{device_imei}.gpx")
        
        try:
            device = Device.objects.get(imei=device_imei)
        except Device.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"No existe el dispositivo con IMEI {device_imei}"))
            return

        # 1. LEER EL ARCHIVO GPX
        if not os.path.exists(archivo_gpx):
            self.stdout.write(self.style.ERROR(f"No se encontró el archivo {archivo_gpx} en el directorio actual."))
            return

        # Parsea el XML (GPX)
        arbol = ET.parse(archivo_gpx)
        raiz = arbol.getroot()
        
        # El archivo GPX tiene un "namespace" que hay que declarar para buscar las etiquetas
        espacio_nombres = {'gpx': 'http://www.topografix.com/GPX/1/1'}
        puntos_ruta = []
        
        for trkpt in raiz.findall('.//gpx:trkpt', espacio_nombres):
            lat = float(trkpt.get('lat'))
            lon = float(trkpt.get('lon'))
            puntos_ruta.append((lat, lon))

        if not puntos_ruta:
            self.stdout.write(self.style.ERROR("El archivo GPX está vacío o no tiene la estructura de OSRM."))
            return

        self.stdout.write(self.style.SUCCESS(f"--- INICIANDO SIMULACIÓN PARA: {device.name} (IMEI: {device_imei}) ---"))
        self.stdout.write(f"✓ Ruta cargada con éxito: {len(puntos_ruta)} puntos GPS detectados.")
        self.stdout.write("Presiona CTRL+C para detener.")

        # Valores iniciales lógicos
        odometer = 150000.0
        fuel = 95.0
        
        # Bucle infinito: cuando llegue al final de la ruta, vuelve a empezar
        while True:
            for indice, punto in enumerate(puntos_ruta):
                lat, lon = punto
                
                # 2. CALCULAR DISTANCIA Y VELOCIDAD EXACTA
                if indice > 0:
                    lat_previa, lon_previa = puntos_ruta[indice - 1]
                    distancia_km = calcular_distancia(lat_previa, lon_previa, lat, lon)
                    odometer += distancia_km
                    
                    # Si asumimos que enviamos un reporte cada 10 segundos...
                    # Velocidad (km/h) = distancia (km) / tiempo (horas -> 10s = 10/3600 hrs)
                    speed_real = distancia_km / (10 / 3600.0)
                    speed = max(0, int(speed_real)) # Evitamos velocidades negativas
                else:
                    speed = 0  # Arranca parado
                    distancia_km = 0
                
                # 3. Simular Datos de Sensores
                # El camión gasta nafta de verdad basado en los km que recorre (aprox 12L/100km)
                fuel -= (distancia_km * 0.12)
                
                # Si se queda sin nafta en medio de la simulación, le llenamos el tanque
                if fuel <= 5: 
                    fuel = 95.0

                battery = 24.0 + random.uniform(-0.3, 0.3)
                now = timezone.now()
                
                # 4. Crear registro en Base de Datos
                Telemetry.objects.create(
                    device=device,
                    timestamp=now,
                    latitude=lat,
                    longitude=lon,
                    speed=speed,
                    ignition=True,
                    odometer=odometer,
                    fuel_level=round(fuel, 2),
                    battery_voltage=round(battery, 2)
                )

                # 5. Actualizar la última conexión del dispositivo
                device.last_update = now
                device.save()

                # Consola interactiva para que veas el progreso
                self.stdout.write(f"[{now.strftime('%H:%M:%S')}] Progreso: {indice + 1}/{len(puntos_ruta)} | Coords: {lat:.4f}, {lon:.4f} | {speed} km/h | Odo: {odometer:.2f}km | Nafta: {fuel:.1f}L")

                # Esperamos 10 segundos reales para enviar el próximo punto (como un GPS de verdad)
                time.sleep(10)
            
            self.stdout.write(self.style.WARNING("--- Ruta completada. Dando la vuelta y reiniciando viaje... ---"))