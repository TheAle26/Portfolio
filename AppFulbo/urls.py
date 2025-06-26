from django.urls import path
from AppFulbo import views
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('inicio/',views.inicio,name='inicio'),
    path('login/',views.login_request,name='login'),
    path('logout/', LogoutView.as_view(next_page='inicio'), name='logout'),
    path('register/',views.register,name='register'),
    path('edit_Profile/', views.edit_profile, name='edit_Profile'),
    path('mi_perfil/', views.mi_perfil, name='mi_perfil'),
    
    path('ligas/buscar_ligas/', views.buscar_ligas, name='buscar_ligas'),
    #path('ligas/unirse/<int:liga_id>/', views.solicitar_unirse, name='solicitar_unirse'),
    path('mis_ligas/',views.mis_ligas, name='mis_ligas'),
    path('jugador/crear/<int:liga_id>/', views.crear_jugador, name='crear_jugador'),
    path('jugador/editar/<int:jugador_id>/', views.editar_jugador, name='editar_jugador'),

    path('ligas/crear/', views.crear_liga, name='crear_liga'),
    path('ligas/<int:liga_id>/', views.ver_liga, name='ver_liga'),
    path('ligas/<int:liga_id>/editar_liga', views.editar_liga, name='editar_liga'),
    path('solicitudes/<int:solicitud_id>/asociar/', views.asociar_jugador, name='asociar_jugador'),

    path('mis_partidos/', views.partidos_jugados, name='mis_partidos'),
    path('ligas/<int:liga_id>/crear_partido/', views.crear_partido, name='crear_partido'),
    path('ligas/<int:liga_id>/gestionar_solicitudes/', views.gestionar_solicitudes, name='gestionar_solicitudes'),
    path('partido/<int:partido_id>/', views.ver_partido, name='ver_partido'),
    path('puntuar_jugadores/<int:partido_id>/<int:puntuacion_pendiente_id>/', views.puntuar_jugadores_partido, name='puntuar_jugadores_partido'),
    path('ligas/<int:liga_id>/crear_equipos/', views.encontrar_equipos_mas_parejos, name='encontrar_equipos_mas_parejos'),


    #path('mensajes/inbox/', views.inbox, name='inbox'),
    #path('mensajes/conversacion/<int:conversacion_id>/', views.conversacion_detail, name='conversacion_detail'),
    #path('mensajes/nuevo/', views.nuevo_chat, name='nuevo_chat'),
    
    #path('mensajes/enviar_ajax/<int:conversacion_id>/', views.enviar_mensaje_ajax, name='enviar_mensaje_ajax'),
    #path('mensajes/obtener/<int:conversacion_id>/', views.obtener_mensajes, name='obtener_mensajes'),
    
    path('notificaciones/marcar_todas_ajax/', views.marcar_todas_notificaciones_ajax, name='marcar_todas_notificaciones_ajax'),
]
