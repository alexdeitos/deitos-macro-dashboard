#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m pip install -r requirements.txt
python manage.py migrate --settings=macro_dashboard.settings_local
python manage.py collectstatic --noinput --settings=macro_dashboard.settings_local
exec python manage.py runserver 0.0.0.0:8000 --settings=macro_dashboard.settings_local
