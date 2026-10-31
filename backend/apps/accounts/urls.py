"""URL routes for Authentication & Session Management (Doc 07 §5, Doc 08 §4)."""

from django.urls import path

from apps.accounts.views_auth import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshView,
    RevokeAllSessionsView,
    SessionDetailView,
    SessionListView,
    TotpEnrollConfirmView,
    TotpEnrollView,
    TotpVerifyView,
)

urlpatterns = [
    # Login & Token endpoints
    path("login", LoginView.as_view(), name="auth-login"),
    path("login/", LoginView.as_view(), name="auth-login-slash"),
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh-slash"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("logout/", LogoutView.as_view(), name="auth-logout-slash"),
    # TOTP MFA (Doc 08 §4.4, §17 A-25)
    path("totp/enroll", TotpEnrollView.as_view(), name="auth-totp-enroll"),
    path("totp/enroll/", TotpEnrollView.as_view(), name="auth-totp-enroll-slash"),
    path(
        "totp/enroll/confirm",
        TotpEnrollConfirmView.as_view(),
        name="auth-totp-enroll-confirm",
    ),
    path(
        "totp/enroll/confirm/",
        TotpEnrollConfirmView.as_view(),
        name="auth-totp-enroll-confirm-slash",
    ),
    path("totp/verify", TotpVerifyView.as_view(), name="auth-totp-verify"),
    path("totp/verify/", TotpVerifyView.as_view(), name="auth-totp-verify-slash"),
    # Session management
    path("sessions", SessionListView.as_view(), name="auth-sessions-list"),
    path("sessions/", SessionListView.as_view(), name="auth-sessions-list-slash"),
    path(
        "sessions/revoke-all",
        RevokeAllSessionsView.as_view(),
        name="auth-sessions-revoke-all",
    ),
    path(
        "sessions/revoke-all/",
        RevokeAllSessionsView.as_view(),
        name="auth-sessions-revoke-all-slash",
    ),
    path(
        "sessions/<uuid:session_id>",
        SessionDetailView.as_view(),
        name="auth-session-detail",
    ),
    path(
        "sessions/<uuid:session_id>/",
        SessionDetailView.as_view(),
        name="auth-session-detail-slash",
    ),
    # Password change
    path(
        "password/change",
        PasswordChangeView.as_view(),
        name="auth-password-change",
    ),
    path(
        "password/change/",
        PasswordChangeView.as_view(),
        name="auth-password-change-slash",
    ),
    # Password reset (Doc 08 §4.5, §17 A-26)
    path(
        "password-reset/request",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset-request-slash",
    ),
    path(
        "password-reset/confirm",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm-slash",
    ),
]
