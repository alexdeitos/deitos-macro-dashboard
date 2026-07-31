import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "macro_dashboard.settings_vercel")
os.environ.setdefault("SQLITE_PATH", "/tmp/macro_dashboard.sqlite3")

from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()

# Cada instância serverless pode começar sem banco. As migrações criam o SQLite
# temporário automaticamente no cold start. O histórico permanece apenas enquanto
# essa instância e seu /tmp existirem.
from django.core.management import call_command

call_command("migrate", interactive=False, verbosity=0)
