"""
URL configuration for mysiteFulbo project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('AppFulbo/', include('AppFulbo.urls')),
    path('password_reset/', 
         auth_views.PasswordResetView.as_view(template_name='registro/password_reset_form.html'), 
         name='password_reset'),

    # 2. Página de confirmación que avisa que el email fue enviado
    path('password_reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='registro/password_reset_done.html'), 
         name='password_reset_done'),

    # 3. El enlace que llega en el email, con un token para validar al usuario
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='registro/password_reset_confirm.html'), 
         name='password_reset_confirm'),

    # 4. Página de confirmación que avisa que la contraseña se cambió con éxito
    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='registro/password_reset_complete.html'), 
         name='password_reset_complete'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)