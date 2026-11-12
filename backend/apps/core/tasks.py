"""Core Celery tasks (LAB-49 Phase 2.9)."""

from __future__ import annotations

from typing import Any

from celery import shared_task


@shared_task(name="core.anomaly_sweep")
def anomaly_sweep_task() -> dict[str, Any]:
    """Daily beat entry point for the business-flow anomaly sweep."""
    from django.core.management import call_command

    call_command("anomaly_sweep")
    return {"status": "ok"}
