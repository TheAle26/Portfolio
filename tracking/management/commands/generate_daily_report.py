from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Max, Min, Avg
from tracking.models import Device, Telemetry, DailyReport
from datetime import timedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Process raw telemetry data, catch up on missing days, and generate Daily Reports'

    def handle(self, *args, **kwargs):
        hoy = timezone.now().date()
        self.stdout.write(self.style.WARNING(f"--- Iniciando motor de reportes diarios (Hoy: {hoy}) ---"))

        devices = Device.objects.all()

        for device in devices:
            # 1. LÓGICA CATCH-UP: ¿Desde qué día tenemos que calcular?
            ultimo_reporte = DailyReport.objects.filter(device=device).order_by('-date').first()

            if ultimo_reporte:
                # Si ya tiene reportes, arrancamos desde el día siguiente al último guardado
                dia_a_procesar = ultimo_reporte.date + timedelta(days=1)
            else:
                # Si es un dispositivo nuevo sin reportes, procesamos solo el día de ayer
                dia_a_procesar = hoy - timedelta(days=1)

            # Si ya estamos al día, lo saltamos
            if dia_a_procesar >= hoy:
                self.stdout.write(f"[{device.name}] Al día. No hay reportes pendientes.")
                continue

            # 2. BUCLE PROCESADOR: Calculamos todos los días faltantes hasta hoy
            while dia_a_procesar < hoy:
                self.stdout.write(f"Procesando {device.name} para la fecha: {dia_a_procesar}...")

                qs = Telemetry.objects.filter(
                    device=device,
                    timestamp__date=dia_a_procesar
                ).order_by('timestamp')

                # Si el vehículo estuvo apagado/sin señal ese día, avanzamos al siguiente
                if not qs.exists():
                    self.stdout.write(f"  -> Sin telemetría. Saltando.")
                    dia_a_procesar += timedelta(days=1)
                    continue

                start_point = qs.first()
                end_point = qs.last()

                # --- A. CÁLCULO DE DISTANCIA ---
                distance_km = 0.0
                if end_point.odometer >= start_point.odometer:
                    # Basado en tu simular_viaje.py, el odómetro ya está en KM
                    distance_km = end_point.odometer - start_point.odometer

                # --- B. CÁLCULO DE COMBUSTIBLE ---
                fuel_total_liters = 0.0
                # Primero intentamos con los campos acumulativos de Flespi (A prueba de fallos)
                val_end_fuel = getattr(end_point, 'total_fuel_consumed', None)
                val_start_fuel = getattr(start_point, 'total_fuel_consumed', None)

                if val_end_fuel is not None and val_start_fuel is not None:
                    if val_end_fuel >= val_start_fuel:
                        fuel_total_liters = val_end_fuel - val_start_fuel
                else:
                    # Si no existe Flespi, lo calculamos por diferencia de nivel de tanque (para tu simulador)
                    if start_point.fuel_level and end_point.fuel_level:
                        if start_point.fuel_level >= end_point.fuel_level:
                            fuel_total_liters = start_point.fuel_level - end_point.fuel_level

                # --- C. COMBUSTIBLE DESPERDICIADO (IDLE) ---
                fuel_idle_liters = 0.0
                val_end_idle = getattr(end_point, 'total_idle_fuel', None)
                val_start_idle = getattr(start_point, 'total_idle_fuel', None)

                if val_end_idle is not None and val_start_idle is not None:
                    if val_end_idle >= val_start_idle:
                        fuel_idle_liters = val_end_idle - val_start_idle

                # --- D. HORAS DE MOTOR ---
                engine_hours_delta = timedelta(0)
                val_end_hours = getattr(end_point, 'total_engine_hours', None)
                val_start_hours = getattr(start_point, 'total_engine_hours', None)
                
                if val_end_hours is not None and val_start_hours is not None:
                     hours_diff = val_end_hours - val_start_hours
                     engine_hours_delta = timedelta(hours=hours_diff)

                # --- E. ESTADÍSTICAS DE VELOCIDAD ---
                stats = qs.aggregate(
                    max_speed=Max('speed'),
                    avg_speed=Avg('speed')
                )

                # --- F. CÁLCULO DE COSTOS REALES ---
                # Buscamos el precio del combustible asignado al vehículo
                precio_litro = Decimal('0.00')
                if device.fuel_type:
                    precio_litro = device.fuel_type.price_per_liter
                
                # Calculamos la plata tirada a la basura por dejar el motor regulando
                wasted_cost = Decimal(str(fuel_idle_liters)) * precio_litro

                # 3. GUARDAMOS EL REPORTE
                report, created = DailyReport.objects.update_or_create(
                    device=device,
                    date=dia_a_procesar,
                    defaults={
                        'distance_km': round(distance_km, 2),
                        'total_fuel_liters': round(fuel_total_liters, 2),
                        'idle_fuel_liters': round(fuel_idle_liters, 2),
                        'max_speed': stats['max_speed'] or 0,
                        'avg_speed': stats['avg_speed'] or 0,
                        'engine_hours': engine_hours_delta,
                        'wasted_cost': round(wasted_cost, 2)
                    }
                )

                action = "Creado" if created else "Actualizado"
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ [{action}]: {distance_km:.1f}km / {fuel_total_liters:.1f}L usados / ${wasted_cost:.2f} perdidos"
                ))

                # Avanzamos al siguiente día en el bucle
                dia_a_procesar += timedelta(days=1)
                
        self.stdout.write(self.style.WARNING("--- Proceso finalizado ---"))