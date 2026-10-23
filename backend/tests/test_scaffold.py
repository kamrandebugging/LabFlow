"""
Scaffold verification test.
Proves that pytest-django test harness executes and settings load properly
(Doc 09 §9.1).
"""

from django.conf import settings


def test_django_settings_loaded() -> None:
    """Assert Django settings boot and DEBUG flag is readable."""
    assert hasattr(settings, "DEBUG")
    assert isinstance(settings.DEBUG, bool)
    assert settings.DEBUG is False
