from django.core.management.base import BaseCommand

from dashboard.services.economic_calendar import TradingEconomicsCalendarCollector


class Command(BaseCommand):
    help = "Coleta o calendário econômico público da Trading Economics."

    def handle(self, *args, **options):
        result = TradingEconomicsCalendarCollector().collect()
        self.stdout.write(self.style.SUCCESS(str(result)) if result.get("status") == "success" else self.style.WARNING(str(result)))
