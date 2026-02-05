from django.urls import path ,reverse_lazy
from AppFulbo import views
from django.contrib.auth.views import LogoutView
from django.contrib.auth import views as auth_views
urlpatterns = [
    path('inicio/',views.inicio,name='AppFulbo_inicio'),
    path('login/',views.login_request,name='AppFulbo_login'),
    path('logout/', LogoutView.as_view(next_page='AppFulbo_inicio'), name='AppFulbo_logout'),
    path('register/',views.register,name='AppFulbo_register'),
    path('edit_Profile/', views.edit_profile, name='AppFulbo_edit_profile'),
    path('mi_perfil/', views.mi_perfil, name='AppFulbo_mi_perfil'),
    

    path('mis_ligas/',views.mis_ligas, name='mis_ligas'),


    path('ligas/crear/', views.crear_liga, name='crear_liga'),
    path('ligas/<int:liga_id>/', views.ver_liga, name='ver_liga'),
    path('ligas/<int:liga_id>/editar_liga', views.editar_liga, name='editar_liga'),
    # path('solicitudes/<int:solicitud_id>/asociar/', views.asociar_jugador, name='asociar_jugador'),
    path('liga/<int:liga_id>/gestionar_partidos/', views.gestionar_partidos_liga, name='gestionar_partidos_liga'),
    path('liga/<int:liga_id>/modificar_partido/<int:partido_id>/', views.modificar_partido, name='modificar_partido'),
    path('liga/<int:liga_id>/eliminar_partido/<int:partido_id>/', views.eliminar_partido, name='eliminar_partido'), 
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
    path('liga/<int:liga_id>/agregar_jugador/', views.agregar_jugador, name='agregar_jugador'), 
    path('liga/<int:liga_id>/modificar_jugador/<int:jugador_id>/', views.modificar_jugador, name='modificar_jugador'), # URL de modificación
    
    # URL para ASOCIAR un usuario a un jugador ya existente (sin usuario)
    path('liga/<int:liga_id>/asociar_jugador/<int:jugador_id>/', views.asociar_usuario_a_jugador, name='asociar_usuario_a_jugador'),

    # URL para ELIMINAR un jugador
    path('liga/<int:liga_id>/eliminar_jugador/<int:jugador_id>/', views.eliminar_jugador, name='eliminar_jugador'),
    path('liga/<int:liga_id>/jugadores/<int:jugador_id>/reactivar/', views.reactivar_jugador, name='reactivar_jugador'),
    path('notificaciones/marcar_todas_ajax/', views.marcar_todas_notificaciones_ajax, name='marcar_todas_notificaciones_ajax'),
    
    
     path('reset_password/', 
          auth_views.PasswordResetView.as_view(
               template_name="registro/password_reset_form.html",
               # Forzamos la redirección a NUESTRA url de éxito:
               success_url=reverse_lazy('AppFulbo_password_reset_done'),
               # IMPORTANTE: Usamos un template de email propio para que el link apunte bien
               email_template_name="registro/password_reset_email.html"
          ), 
          name='AppFulbo_password_reset'),

     # 2. Mensaje de "Correo enviado exitosamente"
     path('reset_password_sent/', 
          auth_views.PasswordResetDoneView.as_view(
               template_name="registro/password_reset_done.html"
          ), 
          name='AppFulbo_password_reset_done'),

     # 3. Link que le llega al usuario para poner la nueva clave
     path('reset/<uidb64>/<token>/', 
          auth_views.PasswordResetConfirmView.as_view(
               template_name="registro/password_reset_confirm.html",
               # Al terminar, ir a nuestro mensaje de éxito:
               success_url=reverse_lazy('AppFulbo_password_reset_complete')
          ), 
          name='AppFulbo_password_reset_confirm'),

     # 4. Mensaje de "Contraseña cambiada con éxito"
     path('reset_password_complete/', 
          auth_views.PasswordResetCompleteView.as_view(
               template_name="registro/password_reset_complete.html"
          ), 
          name='AppFulbo_password_reset_complete'),
     
     
     ]