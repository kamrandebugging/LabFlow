"""Re-export public schema URLs from config.urls_public (Doc 04 §6.4)."""

from config.urls_public import urlpatterns

__all__ = ["urlpatterns"]
