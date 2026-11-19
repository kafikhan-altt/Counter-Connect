import os
import sys
import traceback
from pathlib import Path
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'counterconnect.settings')

try:
    _django_app = get_wsgi_application()
    _startup_error = None
except Exception:
    _django_app = None
    _startup_error = traceback.format_exc()

# Auto-migrate and seed demo data on Vercel when using /tmp/db.sqlite3
if os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
    try:
        db_file = Path('/tmp/db.sqlite3')
        if not db_file.exists():
            from django.core.management import call_command
            call_command('migrate', interactive=False)
            call_command('seed_demo')
    except Exception as e:
        print(f"Vercel auto-init warning: {e}")

def app(environ, start_response):
    if _startup_error:
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain; charset=utf-8')])
        return [_startup_error.encode('utf-8')]
    try:
        return _django_app(environ, start_response)
    except Exception:
        err = traceback.format_exc()
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain; charset=utf-8')])
        return [err.encode('utf-8')]

application = app
