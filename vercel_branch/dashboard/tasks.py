from __future__ import annotations

import logging

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from .models import CollectionRun
from .services.collector import CollectionUnavailable, MarketCollector
from .services.economic_calendar import TradingEconomicsCalendarCollector
from .services.news import InvestingNewsCollector
from .services.persistence import cleanup_old_data, persist_payload

logger = logging.getLogger(__name__)
COLLECTION_LOCK_KEY = "market-dashboard:collector-lock"
NEWS_LOCK_KEY = "market-dashboard:news-collector-lock"
CALENDAR_LOCK_KEY = "market-dashboard:economic-calendar-collector-lock"


@shared_task(
    bind=True,
    autoretry_for=(CollectionUnavailable,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def collect_market_snapshot(self) -> dict:
    task_id = self.request.id or "direct"
    if not cache.add(COLLECTION_LOCK_KEY, task_id, timeout=300):
        return {"status": "skipped", "reason": "collection_already_running"}

    run = CollectionRun.objects.create(task_id=task_id)
    try:
        payload = MarketCollector().collect()
        persist_payload(payload, run)
        ok_count = int(payload.get("successful_sources", 0))
        complete_count = int(payload.get("complete_sources", 0))
        total_count = int(payload.get("total_sources", 0))
        run.status = (
            CollectionRun.Status.SUCCESS
            if complete_count == total_count
            else CollectionRun.Status.PARTIAL
        )
        run.source_status = payload.get("source_status", {})
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "source_status", "finished_at"])
        return {
            "status": run.status,
            "collected_at": payload["collected_at"],
            "successful_sources": ok_count,
            "complete_sources": complete_count,
            "total_sources": total_count,
        }
    except Exception as exc:
        run.status = CollectionRun.Status.FAILED
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        logger.exception("Falha na coleta de mercado")
        raise
    finally:
        if cache.get(COLLECTION_LOCK_KEY) == task_id:
            cache.delete(COLLECTION_LOCK_KEY)


@shared_task
def cleanup_market_history() -> dict[str, int]:
    return cleanup_old_data()


@shared_task
def collect_market_news() -> dict:
    if not cache.add(NEWS_LOCK_KEY, "1", timeout=240):
        return {"status": "skipped", "reason": "news_collection_already_running"}
    try:
        return InvestingNewsCollector().collect()
    finally:
        cache.delete(NEWS_LOCK_KEY)


@shared_task
def collect_economic_calendar() -> dict:
    if not cache.add(CALENDAR_LOCK_KEY, "1", timeout=300):
        return {"status": "skipped", "reason": "calendar_collection_already_running"}
    try:
        return TradingEconomicsCalendarCollector().collect()
    finally:
        cache.delete(CALENDAR_LOCK_KEY)
