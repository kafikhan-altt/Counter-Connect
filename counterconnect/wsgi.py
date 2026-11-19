"""
WSGI config for counterconnect project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'counterconnect.settings')

application = get_wsgi_application()
app = application

# Auto-migrate and seed demo data on Vercel when using /tmp/db.sqlite3
if os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
    db_file = Path('/tmp/db.sqlite3')
    if not db_file.exists() or db_file.stat().st_size == 0:
        from django.core.management import call_command
        try:
            call_command('migrate', interactive=False)
            call_command('seed_demo')
        except Exception as e:
            print(f"Auto-init warning: {e}")
