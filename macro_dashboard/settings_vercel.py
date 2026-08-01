import os
from pathlib import Path

from .settings import *  # noqa: F401,F403

# O filesystem gravável das Vercel Functions é temporário. O SQLite fica em /tmp
# e pode ser reiniciado quando a função sofrer cold start, trocar de instância ou
# receber um novo deploy. Isso é intencional nesta edição.
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", "/tmp/macro_dashboard.sqlite3"))
SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"timeout": 20},
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "macro-dashboard-vercel-sqlite",
        "TIMEOUT": MARKET_CACHE_TTL,
    }
}

# Não há worker Celery permanente. As atualizações são executadas de forma síncrona.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path("/tmp/macro_dashboard_media")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "dashboard.basic_auth.DashboardBasicAuthMiddleware",
    *[
        middleware
        for middleware in MIDDLEWARE
        if middleware != "django.middleware.security.SecurityMiddleware"
    ],
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
