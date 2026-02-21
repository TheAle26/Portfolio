import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _ 
from .models import Device , Telemetry, DailyReport
from django.http import JsonResponse 
from dotenv import load_dotenv 

load_dotenv() 



def obtain_users_devices(user):
    """
    Helper function to get devices assigned to a user.
    Uses select_related for performance optimization.
    """
    return user.assigned_devices.all().select_related('company', 'fuel_type')


@login_required(login_url='tracking_login')
def data_dashboard(request):
    """
    View para mostrar estadisticas
    """
    devices = obtain_users_devices(request.user).order_by('imei')
    reports = DailyReport.objects.filter(device__in=devices).order_by('imei', '-date')
    return render(request, 'tracking/device_map_list.html', {'devices': devices, 'reports': reports})


def landing_page(request):
    return render(request, 'tracking/landing.html')


@login_required(login_url='tracking_login')
def device_inventory(request):
    devices = request.user.assigned_devices.all().prefetch_related('telemetries')
    
    return render(request, 'tracking/device_inventory.html', {
        'devices': devices
    })


@login_required(login_url='tracking_login')
def device_map_list(request):
    """
    Shows the DASHBOARD: Split screen (Map + Sidebar List).
    """
    devices = obtain_users_devices(request.user)
    return render(request, 'tracking/device_map_list.html', {'devices': devices})

@login_required(login_url='tracking_login')
def live_map(request, device_id=None):
    # 1. Obtener dispositivo
    device = obtain_users_devices(request.user).filter(id=device_id).first()
    
    if not device:
        messages.error(request, _("Device not found."))
        return redirect('tracking_dashboard')

    # 2. Obtener EL ÚLTIMO dato de NUESTRA base de datos
    last_telemetry = Telemetry.objects.filter(device=device).order_by('-timestamp').first()

    context = {
        'device_name': device.name,
        # Valores por defecto (La Plata)
        'lat': -34.9214, 
        'lon': -57.9545,
        'last_update': None,
        'speed': 0,
        'ignition': False,
        'odometer': 0,
        'fuel_level': 0,
        'battery_voltage': 0,
        'error': None
    }

    if last_telemetry:
        # 3. Rellenar contexto con datos locales
        context['lat'] = last_telemetry.latitude
        context['lon'] = last_telemetry.longitude
        context['last_update'] = last_telemetry.timestamp
        context['speed'] = last_telemetry.speed
        context['ignition'] = last_telemetry.ignition
        context['odometer'] = last_telemetry.odometer
        context['fuel_level'] = last_telemetry.fuel_level
        context['battery_voltage'] = last_telemetry.battery_voltage
    else:
        context['error'] = _("No historical data available yet.")
        
    context['device_id'] = device.id
    return render(request, 'tracking/map.html', context)




@login_required(login_url='tracking_login')
def get_device_telemetry(request, device_id):
    """
    API endpoint que devuelve JSON para actualizar el mapa vía AJAX.
    """
    try:
        device = obtain_users_devices(request.user).filter(id=device_id).first()
        if not device:
            return JsonResponse({'success': False, 'error': 'Device not found'}, status=404)

        last = Telemetry.objects.filter(device=device).order_by('-timestamp').first()

        if last:
            return JsonResponse({
                'success': True,
                'device_id': device.id,         
                'device_name': device.name,
                'lat': last.latitude,
                'lon': last.longitude,
                'speed': last.speed,
                'ignition': last.ignition,
                'odometer': last.odometer,
                'fuel_level': last.fuel_level,
                'battery_voltage': last.battery_voltage,
                'last_update': last.timestamp.strftime('%H:%M:%S'),
            })
        else:
            return JsonResponse({'success': False, 'error': 'No data'}, status=200)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    
@login_required(login_url='tracking_login')
def get_all_devices_telemetry(request):
   
   
    devices = obtain_users_devices(request.user)
    data = []
    for device in devices:
        last = Telemetry.objects.filter(device=device).order_by('-timestamp').first()
        if last:
            data.append({
                'device_id': device.id,
                'device_name': device.name,
                'lat': last.latitude,
                'lon': last.longitude,
                'ignition': last.ignition,
                'fuel_level': last.fuel_level,
            })
            
    return JsonResponse({'devices': data})