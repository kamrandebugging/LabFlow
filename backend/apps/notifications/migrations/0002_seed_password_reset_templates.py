"""Data migration to seed password_reset notification templates for en and ur (Doc 08 §17 A-27, Doc 02 §5.9, KAN-105)."""

from typing import Any

from django.db import migrations

PASSWORD_RESET_TEMPLATES = [
    (
        "password_reset",
        "en",
        "email",
        "Password Reset Request — {{ lab_name }}",
        (
            "Dear {{ staff_name }},\n\n"
            "A password reset request was received for your account at {{ lab_name }}. "
            "Click the link below to reset your password:\n\n"
            "{{ reset_link }}\n\n"
            "This link expires in 60 minutes. If you did not request this, you can safely ignore this email."
        ),
        {"variables": ["staff_name", "lab_name", "reset_link", "token"]},
    ),
    (
        "password_reset",
        "ur",
        "email",
        "پاس ورڈ ری سیٹ کی درخواست — {{ lab_name }}",
        (
            "محترم {{ staff_name }}،\n\n"
            "آپ کے اکاؤنٹ کا پاس ورڈ ری سیٹ کرنے کی درخواست موصول ہوئی ہے۔ "
            "اپنا پاس ورڈ تبدیل کرنے کے لیے نیچے دیے گئے لنک پر کلک کریں:\n\n"
            "{{ reset_link }}\n\n"
            "یہ لنک 60 منٹ کے لیے کارآمد ہے۔ اگر آپ نے یہ درخواست نہیں کی تو اس ای میل کو نظر انداز کر دیں۔"
        ),
        {"variables": ["staff_name", "lab_name", "reset_link", "token"]},
    ),
]


def seed_password_reset_templates(apps: Any, schema_editor: Any) -> None:
    NotificationTemplate = apps.get_model("notifications", "NotificationTemplate")
    for key, locale, channel, subject, body, schema in PASSWORD_RESET_TEMPLATES:
        NotificationTemplate.objects.get_or_create(
            key=key,
            locale=locale,
            channel=channel,
            defaults={
                "subject": subject,
                "body": body,
                "template_context_schema": schema,
            },
        )


def remove_password_reset_templates(apps: Any, schema_editor: Any) -> None:
    NotificationTemplate = apps.get_model("notifications", "NotificationTemplate")
    NotificationTemplate.objects.filter(key="password_reset").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_notification_models"),
    ]

    operations = [
        migrations.RunPython(
            seed_password_reset_templates,
            reverse_code=remove_password_reset_templates,
        ),
    ]
