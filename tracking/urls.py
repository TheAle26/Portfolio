# tracking/urls.py
from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # --- PUBLIC ---
    path('', views.landing_page, name='tracking_home'),

    # --- DASHBOARD & MAPS ---
    # Renamed views to match English version: 'live_map' and 'device_list'
    path('map/', views.live_map, name='tracking_map'),
    path('map/<int:device_id>/', views.live_map, name='tracking_device_map'),
    
    # Simplified URL from 'device_live_map_list/' to 'devices/'
    path('devices/', views.device_list, name='tracking_device_list'),
    
    # --- AUTHENTICATION ---
    path('login/', auth_views.LoginView.as_view(
        template_name='tracking/auth/login.html',
        # Redirect to device list after login is usually better than home
        next_page='tracking_device_list' 
    ), name='tracking_login'),

    path('logout/', auth_views.LogoutView.as_view(
        next_page='tracking_home'
    ), name='tracking_logout'),

    # --- PASSWORD RESET WORKFLOW ---

    # 1. Request password reset (Email entry)
    path('reset_password/', 
         auth_views.PasswordResetView.as_view(
             template_name="tracking/auth/password_reset_form.html",
             success_url=reverse_lazy('tracking_password_reset_done'),
             email_template_name="tracking/auth/password_reset_email.html"
         ), 
         name='tracking_password_reset'),

    # 2. Email sent confirmation
    path('reset_password_sent/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name="tracking/auth/password_reset_done.html"
         ), 
         name='tracking_password_reset_done'),

    # 3. Link to set new password (Token validation)
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name="tracking/auth/password_reset_confirm.html",
             success_url=reverse_lazy('tracking_password_reset_complete')
         ), 
         name='tracking_password_reset_confirm'),

    # 4. "Password changed" success message
    path('reset_password_complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name="tracking/auth/password_reset_complete.html"
         ), 
         name='tracking_password_reset_complete'),
]