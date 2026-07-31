from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dashboard.models import CollectionRun, MarketPoint, MarketSnapshot


class Command(BaseCommand):
    help = "Apaga somente o histórico de mercado, preservando usuários e configurações."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("Use --confirm para confirmar a exclusão do histórico de mercado.")
        points = MarketPoint.objects.all().delete()[0]
        snapshots = MarketSnapshot.objects.all().delete()[0]
        runs = CollectionRun.objects.all().delete()[0]
        self.stdout.write(self.style.SUCCESS(
            f"Histórico removido: {points} pontos, {snapshots} snapshots e {runs} execuções."
        ))
