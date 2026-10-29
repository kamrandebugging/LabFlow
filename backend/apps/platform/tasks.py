from typing import Any

from celery import shared_task


@shared_task(
    name="tenants.provision",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def provision_tenant_task(self: Any, tenant_slug: str) -> dict[str, Any]:
    """Execute the resumable provisioning state machine for a tenant (Doc 04 §5)."""
    from apps.platform.provisioning import run_provisioning_state_machine

    return run_provisioning_state_machine(tenant_slug=tenant_slug)
