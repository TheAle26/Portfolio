
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views


urlpatterns = [
    path("panel/", views.panel_principal, name="panel_redireccion"),
    path("login/", views.login_view, name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("registro/", views.registro_selector, name="registro_selector"),
    path("registro/cliente/", views.registro_cliente, name="registro_cliente"),
    path("registro/farmacia/", views.registro_farmacia, name="registro_farmacia"),
    path("registro/repartidor/", views.registro_repartidor, name="registro_repartidor"),
    path("registro/terminos_y_condiciones", views.tyc, name="tyc"),
    
    
]
