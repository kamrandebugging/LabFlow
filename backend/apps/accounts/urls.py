"""URL routes for Authentication & Session Management (Doc 07 §5, Doc 08 §4)."""

from django.urls import path

from apps.accounts.views_auth import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    RefreshView,
    RevokeAllSessionsView,
    SessionDetailView,
    SessionListView,
)

urlpatterns = [
    # Login & Token endpoints
    path("login", LoginView.as_view(), name="auth-login"),
    path("login/", LoginView.as_view(), name="auth-login-slash"),
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh-slash"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("logout/", LogoutView.as_view(), name="auth-logout-slash"),
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
]
