from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from dashboard.models import CollectionRun
from dashboard.services.collector import MarketCollector
from dashboard.services.persistence import persist_payload


class Command(BaseCommand):
    help = "Executa uma coleta síncrona usando apenas dados reais das fontes configuradas."

    def handle(self, *args, **options):
        run = CollectionRun.objects.create(task_id="management-command")
        try:
            payload = MarketCollector().collect()
            persist_payload(payload, run)
            run.status = (
                CollectionRun.Status.SUCCESS
                if payload.get("is_complete")
                else CollectionRun.Status.PARTIAL
            )
            run.source_status = payload.get("source_status", {})
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "source_status", "finished_at"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Coleta concluída: {payload.get('successful_sources')}/{payload.get('total_sources')} fontes."
                )
            )
        except Exception as exc:
            run.status = CollectionRun.Status.FAILED
            run.error = str(exc)
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error", "finished_at"])
            raise CommandError(str(exc)) from exc
