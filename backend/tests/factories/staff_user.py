import factory
from django.contrib.auth.hashers import make_password

from apps.accounts.models import Role, StaffUser
from tests.factories.base import TenantModelFactory
from tests.factories.branch import BranchFactory


class StaffUserFactory(TenantModelFactory):
    class Meta:
        model = StaffUser

    branch = factory.SubFactory(BranchFactory)
    role = Role.TECHNICIAN
    email = factory.Sequence(lambda n: f"staff_{n}@labflow.app")
    password_hash = factory.LazyAttribute(
        lambda o: (
            make_password(o.password)
            if o.password
            else "$argon2id$v=19$m=65536,t=3,p=4$fake_salt$fake_hash"
        )
    )
    totp_secret_encrypted = None
    totp_backup_codes_hash = None
    totp_enabled = False
    is_active = True

    class Params:
        # Optional plaintext password; when supplied it is hashed into
        # password_hash instead of the default non-login placeholder.
        password = None
        tenant_wide = factory.Trait(
            branch=None,
            role=Role.OWNER,
        )
