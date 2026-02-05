from django.urls import path, reverse_lazy 
from django.contrib.auth import views as auth_views 
from . import views

urlpatterns = [
    path('', views.landing_page, name='tracking_home'),
    path('mapa/', views.mapa_en_vivo, name='tracking_map'),
    path('mapa/<int:device_id>/', views.mapa_en_vivo, name='tracking_device'),
    
    path('login/', auth_views.LoginView.as_view(
        template_name='tracking/registro/login.html',
        next_page='tracking_home'
    ), name='tracking_login'),

    path('logout/', auth_views.LogoutView.as_view(next_page='tracking_home'), name='tracking_logout'),

    # --- PASSWORD RESET CORREGIDO ---

    # 1. Pide el mail
    path('reset_password/', 
         auth_views.PasswordResetView.as_view(
             template_name="tracking/registro/password_reset_form.html",
             # AVISO: Django por defecto busca 'password_reset_done', hay que forzar el nuestro:
             success_url=reverse_lazy('tracking_password_reset_done'),
             # IMPORTANTE: También hay que cambiar el template del email, o el link adentro va a fallar
             email_template_name="tracking/registro/password_reset_email.html"
         ), 
         name='tracking_password_reset'),


    path('reset_password_sent/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name="tracking/registro/password_reset_done.html"
         ), 
         name='tracking_password_reset_done'),

    # 3. Link para poner nueva clave
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name="tracking/registro/password_reset_confirm.html",

             success_url=reverse_lazy('tracking_password_reset_complete')
         ), 
         name='tracking_password_reset_confirm'),

    # 4. Mensaje "Clave cambiada"
    path('reset_password_complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name="tracking/registro/password_reset_complete.html"
         ), 
         name='tracking_password_reset_complete'),
]