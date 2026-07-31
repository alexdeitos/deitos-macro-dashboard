import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["DJANGO_SETTINGS_MODULE"] = "macro_dashboard.settings_vercel"

from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()
