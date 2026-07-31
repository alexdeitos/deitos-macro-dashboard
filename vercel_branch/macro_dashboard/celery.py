import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "macro_dashboard.settings")

app = Celery("macro_dashboard")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "collect-market-data": {
        "task": "dashboard.tasks.collect_market_snapshot",
        "schedule": float(settings.MARKET_REFRESH_SECONDS),
    },
    "collect-market-news": {
        "task": "dashboard.tasks.collect_market_news",
        "schedule": float(settings.NEWS_REFRESH_SECONDS),
    },
    "collect-economic-calendar": {
        "task": "dashboard.tasks.collect_economic_calendar",
        "schedule": float(settings.ECONOMIC_CALENDAR_REFRESH_SECONDS),
    },
    "cleanup-market-history": {
        "task": "dashboard.tasks.cleanup_market_history",
        "schedule": 86400.0,
    },
}
