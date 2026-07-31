from django.core.management.base import BaseCommand

from dashboard.services.news import InvestingNewsCollector


class Command(BaseCommand):
    help = "Coleta as notícias dos feeds RSS configurados e salva sem duplicidade."

    def handle(self, *args, **options):
        result = InvestingNewsCollector().collect()
        self.stdout.write(self.style.SUCCESS(str(result)))
