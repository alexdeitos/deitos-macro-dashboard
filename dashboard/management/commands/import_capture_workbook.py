from django.core.management.base import BaseCommand, CommandError

from dashboard.services.capture_import import import_workbook


class Command(BaseCommand):
    help = "Importa o workbook de capturas para o banco do dashboard (HISTORICO quando existir; a sincronização ao vivo usa CONFIG_CAPTURA)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Caminho local do arquivo .xlsx/.xlsm")

    def handle(self, *args, **options):
        path = options["path"]
        try:
            with open(path, "rb") as fh:
                class Upload:
                    def __init__(self, stream):
                        self.stream = stream
                    def read(self):
                        return self.stream.read()
                result = import_workbook(Upload(fh))
        except FileNotFoundError as exc:
            raise CommandError(f"Arquivo não encontrado: {path}") from exc
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Importadas {result['imported']} capturas; ignoradas {result['skipped']}."
        ))
