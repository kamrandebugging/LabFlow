from __future__ import annotations

import uuid

import factory

from apps.notifications.models import Notification, NotificationTemplate
from tests.factories.base import TenantModelFactory


class NotificationTemplateFactory(TenantModelFactory):
    class Meta:
        model = NotificationTemplate

    key = factory.Sequence(lambda n: f"template_key_{n}")
    locale = NotificationTemplate.Locale.EN
    channel = NotificationTemplate.Channel.EMAIL
    subject = "Your LabFlow Notification"
    body = "Hello {{ name }}, your update is ready."
    template_context_schema = {"required": ["name"]}


class NotificationFactory(TenantModelFactory):
    class Meta:
        model = Notification

    template_key = "report_ready"
    recipient_type = Notification.RecipientType.PATIENT
    recipient_id = factory.LazyFunction(uuid.uuid4)
    channel = Notification.Channel.EMAIL
    status = Notification.Status.PENDING
    attempts = 0
    next_attempt_at = None
    last_error = None
    idempotency_key = factory.Sequence(lambda n: f"notif-idem-{n}")
