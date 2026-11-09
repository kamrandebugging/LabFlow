"""Directory-level conftest for the ``tests`` package.

Shared fixtures and session guards live in ``tests.tenant_fixtures`` and are
registered from the repository-root ``conftest.py`` via ``pytest_plugins`` so
they are also available to tests inside ``apps/``. Nothing needs to be
auto-loaded from this file; keeping it (almost) empty avoids registering the
same module twice as both a conftest and a plugin.
"""
