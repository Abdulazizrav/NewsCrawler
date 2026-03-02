import os
from pathlib import Path

from django.conf.global_settings import AUTH_USER_MODEL

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-rl5z1=-d%sz5q&&!crw!0832e#n@5753h()j!nw71tk(5y9z1y'

DEBUG = False

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps',
    'django_extensions'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'mysql.connector.django',
        'NAME': os.environ.get('MYSQL_DATABASE', 'railway'),
        'USER': os.environ.get('MYSQL_USER', 'root'),
        'PASSWORD': os.environ.get('MYSQL_PASSWORD', 'NQjZagNZXylSBEdkfNRBBJoWABTfPDrx'),
        'HOST': os.environ.get('MYSQL_HOST', 'shinkansen.proxy.rlwy.net'),
        'PORT': os.environ.get('MYSQL_PORT', '32910')
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Tashkent'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
LOGIN_URL = '/login/'

CORS_ALLOW_CREDENTIALS = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = [
    "https://crawlernews-production.up.railway.app",
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
