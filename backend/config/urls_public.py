"""URL Configuration for the public schema (platform admin, TLS check,
apex endpoints).
"""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
