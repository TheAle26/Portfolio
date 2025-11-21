"""
Django settings for mysiteFulbo project.
OPTIMIZADO PARA PRODUCCION Y DESARROLLO
"""

from pathlib import Path
import os
import socket
from dotenv import load_dotenv 

# Carga las variables del archivo .env
load_dotenv() 

BASE_DIR = Path(__file__).resolve().parent.parent

# --- SEGURIDAD Y ENTORNO ---
hostname = socket.gethostname()

# IMPORTANTE: Pon tu SECRET_KEY en el archivo .env también por seguridad
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-clave-por-defecto-cambiar-en-prod')

if hostname == '2wz':
    # --- PRODUCCIÓN (Raspberry Pi / Servidor) ---
    DEBUG = False
    ALLOWED_HOSTS = [
        'localhost',
        '127.0.0.1',
        '192.168.0.240',
        '190.189.49.129',
        'fulboapp.zapto.org',
    ]
    
    # Configuración de Correo REAL (Gmail)
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
    
    # Rutas estáticas de producción
    STATIC_ROOT = '/var/www/Fulbo/static'
    STATICFILES_DIRS = []
    
    # Base de Datos Producción
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': '/var/www/Fulbo/db.sqlite3',
        }
    }

else:
    # --- DESARROLLO (Tu PC) ---
    DEBUG = True
    ALLOWED_HOSTS = []
    
    # Correo en CONSOLA (Para no gastar cuota de Gmail probando)
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    
    # Rutas estáticas locales
    STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
    STATICFILES_DIRS = [
        os.path.join(BASE_DIR, 'AppFulbo/static'),
    ]
    
    # Base de Datos Desarrollo
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Configuración común para ambos entornos
DEFAULT_FROM_EMAIL = 'Proyectito Fulbo <thedarckalejoxo@gmail.com>'
CSRF_TRUSTED_ORIGINS = ['https://fulboapp.zapto.org']


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'AppFulbo',
    'crispy_forms',
    'crispy_bootstrap4', # OJO: Ver nota abajo sobre Bootstrap 5
]

CRISPY_ALLOWED_TEMPLATE_PACKS = ["bootstrap4"]
CRISPY_TEMPLATE_PACK = "bootstrap4" 

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mysiteFulbo.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [], # Si tienes templates globales, agrégalos aquí
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'AppFulbo.context_processors.notificaciones_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'mysiteFulbo.wsgi.application'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# Internationalization
LANGUAGE_CODE = 'es-arg'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = '/static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

LOGIN_URL='/AppFulbo/login'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}