"""Pytest root configuration.

The shared tenant fixtures and environment guards are defined in
``tests/tenant_fixtures.py``. Registering them as a plugin here (the only
place pytest allows ``pytest_plugins``) makes them available to every test
package, including ``apps/*/tests``, without loading ``tests/conftest.py``
twice.
"""

pytest_plugins = ["tests.tenant_fixtures"]
