"""
NeverQ – Corporate Cafeteria & Food Ordering System
Django 4.2 | SQLite | Bootstrap 5 | Blue/Red Theme
"""

import os
from pathlib import Path

from decouple import AutoConfig

_DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = Path(os.environ.get('NEVERQ_BASE_DIR', _DEFAULT_BASE_DIR))
config = AutoConfig(search_path=str(BASE_DIR))

DEBUG = config('DEBUG', default=False, cast=bool)
# SECRET_KEY must be set in .env explicitly — no fallback default.
# A missing key raises ImproperlyConfigured rather than silently
# invalidating all sessions and CSRF tokens on every process restart.
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost,testserver', cast=lambda v: [s.strip() for s in v.split(',')])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    # Third party
    'crispy_forms',
    'crispy_bootstrap5',
    'widget_tweaks',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    # Project apps
    'apps.core',
    'apps.accounts',
    'apps.menu',
    'apps.orders',
    'apps.pos',
    'apps.reviews',
    'apps.api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.MenuAccessMiddleware',
]

ROOT_URLCONF = 'neverq.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'neverq.wsgi.application'

DB_ENGINE = config('DB_ENGINE', default='postgresql').strip().lower()
if DB_ENGINE in {'sqlite', 'sqlite3'}:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / config('SQLITE_NAME', default='db.sqlite3'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='neverq_db'),
            'USER': config('DB_USER', default='neverq_user'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='127.0.0.1'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }

AUTH_USER_MODEL = 'accounts.StaffUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Password reset
PASSWORD_RESET_TIMEOUT = 259200  # 3 days in seconds

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# Session
SESSION_COOKIE_AGE = 86400 * 365 * 10  # 10 years
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ── Cache ─────────────────────────────────────────────────────────────────
# Required for: email verification tokens (48-hr TTL) and payment gateway
# snapshots (6-hr TTL).  With the default LocMemCache these values are
# per-process and invisible to other gunicorn workers, which breaks both
# email verification links and webhook-based order creation in production.
#
# Set REDIS_URL in .env to enable Redis.  Local single-worker dev can leave
# REDIS_URL blank and the LocMemCache fallback is used instead.
_redis_url = config('REDIS_URL', default='')
if _redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': _redis_url,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
        }
    }
else:
    # Fallback: in-memory cache suitable for local single-worker development ONLY.
    # Not suitable for production (tokens invisible across gunicorn workers).
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'neverq-default',
        }
    }

LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/auth/login/'

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Must be False — JS needs to read this for AJAX CSRF protection
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default='')
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default='')
GOOGLE_APP_ALLOWED_CLIENT_IDS = [
    s.strip()
    for s in config('GOOGLE_APP_ALLOWED_CLIENT_IDS', default='', cast=str).split(',')
    if s.strip()
]
GOOGLE_APP_AUTO_CREATE_CUSTOMER = config('GOOGLE_APP_AUTO_CREATE_CUSTOMER', default=True, cast=bool)
GOOGLE_APP_DEFAULT_COMPANY_ID = config('GOOGLE_APP_DEFAULT_COMPANY_ID', default=0, cast=int) or None
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

PHONEPE_MERCHANT_ID = config('PHONEPE_MERCHANT_ID', default='')
PHONEPE_SALT_KEY    = config('PHONEPE_SALT_KEY', default='')
PHONEPE_SALT_INDEX  = config('PHONEPE_SALT_INDEX', default='1')
PHONEPE_MODE        = config('PHONEPE_MODE', default='test')

RAZORPAY_KEY_ID     = config('RAZORPAY_KEY_ID', default='')
RAZORPAY_KEY_SECRET = config('RAZORPAY_KEY_SECRET', default='')
# Webhook secret — set in the Razorpay Dashboard under Settings → Webhooks.
# This is a SEPARATE value from RAZORPAY_KEY_SECRET.
# Without it, the /orders/razorpay/webhook/ endpoint will refuse all deliveries.
RAZORPAY_WEBHOOK_SECRET = config('RAZORPAY_WEBHOOK_SECRET', default='')

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=(EMAIL_HOST_USER or 'noreplay@neverno.in'))
SERVER_EMAIL = config('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
CONTACT_FORM_RECIPIENTS = [
    s.strip()
    for s in config('CONTACT_FORM_RECIPIENTS', default='pritam@neverno.in,niladri.roy@neverno.in', cast=str).split(',')
    if s.strip()
]

# Django 4+ requires CSRF_TRUSTED_ORIGINS when the app is served behind a
# reverse proxy or over HTTPS (e.g. gunicorn + nginx).  Leave blank in local dev.
# Production example: CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
CSRF_TRUSTED_ORIGINS = [
    s.strip()
    for s in config('CSRF_TRUSTED_ORIGINS', default='', cast=str).split(',')
    if s.strip()
]

# App settings
NEVERQ = {
    'APP_NAME': 'NeverQ',
    'TAGLINE': 'Corporate Cafeteria & Food Ordering',
    'VERSION': '1.0.0',
    'SUPPORT_EMAIL': 'support@neverq.in',
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': config('DJANGO_LOG_LEVEL', default='WARNING'),
            'propagate': False,
        },
    },
}

# ── REST Framework ─────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.api.authentication.NeverQJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/minute',
        'user': '300/minute',
    },
}

# ── SimpleJWT ──────────────────────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=12),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ── CORS ───────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    s.strip()
    for s in config('CORS_ALLOWED_ORIGINS', default='', cast=str).split(',')
    if s.strip()
]
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=False, cast=bool)
CORS_URLS_REGEX = r'^/api/.*$'

# ── Firebase ───────────────────────────────────────────────────────────────────
FIREBASE_CREDENTIALS_PATH = config('FIREBASE_CREDENTIALS_PATH', default='')
