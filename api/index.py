import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["DJANGO_SETTINGS_MODULE"] = "macro_dashboard.settings_vercel"
os.environ.setdefault("SQLITE_PATH", "/tmp/macro_dashboard.sqlite3")

from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()

# O SQLite da Vercel é temporário e cada nova instância pode iniciar sem tabelas.
# Executa as migrações no cold start antes de atender as requisições do dashboard.
from django.core.management import call_command

call_command("migrate", interactive=False, verbosity=0)
