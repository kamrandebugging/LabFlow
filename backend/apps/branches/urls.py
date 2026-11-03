"""URL routing for Branch operations (Doc 04 §8.2, §8.3, §11.3, KAN-158 / LAB-33)."""

from django.urls import path

from apps.branches.views import (
    BranchCloseView,
    BranchDetailView,
    BranchListCreateView,
    BranchReopenView,
)

urlpatterns = [
    path("", BranchListCreateView.as_view(), name="branch-list-create"),
    path("<uuid:branch_id>", BranchDetailView.as_view(), name="branch-detail"),
    path(
        "<uuid:branch_id>/",
        BranchDetailView.as_view(),
        name="branch-detail-slash",
    ),
    path("<uuid:branch_id>/close", BranchCloseView.as_view(), name="branch-close"),
    path(
        "<uuid:branch_id>/close/",
        BranchCloseView.as_view(),
        name="branch-close-slash",
    ),
    path("<uuid:branch_id>/reopen", BranchReopenView.as_view(), name="branch-reopen"),
    path(
        "<uuid:branch_id>/reopen/",
        BranchReopenView.as_view(),
        name="branch-reopen-slash",
    ),
]
