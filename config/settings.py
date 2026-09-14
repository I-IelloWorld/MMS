import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


def env_bool(name, default=False):
    value = os.getenv(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


IS_VERCEL = env_bool("VERCEL")
DEBUG = env_bool("MMS_DEBUG", True)
SECRET_KEY = os.getenv("MMS_SECRET_KEY", "django-insecure-local-mms-change-me")
if not DEBUG and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-")):
    raise ImproperlyConfigured(
        "MMS_SECRET_KEY must be a unique random value containing at least 50 characters."
    )

ALLOWED_HOSTS = env_list("MMS_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("MMS_CSRF_TRUSTED_ORIGINS")
vercel_url = os.getenv("VERCEL_URL", "").strip()
if vercel_url:
    if vercel_url not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(vercel_url)
    vercel_origin = f"https://{vercel_url}"
    if vercel_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(vercel_origin)


# Application definition

INSTALLED_APPS = [
    # Override runserver to start the local recurrence scheduler as well.
    'apps.common.apps.CommonConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'storages',
    'apps.accounts.apps.AccountsConfig',
    'apps.facilities.apps.FacilitiesConfig',
    'apps.assets.apps.AssetsConfig',
    # Migration-only app: upgrades must still traverse the historical migrations.
    'apps.maintenance.apps.MaintenanceConfig',
    'apps.workorders.apps.WorkordersConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.data_imports.apps.DataImportsConfig',
    'apps.dashboard.apps.DashboardConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
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
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.dashboard.context_processors.workspace_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database. Vercel should use Supabase's transaction-pooler DATABASE_URL.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=0,
            conn_health_checks=True,
            ssl_require=not DEBUG,
        )
    }
    if not DATABASES["default"]["ENGINE"].endswith("postgresql") and not DEBUG:
        raise ImproperlyConfigured("DATABASE_URL must point to PostgreSQL in production.")
    if os.getenv("MMS_DATABASE_POOL_MODE", "transaction") == "transaction":
        # Supabase transaction pooling does not support session-level prepared statements.
        DATABASES["default"].setdefault("OPTIONS", {})["prepare_threshold"] = None
elif os.getenv("MMS_DB_ENGINE", "sqlite") == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("MMS_DB_NAME", "mms"),
            "USER": os.getenv("MMS_DB_USER", "mms"),
            "PASSWORD": os.getenv("MMS_DB_PASSWORD", ""),
            "HOST": os.getenv("MMS_DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("MMS_DB_PORT", "5432"),
            "CONN_MAX_AGE": 0 if IS_VERCEL else 60,
            "OPTIONS": {"sslmode": os.getenv("MMS_DB_SSLMODE", "prefer")},
        }
    }
else:
    if IS_VERCEL or not DEBUG:
        raise ImproperlyConfigured("DATABASE_URL is required; SQLite is not persistent on Vercel.")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = []

AUTHENTICATION_BACKENDS = ["apps.accounts.backends.WarehouseRoleBackend"]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'zh-hans'

LANGUAGES = [
    ('zh-hans', _('简体中文')),
    ('en', _('English')),
    ('es', _('Español')),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGE_BACKEND = os.getenv("MMS_STORAGE_BACKEND", "filesystem").lower()
if STORAGE_BACKEND == "supabase":
    storage_settings = {
        "access_key": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "bucket_name": os.getenv("AWS_STORAGE_BUCKET_NAME", ""),
        "endpoint_url": os.getenv("AWS_S3_ENDPOINT_URL", "").rstrip("/"),
        "region_name": os.getenv("AWS_S3_REGION_NAME", "us-east-1"),
    }
    missing_storage = [key for key, value in storage_settings.items() if not value]
    if missing_storage:
        raise ImproperlyConfigured(
            "Missing Supabase Storage settings: " + ", ".join(missing_storage)
        )
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                **storage_settings,
                "addressing_style": "path",
                "signature_version": "s3v4",
                "default_acl": None,
                "file_overwrite": False,
                "querystring_auth": True,
                "querystring_expire": 300,
                "location": os.getenv("MMS_STORAGE_PREFIX", "media").strip("/"),
            },
        },
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
else:
    if IS_VERCEL:
        raise ImproperlyConfigured(
            "Set MMS_STORAGE_BACKEND=supabase; Vercel's local filesystem is not persistent."
        )
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'login'

CELERY_BROKER_URL = os.getenv("MMS_REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("MMS_REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_TIMEZONE = "UTC"
MMS_LOCAL_SCHEDULER = env_bool("MMS_LOCAL_SCHEDULER", not IS_VERCEL)
MMS_SCHEDULER_INTERVAL_SECONDS = int(os.getenv("MMS_SCHEDULER_INTERVAL_SECONDS", "30"))
MMS_CRON_MAX_OCCURRENCES = int(os.getenv("MMS_CRON_MAX_OCCURRENCES", "100"))
CRON_SECRET = os.getenv("CRON_SECRET", "")
if IS_VERCEL and len(CRON_SECRET) < 16:
    raise ImproperlyConfigured(
        "CRON_SECRET must contain at least 16 characters for the Vercel scheduler endpoint."
    )
CELERY_BEAT_SCHEDULE = {
    "generate-recurring-work-orders": {
        "task": "apps.workorders.tasks.generate_recurring_work_orders_task",
        "schedule": float(MMS_SCHEDULER_INTERVAL_SECONDS),
    }
}

EMAIL_BACKEND = os.getenv("MMS_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("MMS_FROM_EMAIL", "mms@example.com")

MMS_MAX_UPLOAD_BYTES = 4 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MMS_MAX_UPLOAD_BYTES
DATA_UPLOAD_MAX_MEMORY_SIZE = MMS_MAX_UPLOAD_BYTES + 256 * 1024

# Production HTTPS and browser security. Vercel terminates TLS at its proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if IS_VERCEL else None
SECURE_SSL_REDIRECT = env_bool("MMS_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = int(os.getenv("MMS_SECURE_HSTS_SECONDS", "3600" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("MMS_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("MMS_SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
