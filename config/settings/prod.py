"""Ambiente di produzione.

Non esercitato in questa prova: presente per completezza e per tenere fuori da
base.py le impostazioni che varierebbero al deploy.
"""

from .base import *  # noqa: F401,F403

DEBUG = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
