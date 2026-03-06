"""
WSGI config for Brightway Consulting project.
"""

import os
import sys

# Ensure project root is on path (needed on PythonAnywhere and some servers)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bwc.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
