# tracking/views.py
import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Dispositivo
import tracking.accounts_views

FLESPI_TOKEN = 'exQOwyhjfgtXiZV5sBu3WCdhpm0A1HWdLfCGy1dLRBT6mle1lv5roOMvSAlWgbnL'

 
def landing_page(request):
    return render(request, 'tracking/landing.html')

@login_required(login_url='/tracking/registro/login.hmtl')
def mapa_en_vivo(request,device_id=None): # <--- Agregamos el parámetro opcional
    # 1. Traemos TODOS los dispositivos permitidos para este usuario
    dispositivo = request.user.dispositivos_asignados.filter(id=device_id).first()
    
    if not dispositivo:
        return render(request, 'tracking/map.html', {
            'mensaje': 'Dispositivo no encontrado o no tienes permiso para verlo.'
        })
        

    url = f'https://flespi.io/gw/devices/{dispositivo.imei}/telemetry/position'
    headers = {'Authorization': f'FlespiToken {FLESPI_TOKEN}'}
    context = {
        'device_name': dispositivo.nombre,
        'lat': -34.9214, # Default: La Plata
        'lon': -57.9545,
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
        context['error'] = f"Error de conexión: {str(e)}"
        
    return render(request, 'tracking/map.html', context)

