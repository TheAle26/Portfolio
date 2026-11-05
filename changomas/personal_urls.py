from django.contrib.auth import views as auth_views
from django.urls import path

from . import personal

urlpatterns = [
    path('cuenta/registro/', personal.register, name='account_register'),
    path('cuenta/ingresar/', personal.login_view, name='account_login'),
    path('cuenta/salir/', auth_views.LogoutView.as_view(next_page='/supermarket-tracker/'), name='account_logout'),
    path('cuenta/configuracion/', personal.preferences, name='account_settings'),
    path('cuenta/seguimientos/', personal.subscriptions_page, name='account_watchlist'),
    path('cuenta/seguimientos/agregar/', personal.subscriptions_page, name='account_subscription_add'),
    path('seguimientos/<int:pk>/agregar/', personal.subscription_add, name='subscription_add'),
    path('cuenta/recuperar/', personal.TrackerPasswordResetView.as_view(
        template_name='changomas/personal/password_reset_form.html',
        email_template_name='changomas/personal/password_reset_email.txt',
        subject_template_name='changomas/personal/password_reset_subject.txt',
        success_url='/supermarket-tracker/cuenta/recuperar/enviado/',
    ), name='account_password_reset'),
    path('cuenta/recuperar/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='changomas/personal/password_reset_done.html'), name='account_password_reset_done'),
    path('cuenta/restablecer/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='changomas/personal/password_reset_confirm.html',
        success_url='/supermarket-tracker/cuenta/restablecer/listo/'), name='account_password_reset_confirm'),
    path('cuenta/restablecer/listo/', auth_views.PasswordResetCompleteView.as_view(
        template_name='changomas/personal/password_reset_complete.html'), name='account_password_reset_complete'),
    path('seguimientos/', personal.subscriptions_page, name='personal_subscriptions'),
    path('preferencias/', personal.preferences, name='personal_preferences'),
    path('verificar-email/<str:token>/', personal.verify_email, name='personal_verify_email'),
    path('baja-email/<str:token>/', personal.unsubscribe, name='personal_unsubscribe'),
    path('api/me/cart/', personal.cart_api, name='personal_cart_api'),
    path('api/me/cart/items/<str:ean>/', personal.cart_item_api, name='personal_cart_item_api'),
    path('api/me/cart/import/', personal.cart_import_api, name='personal_cart_import'),
    path('api/me/subscriptions/', personal.subscriptions_api, name='personal_subscriptions_api'),
]
