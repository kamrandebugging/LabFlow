"""Celery app for LabFlow (KAN-155 / LAB-30).

Wires the shared tasks (apps/*/tasks.py) to Django settings via the CELERY
namespace. Task routing: the reports queue (Doc 01 §13) is a deployment
concern — workers are started with -Q reports,... as needed.

Test settings set CELERY_TASK_ALWAYS_EAGER=True so .delay() executes
synchronously in tests.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

app = Celery("labflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
