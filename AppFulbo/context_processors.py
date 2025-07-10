# en AppFulbo/context_processors.py
from .models import Notificacion
from django.core.cache import cache

def notificaciones_context(request):
    if request.user.is_authenticated:
        # Creamos una clave de caché única para cada usuario
        cache_key = f'notificaciones_no_leidas_{request.user.id}'
        
        # 1. Intentamos obtener el valor de la caché
        notificaciones_no_leidas = cache.get(cache_key)
        
        # 2. Si no está en la caché (es None), hacemos la consulta a la DB
        if notificaciones_no_leidas is None:
            notificaciones_no_leidas = Notificacion.objects.filter(usuario=request.user, leido=False).count()
            # 3. Guardamos el resultado en la caché por 60 segundos
            cache.set(cache_key, notificaciones_no_leidas, 60)
    else:
        notificaciones_no_leidas = 0
        
    return {
        'notificaciones_no_leidas': notificaciones_no_leidas,
    }