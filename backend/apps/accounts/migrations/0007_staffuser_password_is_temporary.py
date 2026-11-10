# LAB-62: StaffUser.password_is_temporary — tracks accounts still using the
# provisioning-issued temporary master password (tenant.temp_password).
#
# Set True when the Lab Owner is created during tenant provisioning (P-8) and
# cleared in AuthService.change_password. Login surfaces it to the client as
# ``must_change_password`` so the frontend can show a "change your password"
# warning until the owner sets a personal credential.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_data_export"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffuser",
            name="password_is_temporary",
            field=models.BooleanField(default=False),
        ),
    ]
