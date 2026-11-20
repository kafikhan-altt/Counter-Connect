import os
import sys
import shutil
import traceback
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'counterconnect.settings')

# Fast 1-millisecond initialization on Vercel for local SQLite fallback: copy pre-seeded template to /tmp
if os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
    try:
        db_file = Path('/tmp/db.sqlite3')
        if not db_file.exists():
            template_db = Path(__file__).resolve().parent.parent / 'demo_template.sqlite3'
            if template_db.exists():
                shutil.copyfile(template_db, db_file)
            else:
                from django.core.management import call_command
                call_command('migrate', interactive=False)
                call_command('seed_demo')
    except Exception as e:
        print(f"Vercel auto-init note: {e}")

from django.core.wsgi import get_wsgi_application

try:
    _django_app = get_wsgi_application()
    _startup_error = None

    # If connected to cloud PostgreSQL (Supabase), ensure tables and demo data exist
    if os.environ.get('VERCEL') and os.environ.get('DATABASE_URL'):
        try:
            from django.db import connection
            table_names = connection.introspection.table_names()
            if 'catalog_location' not in table_names:
                from django.core.management import call_command
                call_command('migrate', interactive=False)
                call_command('seed_demo')
        except Exception as db_err:
            print(f"Cloud DB migration notice: {db_err}")
except Exception:
    _django_app = None
    _startup_error = traceback.format_exc()

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
