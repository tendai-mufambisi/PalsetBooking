
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
BASE_URL = os.getenv("BASE_URL", "https://booking.easytransit.co.zw")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-me-in-production")

#DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
# Read DEBUG from environment; defaults to True for local development
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = ["*"]

# CSRF trusted origins: supply a comma-separated list of origins (including scheme)
# e.g. DJANGO_CSRF_TRUSTED_ORIGINS=https://abcd1234.ngrok.io,https://example.com
csrf_origins = os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '')
if csrf_origins:
    CSRF_TRUSTED_ORIGINS = [s.strip() for s in csrf_origins.split(',') if s.strip()]
else:
    CSRF_TRUSTED_ORIGINS = []

# When running behind a proxy (ngrok etc) it's useful to honour the X-Forwarded-Proto header
# so Django knows requests were originally HTTPS. Only enable if your proxy sets this header.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # third party
    "rest_framework",

    # local
    "rides",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise should be directly after SecurityMiddleware so it can serve static files early
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rides_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "rides.dashboard_views.dashboard_context_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "rides_project.wsgi.application"

# Database

# Use local SQLite for development by default. To use the remote MySQL (e.g. on PythonAnywhere),
# set USE_REMOTE_DB=True and provide DB_NAME, DB_USER, DB_PASSWORD, DB_HOST and optionally DB_PORT.
if os.getenv("USE_REMOTE_DB", "False") == "True":
    DATABASES = {
        "default": {
            "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.mysql"),
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "3306"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Include top-level project `static/` directory so collectstatic and static file finders see files
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# Email
# In development prefer the console backend to avoid real SMTP/TLS issues.
if DEBUG:
    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
else:
    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")

# Use custom backend that bypasses SSL verification for local testing
if DEBUG and os.getenv("IGNORE_EMAIL_SSL_VERIFICATION", "False") == "True":
    EMAIL_BACKEND = "rides.email_backend.NoSSLVerificationEmailBackend"

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "EasyTransit <lzambwi@gmail.com>")


# Google Maps
# New split keys: use a client key for browser (Maps JS + Places) and a server key for
# server-to-server calls (Distance Matrix). For backwards compatibility the old
# GOOGLE_MAPS_API_KEY env var is still accepted if either new var is not set.
GOOGLE_MAPS_CLIENT_KEY = os.getenv("GOOGLE_MAPS_CLIENT_KEY", "")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", GOOGLE_MAPS_CLIENT_KEY)

# Cache timeout for distance results (seconds)
GOOGLE_DISTANCE_CACHE_TIMEOUT = int(os.getenv("GOOGLE_DISTANCE_CACHE_TIMEOUT", str(6 * 3600)))

PAYNOW_INTEGRATION_ID = os.getenv("PAYNOW_INTEGRATION_ID", "")
PAYNOW_INTEGRATION_KEY = os.getenv("PAYNOW_INTEGRATION_KEY", "")


PAYNOW_RETURN_URL = os.getenv("PAYNOW_RETURN_URL", f"{BASE_URL}/paynow/return/")
PAYNOW_RESULT_URL = os.getenv("PAYNOW_RESULT_URL", f"{BASE_URL}/paynow/result/")
PAYNOW_MERCHANT_EMAIL = os.getenv("PAYNOW_MERCHANT_EMAIL", "")
# Set to False to disable TLS certificate verification for Paynow (use only for local testing)
PAYNOW_VERIFY_SSL = os.getenv("PAYNOW_VERIFY_SSL", "True") == "True"
# Taxi owner contact (defaults to easytransit from user input)
TAXI_OWNER_EMAIL = os.getenv("TAXI_OWNER_EMAIL", "enquiries@easytransit.co.zw")
TAXI_OWNER_PHONE = os.getenv("TAXI_OWNER_PHONE", "+263789423154")

# Use JSONField default for Django < 3.1 alternative
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Auth redirects for custom dashboard
LOGIN_URL = '/dashboard/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/dashboard/login/'
PASSWORD_RESET_TIMEOUT = 86400  # 24 hours

# Logging Configuration for Debugging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'debug.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'rides': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'rides.services': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'rides.services.paynow': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

