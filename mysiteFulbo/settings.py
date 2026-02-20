from pathlib import Path
import os
from dotenv import load_dotenv 
from django.utils.translation import gettext_lazy as _

# Carga las variables del archivo .env
load_dotenv() 

BASE_DIR = Path(__file__).resolve().parent.parent

# --- SEGURIDAD Y CREDENCIALES ---
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-clave-por-defecto-cambiar-en-prod')

# Definimos el entorno leyendo el .env (Si no existe, asume 'development')
DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development')

# --- CONFIGURACIÓN DE CORREO (COMÚN) ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = 'Alejo Vincent <thedarckalejoxo@gmail.com>'

# --- ENTORNOS ---
if DJANGO_ENV == 'production':
    # --- PRODUCCIÓN (Raspberry Pi / Servidor) ---
    DEBUG = False
    ALLOWED_HOSTS = [
        'localhost',
        '127.0.0.1',
        '192.168.0.240',
        '190.189.49.129',
        'fulboapp.zapto.org',
        'vincentalejo.myddns.me',
    ]
    CSRF_TRUSTED_ORIGINS = ['https://fulboapp.zapto.org']
    
    # Rutas estáticas de producción
    STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
    STATICFILES_DIRS = [
        os.path.join(BASE_DIR, 'AppFulbo/static'),
    ]
    
    # --- SEGURIDAD HTTPS ---
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

else:
    # --- DESARROLLO (Tu PC / Docker Local) ---
    DEBUG = True
    # Usamos '*' en desarrollo para que Docker y tu PC se comuniquen sin bloqueos
    ALLOWED_HOSTS = ['*'] 
    CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']
    
    # Rutas estáticas locales
    STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
    STATICFILES_DIRS = [
        os.path.join(BASE_DIR, 'AppFulbo/static'),
    ]


# --- ARCHIVOS ESTÁTICOS Y MULTIMEDIA ---
STATIC_URL = '/static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')


# --- BASE DE DATOS (COMÚN PARA DOCKER: POSTGRESQL) ---
# Al usar Docker, tanto en prod como en dev usaremos la misma arquitectura de DB
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'mi_proyecto_db'),
        'USER': os.environ.get('DB_USER', 'alejo'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'password_secreto'),
        'HOST': os.environ.get('DB_HOST', 'db'), # 'db' es el contenedor de Postgres
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# --- APLICACIONES ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Tus Apps
    'AppFulbo',
    'portal',
    'tracking',
    # Librerías
    'crispy_forms',
    'crispy_bootstrap4', 
    'apps.accounts',
    'apps.orders',
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
        'DIRS': [], 
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
AUTH_USER_MODEL = 'portal.User'
# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# --- INTERNACIONALIZACIÓN ---
LANGUAGES = [
    ('en', _('English')), 
    ('es', _('Spanish')), 
]
LANGUAGE_CODE = 'es-ar' # Unificado (tenías en-us y es-arg duplicados)
TIME_ZONE = 'America/Argentina/Buenos_Aires' # Ajustado a tu zona horaria real
USE_I18N = True
USE_TZ = True



LOGIN_URL = '/AppFulbo/login'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- CACHÉ ---
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}