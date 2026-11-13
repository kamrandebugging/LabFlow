"""Demo seed must never print passwords/TOTP secrets by default."""

from io import StringIO

from apps.core.management.commands.seed_demo_tenant import Command

OPERATOR = {
    "email": "admin@example.test",
    "password": "SuperSecretDemoPass!",
    "totp_secret": "JBSWY3DPEHPK3PXP",
}
TENANTS = [
    {
        "name": "Demo Lab",
        "slug": "demolab",
        "domain": "demolab.localhost",
        "staff": [
            {
                "role": "owner",
                "email": "owner@demolab.test",
                "password": "OwnerDemoPass!",
                "totp": "GEZ4KAMYMW6UZWV2UIDBOHZNSEUQOSDK",
            }
        ],
    }
]


def _render(*, show_credentials: bool) -> str:
    out = StringIO()
    command = Command(stdout=out)
    command._print_summary(  # noqa: SLF001 - direct summary contract test
        OPERATOR, TENANTS, show_credentials=show_credentials
    )
    return out.getvalue()


def test_default_summary_prints_no_credentials_or_secrets() -> None:
    rendered = _render(show_credentials=False)
    assert "admin@example.test" in rendered
    assert "owner@demolab.test" in rendered
    for secret in (
        OPERATOR["password"],
        OPERATOR["totp_secret"],
        "OwnerDemoPass!",
        "GEZ4KAMYMW6UZWV2UIDBOHZNSEUQOSDK",
    ):
        assert secret not in rendered
    assert "--show-credentials" in rendered


def test_show_credentials_requires_warning_and_prints_values() -> None:
    rendered = _render(show_credentials=True)
    assert "WARNING" in rendered
    assert OPERATOR["password"] in rendered
    assert OPERATOR["totp_secret"] in rendered
    assert "OwnerDemoPass!" in rendered
