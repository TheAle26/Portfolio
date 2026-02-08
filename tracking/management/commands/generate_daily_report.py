from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Max, Min, Avg
from tracking.models import Device, Telemetry, DailyReport
from datetime import timedelta

class Command(BaseCommand):
    help = 'Process raw telemetry data from yesterday and generate Daily Reports'

    def handle(self, *args, **kwargs):
       
        yesterday = timezone.now().date() - timedelta(days=1)
        
        self.stdout.write(f"--- Generating Reports for: {yesterday} ---")

        devices = Device.objects.all()

        for device in devices:

            qs = Telemetry.objects.filter(
                device=device,
                timestamp__date=yesterday
            ).order_by('timestamp')

            # If no data, skip
            if not qs.exists():
                self.stdout.write(f"Skipping {device.name}: No telemetry found for {yesterday}.")
                continue

            start_point = qs.first()
            end_point = qs.last()

            if not start_point or not end_point:
                continue

           
           
            distance_km = 0.0
            if end_point.odometer >= start_point.odometer:
                # Assuming odometer comes in Meters from Teltonika/Flespi
                distance_km = (end_point.odometer - start_point.odometer) / 1000.0
            
            
            fuel_total_liters = 0.0
            if end_point.total_fuel_consumed and start_point.total_fuel_consumed:
                if end_point.total_fuel_consumed >= start_point.total_fuel_consumed:
                    fuel_total_liters = end_point.total_fuel_consumed - start_point.total_fuel_consumed

            # C. Idle Fuel (Wasted fuel)
            fuel_idle_liters = 0.0
            
            #hasattr(objeto, 'nombre_del_campo'):

            # Es una función de Python que devuelve True si el atributo existe y False si no. Esto es útil para evitar errores de atributo cuando no estás seguro de que un objeto tenga un campo específico.
            val_end = getattr(end_point, 'total_idle_fuel', None)
            val_start = getattr(start_point, 'total_idle_fuel', None)

            if val_end is not None and val_start is not None:
                if val_end >= val_start:
                    fuel_idle_liters = val_end - val_start

            # D. Engine Hours (Total hours ON)
            # Assuming you have 'total_engine_hours' in Telemetry
            engine_hours_delta = timedelta(0)
            if hasattr(end_point, 'total_engine_hours') and hasattr(start_point, 'total_engine_hours'):
                 hours_diff = end_point.total_engine_hours - start_point.total_engine_hours
                 engine_hours_delta = timedelta(hours=hours_diff)

            # E. Max & Avg Speed (Aggregation)
            # These are not cumulative, so we must ask the DB to calculate
            stats = qs.aggregate(
                max_speed=Max('speed'),
                avg_speed=Avg('speed')
            )

            # 5. SAVE OR UPDATE THE REPORT
            report, created = DailyReport.objects.update_or_create(
                device=device,
                date=yesterday,
                defaults={
                    'distance_km': round(distance_km, 2),
                    'total_fuel_liters': round(fuel_total_liters, 2),
                    'idle_fuel_liters': round(fuel_idle_liters, 2),
                    'max_speed': stats['max_speed'] or 0,
                    'avg_speed': stats['avg_speed'] or 0,
                    'engine_hours': engine_hours_delta,
                    
                    # Optional: Calculate cost (e.g., $1.50 per liter)
                    'wasted_cost': round(fuel_idle_liters * 1.50, 2) 
                }
            )

            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(
                f"✓ {device.name} [{action}]: {distance_km:.1f}km / {fuel_total_liters:.1f}L Used / {fuel_idle_liters:.1f}L Wasted"
            ))