"""URL routing for Patients API (Doc 03 §6.2)."""

from django.urls import path

from apps.patients.views import (
    PatientDetailView,
    PatientHistoryView,
    PatientListCreateView,
)

urlpatterns = [
    path("", PatientListCreateView.as_view(), name="patient-list-create"),
    path("<uuid:id>", PatientDetailView.as_view(), name="patient-detail"),
    path("<uuid:id>/", PatientDetailView.as_view(), name="patient-detail-slash"),
    path("<uuid:id>/history", PatientHistoryView.as_view(), name="patient-history"),
    path(
        "<uuid:id>/history/", PatientHistoryView.as_view(), name="patient-history-slash"
    ),
]
