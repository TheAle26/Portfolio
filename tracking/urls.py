from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # --- PUBLIC ---
    path('', views.landing_page, name='tracking_home'),

    # --- DASHBOARD (Pantalla Dividida) ---
    path('dashboard/', views.device_map_list, name='tracking_dashboard'),

    # --- INVENTORY (Tabla de Datos) ---
    path('inventory/', views.device_inventory, name='tracking_inventory'),
    
    # --- MAPA INDIVIDUAL (Pantalla Completa) ---
    path('map/<int:device_id>/', views.live_map, name='tracking_device_map'),
    
    path('api/telemetry/<int:device_id>/', views.get_device_telemetry, name='api_telemetry'),
    
    path('api/telemetry/all/', views.get_all_devices_telemetry, name='api_telemetry_all'),
    
    
    # --- AUTHENTICATION ---
    path('login/', auth_views.LoginView.as_view(
        template_name='tracking/auth/login.html',
        # Al loguearse, vamos al Dashboard (mapa general)
        next_page='tracking_dashboard' 
    ), name='tracking_login'),

    path('logout/', auth_views.LogoutView.as_view(
        next_page='tracking_home'
    ), name='tracking_logout'),

    # --- PASSWORD RESET WORKFLOW ---
    path('reset_password/', 
         auth_views.PasswordResetView.as_view(
             template_name="tracking/auth/password_reset_form.html",
             success_url=reverse_lazy('tracking_password_reset_done'),
             email_template_name="tracking/auth/password_reset_email.html"
         ), name='tracking_password_reset'),

    path('reset_password_sent/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name="tracking/auth/password_reset_done.html"
         ), name='tracking_password_reset_done'),

    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name="tracking/auth/password_reset_confirm.html",
             success_url=reverse_lazy('tracking_password_reset_complete')
         ), name='tracking_password_reset_confirm'),

    path('reset_password_complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name="tracking/auth/password_reset_complete.html"
         ), name='tracking_password_reset_complete'),
]