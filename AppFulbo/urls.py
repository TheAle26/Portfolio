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
    
    # path('ligas/buscar_ligas/', views.buscar_ligas, name='buscar_ligas'),
    #path('ligas/unirse/<int:liga_id>/', views.solicitar_unirse, name='solicitar_unirse'),
    path('mis_ligas/',views.mis_ligas, name='mis_ligas'),


    path('ligas/crear/', views.crear_liga, name='crear_liga'),
    path('ligas/<int:liga_id>/', views.ver_liga, name='ver_liga'),
    path('ligas/<int:liga_id>/editar_liga', views.editar_liga, name='editar_liga'),
    # path('solicitudes/<int:solicitud_id>/asociar/', views.asociar_jugador, name='asociar_jugador'),

    path('mis_partidos/', views.partidos_jugados, name='mis_partidos'),
    path('ligas/<int:liga_id>/crear_partido/', views.crear_partido, name='crear_partido'),
    # path('ligas/<int:liga_id>/gestionar_solicitudes/', views.gestionar_solicitudes, name='gestionar_solicitudes'),
    path('partido/<int:partido_id>/', views.ver_partido, name='ver_partido'),
    path('puntuar_jugadores/<int:partido_id>/<int:puntuacion_pendiente_id>/', views.puntuar_jugadores_partido, name='puntuar_jugadores_partido'),
    path('ligas/<int:liga_id>/crear_equipos/', views.encontrar_equipos_mas_parejos, name='encontrar_equipos_mas_parejos'),
    path('verificar_usuario/', views.verificar_usuario_ajax, name='verificar_usuario_ajax'),
    path('liga/<int:liga_id>/gestionar_jugadores/', views.gestionar_jugadores_liga, name='gestionar_jugadores_liga'),

    # URL para AGREGAR UN NUEVO JUGADOR Y ASOCIAR UN USUARIO
    path('liga/<int:liga_id>/agregar_jugador_y_usuario/', views.agregar_jugador_y_usuario, name='agregar_jugador_y_usuario'), # Renombrado para coincidir con la vista

    # URL para CREAR JUGADOR SIN USUARIO
    path('liga/<int:liga_id>/crear_jugador_sin_usuario/', views.crear_jugador_sin_usuario, name='crear_jugador_sin_usuario'),

    # URL para MODIFICAR un jugador existente
    path('liga/<int:liga_id>/modificar_jugador/<int:jugador_id>/', views.modificar_jugador, name='modificar_jugador'),
    
    # URL para ASOCIAR un usuario a un jugador ya existente (sin usuario)
    path('liga/<int:liga_id>/asociar_jugador/<int:jugador_id>/', views.asociar_usuario_a_jugador, name='asociar_usuario_a_jugador'),

    # URL para ELIMINAR un jugador
    path('liga/<int:liga_id>/eliminar_jugador/<int:jugador_id>/', views.eliminar_jugador, name='eliminar_jugador'),
    path('liga/<int:liga_id>/jugadores/<int:jugador_id>/reactivar/', views.reactivar_jugador, name='reactivar_jugador'),
    path('notificaciones/marcar_todas_ajax/', views.marcar_todas_notificaciones_ajax, name='marcar_todas_notificaciones_ajax'),
]
