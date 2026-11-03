"""URL routing for the referral-partner registry (Doc 05 §5.1–§5.4, §10;
KAN-164 / LAB-39). All endpoints are Owner only (RM-1, RM-3)."""

from django.urls import path

from apps.partners.views import (
    PartnerCollectionView,
    PartnerDashboardView,
    PartnerDetailView,
    RuleCollectionView,
    RuleDetailView,
)

urlpatterns = [
    path(
        "referral-partners",
        PartnerCollectionView.as_view(),
        name="partner-collection",
    ),
    path(
        "referral-partners/",
        PartnerCollectionView.as_view(),
        name="partner-collection-slash",
    ),
    path(
        "referral-partners/<uuid:partner_id>/dashboard",
        PartnerDashboardView.as_view(),
        name="partner-dashboard",
    ),
    path(
        "referral-partners/<uuid:partner_id>/dashboard/",
        PartnerDashboardView.as_view(),
        name="partner-dashboard-slash",
    ),
    path(
        "referral-partners/<uuid:partner_id>/rules",
        RuleCollectionView.as_view(),
        name="rule-collection",
    ),
    path(
        "referral-partners/<uuid:partner_id>/rules/",
        RuleCollectionView.as_view(),
        name="rule-collection-slash",
    ),
    path(
        "referral-partners/<uuid:partner_id>",
        PartnerDetailView.as_view(),
        name="partner-detail",
    ),
    path(
        "referral-partners/<uuid:partner_id>/",
        PartnerDetailView.as_view(),
        name="partner-detail-slash",
    ),
    path(
        "revenue-share-rules/<uuid:rule_id>",
        RuleDetailView.as_view(),
        name="rule-detail",
    ),
    path(
        "revenue-share-rules/<uuid:rule_id>/",
        RuleDetailView.as_view(),
        name="rule-detail-slash",
    ),
]
