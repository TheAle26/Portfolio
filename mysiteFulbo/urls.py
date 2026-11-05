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
from changomas import tracker as supermarket_tracker, personal as supermarket_personal
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from portal import views as portal_views # Importamos la vista del portal
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('AppFulbo/', include('AppFulbo.urls')),
    path('tracking/', include('tracking.urls')),
    path('supermarket-tracker/', include('changomas.urls')),
    path('changomas/', supermarket_tracker.legacy_redirect),
    path('changomas/<path:suffix>', supermarket_tracker.legacy_redirect),
    path('api/v2/supermarkets/products/', supermarket_tracker.catalog_api),
    path('api/v2/supermarkets/quote/', supermarket_tracker.quote_api),
    path('api/v2/supermarkets/me/cart/', supermarket_personal.cart_api),
    path('api/v2/supermarkets/me/cart/items/<str:ean>/', supermarket_personal.cart_item_api),
    path('api/v2/supermarkets/me/cart/import/', supermarket_personal.cart_import_api),
    path('api/v2/supermarkets/me/subscriptions/', supermarket_personal.subscriptions_api),
    path('api/v1/supermarkets/', include('changomas.api_urls')),
    #el portal
    path('', portal_views.index, name='home'),
    path('i18n/', include('django.conf.urls.i18n')),
    
    path("FarmaGo/accounts/", include("apps.accounts.urls")),
    path("FarmaGo/orders/", include("apps.orders.urls")),
    path("FarmaGo", TemplateView.as_view(template_name="accounts/home.html"), name="FarmaGohome"),

]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
