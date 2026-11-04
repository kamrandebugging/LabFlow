from __future__ import annotations

import factory

from apps.accounts.models import DataExport
from tests.factories.base import TenantModelFactory
from tests.factories.staff_user import StaffUserFactory

__all__ = ["StaffUserFactory", "DataExportFactory"]


class DataExportFactory(TenantModelFactory):
    """Factory for accounts.DataExport (LAB-38 / KAN-163)."""

    class Meta:
        model = DataExport

    requested_by = factory.SubFactory(StaffUserFactory)
    status = DataExport.Status.PENDING
    bundle_key = None
    download_url = None
    download_expires_at = None
    error = None
    completed_at = None
