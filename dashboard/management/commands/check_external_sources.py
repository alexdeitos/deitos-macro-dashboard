from __future__ import annotations

import time
from django.core.management.base import BaseCommand

from dashboard.services.sources import AwesomeApiSource, BancoCentralSource, InvestingSource
from dashboard.services.investing_calendar import collect_investing_daytrade_calendar
from dashboard.services.fed_analysis import collect_fed_data


class Command(BaseCommand):
    help = "Testa as fontes externas do dashboard e exibe diagnóstico por fonte."

    def add_arguments(self, parser):
        parser.add_argument("--no-investing-calendar", action="store_true")
        parser.add_argument("--no-fred", action="store_true")

    def _print_result(self, name, started, ok, detail):
        elapsed = int((time.monotonic() - started) * 1000)
        marker = self.style.SUCCESS("OK") if ok else self.style.ERROR("FALHA")
        self.stdout.write(f"{marker:>8}  {name:<24} {elapsed:>6} ms  {detail}")

    def handle(self, *args, **options):
        self.stdout.write("\nDiagnóstico de fontes externas\n" + "=" * 80)

        for source in (AwesomeApiSource(), BancoCentralSource(), InvestingSource()):
            started = time.monotonic()
            try:
                result = source.fetch()
                detail = f"quotes={len(result.quotes)} complete={result.complete}"
                if result.error:
                    detail += f" | {result.error[:240]}"
                self._print_result(source.name, started, result.ok, detail)
            except Exception as exc:
                self._print_result(source.name, started, False, str(exc)[:300])

        if not options["no_investing_calendar"]:
            started = time.monotonic()
            try:
                result = collect_investing_daytrade_calendar(force=True)
                ok = result.get("status") == "success"
                self._print_result(
                    "investing_calendar",
                    started,
                    ok,
                    f"events_saved={result.get('events_saved', result.get('events_found', 0))}",
                )
            except Exception as exc:
                self._print_result("investing_calendar", started, False, str(exc)[:300])

        if not options["no_fred"]:
            started = time.monotonic()
            try:
                result = collect_fed_data(force=True)
                ok = bool(result.get("available"))
                self._print_result("fred", started, ok, result.get("message") or f"series={len(result.get('latest', {}))}")
            except Exception as exc:
                self._print_result("fred", started, False, str(exc)[:300])

        self.stdout.write("\nObservação: FRED exige FRED_API_KEY; uma ausência de chave é reportada como não disponível, não como erro de rede.\n")
