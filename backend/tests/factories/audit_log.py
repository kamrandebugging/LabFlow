import uuid

import factory

from apps.accounts.models import AuditLog
from tests.factories.base import TenantModelFactory


class AuditLogFactory(TenantModelFactory):
    class Meta:
        model = AuditLog

    actor_id = factory.LazyFunction(uuid.uuid4)
    action = "patient.registered"
    entity_type = "patient"
    entity_id = factory.LazyFunction(uuid.uuid4)
    before_jsonb = None
    after_jsonb = factory.LazyFunction(lambda: {"status": "active"})
    ip = "127.0.0.1"
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

    class Params:
        system_event = factory.Trait(
            actor_id=None,
        )
