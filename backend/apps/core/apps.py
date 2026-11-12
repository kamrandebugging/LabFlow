from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Core Tenancy Platform"

    def ready(self) -> None:
        # Error reporting is opt-in via SENTRY_DSN (no DSN -> no-op).
        from apps.core.observability import init_sentry

        init_sentry()
        # Register the outbound-webhook startup check (API7 G-11).
        from apps.core import checks  # noqa: F401
