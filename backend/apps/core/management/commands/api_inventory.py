"""Emit (or verify) the checked-in API inventory (LAB-49 Phase 1.1, SE-41).

The inventory is the authoritative list of live routes: path, methods, view,
authentication surface and the central role policy. It is generated from the
URLconf, never hand-written, so a new route cannot ship without appearing here.

Usage::

    python manage.py api_inventory                 # write docs/api-inventory.json
    python manage.py api_inventory --check         # fail when it has drifted
    python manage.py api_inventory --output PATH   # write somewhere else

CI (the user adds this line, per the LAB-49 hard rule):

    cd backend && python manage.py api_inventory --check
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import URLPattern, URLResolver, get_resolver

from apps.core.authorization import (
    PUBLIC_URL_NAMES,
    allowed_roles_for,
    normalize_url_name,
)

_METHODS = ("get", "post", "put", "patch", "delete")
_DEFAULT_OUTPUT = Path(settings.BASE_DIR).parent / "docs" / "api-inventory.json"


def _iter_patterns(patterns: Any, prefix: str = "") -> Any:
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _iter_patterns(
                pattern.url_patterns, prefix + str(pattern.pattern)
            )
        elif isinstance(pattern, URLPattern):
            yield pattern, prefix + str(pattern.pattern)


def _methods_for(view: Any) -> list[str]:
    view_class = getattr(view, "cls", None)
    if view_class is None:
        return ["GET"]
    return [method.upper() for method in _METHODS if hasattr(view_class, method)]


def _view_name(view: Any) -> str:
    view_class = getattr(view, "cls", None)
    if view_class is not None:
        return view_class.__name__
    return getattr(view, "__name__", "unknown")


def _permissions(view: Any) -> list[str]:
    view_class = getattr(view, "cls", None)
    if view_class is None:
        return []
    return [permission.__name__ for permission in view_class.permission_classes]


def build_inventory() -> dict[str, Any]:
    """Walk both URLconfs and return the canonical inventory payload."""
    routes: list[dict[str, Any]] = []
    for urlconf_name in (settings.ROOT_URLCONF, settings.PUBLIC_SCHEMA_URLCONF):
        urlconf = get_resolver(urlconf_name)
        for pattern, route in _iter_patterns(urlconf.url_patterns):
            if route.startswith("admin/"):
                # Django admin is inventoried once as a gated surface below.
                continue
            name = pattern.name or ""
            normalized = normalize_url_name(name)
            permissions = _permissions(pattern.callback)
            public = (
                normalized in PUBLIC_URL_NAMES
                or "AllowAny" in permissions
                or not permissions
            )
            methods = _methods_for(pattern.callback)
            roles: dict[str, list[str]] = {}
            for method in methods:
                allowed = allowed_roles_for(name, method)
                if allowed is not None:
                    roles[method] = sorted(allowed)
            routes.append(
                {
                    "path": "/" + route,
                    "name": normalized,
                    "view": _view_name(pattern.callback),
                    "methods": methods,
                    "permissions": permissions,
                    "public": public,
                    "roles": roles,
                    "urlconf": "public"
                    if urlconf_name == settings.PUBLIC_SCHEMA_URLCONF
                    else "tenant",
                }
            )

    routes.sort(key=lambda row: (row["path"], row["methods"]))
    return {
        "generated_by": "python manage.py api_inventory",
        "version": 1,
        "route_count": len(routes),
        "gated_surfaces": [
            {
                "path": "/admin/",
                "note": "Django admin; IP-allowlisted at Caddy (Phase 3.2)",
            },
            {
                "path": "/api/schema|docs|redoc",
                "note": "OpenAPI docs; gated by DOCS_ENABLED (Phase 3.2)",
            },
        ],
        "routes": routes,
    }


class Command(BaseCommand):
    help = "Emit or verify the API inventory (route list + auth + role policy)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Fail when the checked-in inventory differs from the live URLconf.",
        )
        parser.add_argument(
            "--output",
            default=str(_DEFAULT_OUTPUT),
            help="Output path (default: docs/api-inventory.json).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        payload = build_inventory()
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        output = Path(options["output"])

        if options["check"]:
            if not output.exists():
                raise CommandError(
                    f"{output} is missing; run `python manage.py api_inventory`."
                )
            current = output.read_text(encoding="utf-8")
            if current != rendered:
                raise CommandError(
                    "API inventory drift: run `python manage.py api_inventory` "
                    f"and commit {output}."
                )
            self.stdout.write(
                self.style.SUCCESS(
                    "API inventory matches the live URLconf "
                    f"({payload['route_count']} routes)."
                )
            )
            return

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {payload['route_count']} routes to {output}.")
        )
