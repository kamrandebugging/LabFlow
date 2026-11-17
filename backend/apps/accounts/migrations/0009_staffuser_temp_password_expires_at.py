from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_staff_identity_and_ci_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffuser",
            name="temp_password_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
