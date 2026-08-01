import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY não configurada.")


DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "macro_dashboard.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "macro_dashboard.wsgi.application"
ASGI_APPLICATION = "macro_dashboard.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "macro_db"),
        "USER": os.getenv("DB_USER", "macro_user"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "db"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "TIMEOUT": env_int("MARKET_CACHE_TTL", 300),
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 240
CELERY_TASK_SOFT_TIME_LIMIT = 210
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_RESULT_EXPIRES = 3600

MARKET_REFRESH_SECONDS = env_int("MARKET_REFRESH_SECONDS", 300)
MARKET_CACHE_TTL = env_int("MARKET_CACHE_TTL", 300)
MARKET_HISTORY_DAYS = env_int("MARKET_HISTORY_DAYS", 30)
MARKET_CHART_HISTORY_HOURS = env_int("MARKET_CHART_HISTORY_HOURS", 24)
HTTP_CONNECT_TIMEOUT_SECONDS = env_int("HTTP_CONNECT_TIMEOUT_SECONDS", 5)
HTTP_READ_TIMEOUT_SECONDS = env_int("HTTP_READ_TIMEOUT_SECONDS", 15)
HTTP_TIMEOUT_SECONDS = (HTTP_CONNECT_TIMEOUT_SECONDS, HTTP_READ_TIMEOUT_SECONDS)
INVESTING_ENABLED = env_bool("INVESTING_ENABLED", True)
INVESTING_HTTP_ATTEMPTS = env_int("INVESTING_HTTP_ATTEMPTS", 2)
INVESTING_REQUEST_MIN_DELAY_SECONDS = env_float("INVESTING_REQUEST_MIN_DELAY_SECONDS", 1.2)
INVESTING_REQUEST_MAX_DELAY_SECONDS = env_float("INVESTING_REQUEST_MAX_DELAY_SECONDS", 2.4)
INVESTING_RETRY_BACKOFF_SECONDS = env_float("INVESTING_RETRY_BACKOFF_SECONDS", 2.0)
INVESTING_CIRCUIT_COOLDOWN_SECONDS = env_int("INVESTING_CIRCUIT_COOLDOWN_SECONDS", 300)
INVESTING_ADR_CACHE_SECONDS = env_int("INVESTING_ADR_CACHE_SECONDS", 600)
INVESTING_BONDS_CACHE_SECONDS = env_int("INVESTING_BONDS_CACHE_SECONDS", 1800)
INVESTING_MIN_HTML_BYTES = env_int("INVESTING_MIN_HTML_BYTES", 1000)
NEWS_ENABLED = env_bool("NEWS_ENABLED", True)
NEWS_REFRESH_SECONDS = env_int("NEWS_REFRESH_SECONDS", 300)
NEWS_RETENTION_DAYS = env_int("NEWS_RETENTION_DAYS", 7)
NEWS_DISPLAY_HOURS = env_int("NEWS_DISPLAY_HOURS", 72)
NEWS_MIN_RELEVANCE = env_int("NEWS_MIN_RELEVANCE", 20)
NEWS_HTTP_TIMEOUT_SECONDS = env_int("NEWS_HTTP_TIMEOUT_SECONDS", 15)
NEWS_CACHE_METADATA_SECONDS = env_int("NEWS_CACHE_METADATA_SECONDS", 86400)
ECONOMIC_CALENDAR_ENABLED = env_bool("ECONOMIC_CALENDAR_ENABLED", True)
ECONOMIC_CALENDAR_REFRESH_SECONDS = env_int("ECONOMIC_CALENDAR_REFRESH_SECONDS", 300)
ECONOMIC_CALENDAR_RETENTION_DAYS = env_int("ECONOMIC_CALENDAR_RETENTION_DAYS", 14)
ECONOMIC_CALENDAR_HTTP_TIMEOUT_SECONDS = env_int("ECONOMIC_CALENDAR_HTTP_TIMEOUT_SECONDS", 25)
ECONOMIC_CALENDAR_HTTP_ATTEMPTS = env_int("ECONOMIC_CALENDAR_HTTP_ATTEMPTS", 2)
ECONOMIC_CALENDAR_CIRCUIT_SECONDS = env_int("ECONOMIC_CALENDAR_CIRCUIT_SECONDS", 300)
ECONOMIC_CALENDAR_MIN_HTML_BYTES = env_int("ECONOMIC_CALENDAR_MIN_HTML_BYTES", 5000)
ECONOMIC_CALENDAR_SOURCE_TIMEZONE = os.getenv("ECONOMIC_CALENDAR_SOURCE_TIMEZONE", "UTC")
ECONOMIC_CALENDAR_COUNTRIES = env_list("ECONOMIC_CALENDAR_COUNTRIES", "BR,US,CN,EA")
AWESOME_API_KEY = os.getenv("AWESOME_API_KEY", "").strip()
SEED_ON_START = env_bool("SEED_ON_START", True)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False) if not DEBUG else False
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0) if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
