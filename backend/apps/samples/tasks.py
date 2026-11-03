"""Celery tasks for the Samples app (KAN-138 / LAB-22, original LAB-42).

samples.notify_rejection (notifications queue, Doc 01 §13):
- Tells the patient and the collecting branch that a recollection is
  needed (Doc 03 §5.4), using notification_template in the tenant default
  language — tenant_setting key report_default_language (Doc 04 §10.2,
  A-16). Doc 02 has no per-patient language column, so the tenant default
  is used until a per-patient language exists (OQ-30, Doc 07).
- Recipients: the holding branch ALWAYS; the patient ONLY under EV-4
  (Doc 06 §6) — i.e. only if the tenant permits patient rejection notices
  (tenant_setting patient_rejection_notices_enabled, default OFF: "silence
  is better than a message the lab did not choose to send") AND a patient
  contact exists. If either is missing, no patient row is created.
- template_key "sample_rejected" (A-20, Proposed) — NOT seeded in the repo,
  so an interim fallback message is logged and delivery renders from it
  until the template exists.
- Idempotency: keyed on the REJECTED event id — Notification rows carry
  idempotency_key "sample_rejection:{event_id}:{branch|patient}" under the
  partial UNIQUE constraint, so a second run for the same event is a no-op.
- v1 records the notification INTENT as PENDING Notification rows; it does
  NOT send SMS/WhatsApp — delivery (Doc 06) picks the rows up later. A row
  already SENT is never re-sent.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.db import IntegrityError, transaction
from django_tenants.utils import schema_context

from apps.accounts.models import TenantSetting
from apps.notifications.models import Notification, NotificationTemplate
from apps.samples.models import SampleEvent

logger = logging.getLogger(__name__)

TASK_NAME = "samples.notify_rejection"
TEMPLATE_KEY = "sample_rejected"
PATIENT_NOTICES_SETTING = "patient_rejection_notices_enabled"
LANGUAGE_SETTING = "report_default_language"


def _tenant_setting(key: str, default: str) -> str:
    row = TenantSetting.objects.filter(key=key).first()
    return row.value if row is not None else default


def _fallback_message(
    locale: str, *, accession_id: str, branch_phone: str | None
) -> str:
    """Interim A-20 fallback (EV-5): plain, short, no result values.

    Used until the sample_rejected NotificationTemplate is seeded.
    """
    if locale == "ur":
        phone_part = f" برانچ فون: {branch_phone}." if branch_phone else ""
        return (
            f"آپ کا نمونہ ({accession_id}) پراسیس نہیں ہو سکا۔"
            f" نئے نمونے کے لیے لیب سے رابطہ کریں۔{phone_part}"
        )
    phone_part = f" Branch phone: {branch_phone}." if branch_phone else ""
    return (
        f"Your sample ({accession_id}) could not be processed."
        f" Please contact the lab about a new sample.{phone_part}"
    )


@shared_task(name=TASK_NAME)
def notify_rejection_task(schema_name: str, event_id: str) -> dict[str, Any]:
    """Record rejection notices for one REJECTED sample event.

    Idempotent per event id: a second run exits without duplicating rows.
    """
    with schema_context(schema_name):
        try:
            event = SampleEvent.objects.select_related(
                "sample__invoice__patient", "sample__branch", "actor"
            ).get(pk=event_id, event=SampleEvent.EventType.REJECTED)
        except (SampleEvent.DoesNotExist, ValueError):
            logger.warning(
                "samples.notify_rejection: event %s not found in schema %s — skip",
                event_id,
                schema_name,
            )
            return {"status": "skipped", "reason": "event_not_found"}

        sample = event.sample
        patient = sample.invoice.patient
        branch = sample.branch

        locale = _tenant_setting(LANGUAGE_SETTING, "en")
        if locale not in ("en", "ur"):
            locale = "en"
        template = NotificationTemplate.objects.filter(
            key=TEMPLATE_KEY,
            locale=locale,
            channel=Notification.Channel.WHATSAPP,
        ).first()
        if template is None:
            logger.info(
                "samples.notify_rejection: template '%s' (%s) not seeded — "
                "using interim fallback message. Accession %s.",
                TEMPLATE_KEY,
                locale,
                sample.accession_id,
            )
        branch_phone = branch.phone if branch else None
        _fallback_message(
            locale, accession_id=sample.accession_id, branch_phone=branch_phone
        )

        created: list[str] = []
        # 1. Branch notice — always (Doc 06 §6).
        if _record_notice(
            idempotency_key=f"sample_rejection:{event.id}:branch",
            recipient_type=Notification.RecipientType.STAFF,
            recipient_id=None,  # the branch as a whole; resolved via the event id
            channel=Notification.Channel.WHATSAPP,
        ):
            created.append("branch")

        # 2. Patient notice — only under EV-4.
        permit = _tenant_setting(PATIENT_NOTICES_SETTING, "false").lower() == "true"
        if permit and patient is not None and (patient.phone or "").strip():
            if _record_notice(
                idempotency_key=f"sample_rejection:{event.id}:patient",
                recipient_type=Notification.RecipientType.PATIENT,
                recipient_id=patient.id,
                channel=Notification.Channel.WHATSAPP,
            ):
                created.append("patient")
        elif permit:
            logger.info(
                "samples.notify_rejection: patient notice skipped for event %s — "
                "no patient contact.",
                event.id,
            )

        return {
            "status": "ok",
            "event_id": str(event.id),
            "accession_id": sample.accession_id,
            "locale": locale,
            "template": TEMPLATE_KEY if template else "fallback",
            "notices": created,
        }


def _record_notice(
    *,
    idempotency_key: str,
    recipient_type: str,
    recipient_id: Any,
    channel: str,
) -> bool:
    """Insert one PENDING notice intent; False when it already exists."""
    try:
        with transaction.atomic():
            Notification.objects.create(
                template_key=TEMPLATE_KEY,
                recipient_type=recipient_type,
                recipient_id=recipient_id,
                channel=channel,
                status=Notification.Status.PENDING,
                idempotency_key=idempotency_key,
            )
        return True
    except IntegrityError:
        # Already recorded for this event+recipient — idempotent no-op.
        return False
