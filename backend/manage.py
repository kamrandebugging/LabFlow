#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main() -> None:
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.conf import settings
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # LAB-49 Phase 3.4: a DEBUG=True settings module must never be used
    # implicitly. Local work opts in explicitly with LABFLOW_LOCAL_DEV=1.
    if settings.DEBUG and os.environ.get("LABFLOW_LOCAL_DEV") != "1":
        raise SystemExit(
            "Refusing to run with DEBUG=True. Set LABFLOW_LOCAL_DEV=1 for "
            "local development, or use config.settings.prod in production."
        )

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
