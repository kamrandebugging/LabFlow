"""URL routing for Tenant Settings endpoints (Doc 04 §10, KAN-160 / LAB-35)."""

from django.urls import path

from apps.platform.views_settings import SettingsView

urlpatterns = [
    path("settings", SettingsView.as_view(), name="settings"),
    path("settings/", SettingsView.as_view(), name="settings-slash"),
]
