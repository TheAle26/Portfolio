# tracking/views.py
import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _  # Import for translation hooks
from .models import Device

# SECURITY NOTE: In production, keep this secret!
FLESPI_TOKEN = 'exQOwyhjfgtXiZV5sBu3WCdhpm0A1HWdLfCGy1dLRBT6mle1lv5roOMvSAlWgbnL'

def landing_page(request):
    return render(request, 'tracking/landing.html')

@login_required(login_url='tracking_login') # We use the URL name, not the path
def device_list(request):
    """
    Shows the list of devices assigned to the user.
    """
    devices = request.user.assigned_devices.all()
    return render(request, 'tracking/device_map_list.html', {'devices': devices})

@login_required(login_url='tracking_login')
def live_map(request, device_id=None):
    """
    Shows the live map for a specific device.
    Fetches real-time data from Flespi API.
    """
    # 1. Get the specific device from the user's allowed list
    # We use 'first()' to avoid crashing if it doesn't exist
    device = request.user.assigned_devices.filter(id=device_id).first()
    
    if not device:
        # We wrap the string in _() so Django knows it can be translated later
        messages.error(request, _("Device not found or you don't have permission to view it."))
        return redirect('tracking_device_list') # Must match the name in urls.py

    # 2. Prepare Flespi API Request
    url = f'https://flespi.io/gw/devices/{device.imei}/telemetry/position'
    headers = {'Authorization': f'FlespiToken {FLESPI_TOKEN}'}
    
    context = {
        'device_name': device.name,
        'lat': -34.9214, # Default: La Plata
        'lon': -57.9545,
        'last_update': None,
        'error': None
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if 'result' in data and len(data['result']) > 0:
                telemetry = data['result'][0]
                
                context['lat'] = telemetry.get('position.latitude', 0)
                context['lon'] = telemetry.get('position.longitude', 0)
                context['last_update'] = telemetry.get('timestamp', 0)
        else:
            context['error'] = f"Flespi Error: {response.status_code}"
            
    except Exception as e:
        # Mark this string for translation too
        context['error'] = _("Connection error: ") + str(e)
        
    return render(request, 'tracking/map.html', context)