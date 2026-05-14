"""
wsgi.py — Gunicorn / uWSGI entry point for OstelloRides.

Usage (VPS / Railway / Render / Fly):
  gunicorn --chdir backend wsgi:app --bind 0.0.0.0:8000 --workers 2

Environment variables:
  SECRET_KEY   — Flask secret (required in production)
  OSRM_BASE    — Override OSRM endpoint (default: project-osrm.org/driving)
  DB_PATH      — Override SQLite path (optional; defaults to database/ostello.db)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app import app, ensure_db_ready, normalize_seed_user_hashes

ensure_db_ready()
normalize_seed_user_hashes()
