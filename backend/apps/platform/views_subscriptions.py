"""Phase 2 Platform Subscriptions and Mark-Paid views.

Covers:
- GET /api/v1/platform/subscriptions (list + summary cards)
- GET /api/v1/platform/subscriptions/<id> (detail + payment history)
- POST /api/v1/platform/subscriptions/<id>/mark-paid (TOTP-gated write, audit)
- POST /api/v1/platform/subscriptions/<id>/change-plan (TOTP-gated write, audit)
"""

import contextlib
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import (
    Plan,
    Subscription,
    SubscriptionPayment,
)
from apps.platform.access import invalidate_access_mode_cache
from apps.platform.views import (
    IsAuthenticatedPlatformUser,
    PlatformJWTAuthentication,
    problem_response,
)
from apps.platform.views_admin import (
    _get_platform_user,
    _require_totp,
    _unauthorized,
    _write_platform_audit,
)


def _money(val: Decimal | str | None) -> str:
    if val is None:
        return "0.00"
    if isinstance(val, Decimal):
        return f"{val:.2f}"
    try:
        return f"{Decimal(str(val)):.2f}"
    except Exception:
        return "0.00"


class PlatformSubscriptionListView(APIView):
    """GET /api/v1/platform/subscriptions — list subscriptions with summary metrics."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        status_param = request.query_params.get("status", "").strip().lower()
        plan_param = request.query_params.get("plan", "").strip()
        search_query = request.query_params.get("q", "").strip().lower()

        qs = Subscription.objects.select_related("tenant", "plan").all()

        if status_param and status_param != "all":
            if status_param == "founding":
                qs = qs.filter(plan__name__icontains="founding")
            else:
                qs = qs.filter(status=status_param)

        if plan_param and plan_param != "all":
            qs = (
                qs.filter(plan__id=plan_param)
                if _is_uuid(plan_param)
                else qs.filter(plan__name__icontains=plan_param)
            )

        if search_query:
            qs = qs.filter(tenant__name__icontains=search_query) | qs.filter(
                tenant__slug__icontains=search_query
            )

        qs = qs.order_by("-created_at")

        subscriptions_data: list[dict[str, Any]] = []
        for s in qs:
            last_pay = (
                SubscriptionPayment.objects.filter(subscription=s)
                .order_by("-paid_date", "-created_at")
                .first()
            )
            subscriptions_data.append(
                {
                    "id": str(s.id),
                    "tenant": {
                        "id": str(s.tenant.id),
                        "name": s.tenant.name,
                        "slug": s.tenant.slug,
                        "city": s.tenant.city,
                    },
                    "plan": {
                        "id": str(s.plan.id),
                        "name": s.plan.name,
                        "price": _money(s.plan.price),
                    },
                    "billing_cycle": getattr(s, "billing_cycle", "monthly")
                    or "monthly",
                    "amount": _money(s.plan.price),
                    "status": s.status,
                    "starts_at": s.starts_at.isoformat() if s.starts_at else None,
                    "ends_at": s.ends_at.isoformat() if s.ends_at else None,
                    "next_due": s.next_due.isoformat() if s.next_due else None,
                    "last_payment": {
                        "paid_date": last_pay.paid_date.isoformat(),
                        "amount": _money(last_pay.amount),
                        "method": last_pay.method,
                        "reference": last_pay.reference,
                    }
                    if last_pay
                    else None,
                }
            )

        # Compute summary cards
        active_subs = Subscription.objects.filter(status=Subscription.Status.ACTIVE)
        mrr = active_subs.aggregate(total=Sum("plan__price"))["total"] or Decimal(
            "0.00"
        )

        overdue_subs = Subscription.objects.filter(status=Subscription.Status.PAST_DUE)
        overdue_count = overdue_subs.count()
        overdue_amount = overdue_subs.aggregate(total=Sum("plan__price"))[
            "total"
        ] or Decimal("0.00")

        lifetime_subs = Subscription.objects.filter(plan__name__icontains="lifetime")
        lifetime_sold_count = lifetime_subs.count()
        lifetime_revenue = SubscriptionPayment.objects.aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")

        founding_slots_used = Subscription.objects.filter(
            plan__name__icontains="founding"
        ).count()

        return Response(
            {
                "subscriptions": subscriptions_data,
                "summary": {
                    "mrr": _money(mrr),
                    "overdue_count": overdue_count,
                    "overdue_amount": _money(overdue_amount),
                    "lifetime_sold_count": lifetime_sold_count,
                    "lifetime_revenue": _money(lifetime_revenue),
                    "founding_slots_used": founding_slots_used,
                    "founding_slots_total": 10,
                },
            },
            status=status.HTTP_200_OK,
        )


class PlatformSubscriptionDetailView(APIView):
    """GET /api/v1/platform/subscriptions/<id> — detail with full payment ledger."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request, subscription_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        sub = (
            Subscription.objects.select_related("tenant", "plan")
            .filter(id=subscription_id)
            .first()
        )
        if not sub:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Subscription not found.",
                status_code=404,
            )

        payments = (
            SubscriptionPayment.objects.filter(subscription=sub)
            .select_related("recorded_by")
            .order_by("-paid_date", "-created_at")
        )

        payment_list = [
            {
                "id": str(p.id),
                "amount": _money(p.amount),
                "method": p.method,
                "reference": p.reference,
                "notes": p.notes,
                "paid_date": p.paid_date.isoformat(),
                "recorded_by_email": p.recorded_by.email if p.recorded_by else None,
                "created_at": p.created_at.isoformat(),
            }
            for p in payments
        ]

        return Response(
            {
                "id": str(sub.id),
                "tenant": {
                    "id": str(sub.tenant.id),
                    "name": sub.tenant.name,
                    "slug": sub.tenant.slug,
                    "city": sub.tenant.city,
                    "province": sub.tenant.province,
                    "owner_name": sub.tenant.owner_name,
                    "owner_email": sub.tenant.owner_email,
                    "owner_phone": sub.tenant.owner_phone,
                    "status": sub.tenant.status,
                },
                "plan": {
                    "id": str(sub.plan.id),
                    "name": sub.plan.name,
                    "price": _money(sub.plan.price),
                    "max_branches": sub.plan.max_branches,
                    "max_staff": sub.plan.max_staff,
                },
                "billing_cycle": getattr(sub, "billing_cycle", "monthly") or "monthly",
                "status": sub.status,
                "starts_at": sub.starts_at.isoformat() if sub.starts_at else None,
                "ends_at": sub.ends_at.isoformat() if sub.ends_at else None,
                "next_due": sub.next_due.isoformat() if sub.next_due else None,
                "payments": payment_list,
            },
            status=status.HTTP_200_OK,
        )


class PlatformSubscriptionMarkPaidView(APIView):
    """POST /api/v1/platform/subscriptions/<id>/mark-paid — record offline payment."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(self, request: Request, subscription_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        totp_err = _require_totp(user)
        if totp_err:
            return totp_err

        sub = (
            Subscription.objects.select_related("tenant", "plan")
            .filter(id=subscription_id)
            .first()
        )
        if not sub:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Subscription not found.",
                status_code=404,
            )

        data = request.data if isinstance(request.data, dict) else {}
        method = str(data.get("method", "")).strip()
        reference = str(data.get("reference", "")).strip()
        amount_raw = data.get("amount")
        notes = str(data.get("notes", "")).strip()

        if not method:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="Payment method is required.",
                status_code=422,
            )
        if not reference:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="Transaction reference is required.",
                status_code=422,
            )

        try:
            amount = Decimal(
                str(amount_raw if amount_raw is not None else sub.plan.price)
            )
            if amount <= Decimal("0.00"):
                raise ValueError()
        except Exception:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="Amount must be a positive number.",
                status_code=422,
            )

        # If amount differs from plan price, a reason is required in notes
        if amount != sub.plan.price and not notes:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail=(
                    "A reason note is required when recording an amount "
                    "different from the plan price."
                ),
                status_code=422,
            )

        paid_date = timezone.now().date()
        if data.get("paid_date"):
            with contextlib.suppress(Exception):
                paid_date = date.fromisoformat(str(data["paid_date"]))

        payment = SubscriptionPayment.objects.create(
            tenant=sub.tenant,
            subscription=sub,
            amount=amount,
            method=method,
            reference=reference,
            notes=notes,
            paid_date=paid_date,
            recorded_by=user,
        )

        before_state = {
            "status": sub.status,
            "next_due": sub.next_due.isoformat() if sub.next_due else None,
        }

        # Update subscription status and advance next_due date
        sub.status = Subscription.Status.ACTIVE
        cycle = getattr(sub, "billing_cycle", "monthly") or "monthly"
        if cycle == "annual":
            sub.next_due = paid_date + timedelta(days=365)
        elif cycle == "lifetime":
            sub.next_due = None
        else:
            sub.next_due = paid_date + timedelta(days=30)
        sub.save()

        # Invalidate access mode cache
        invalidate_access_mode_cache(sub.tenant.slug)

        after_state = {
            "status": sub.status,
            "next_due": sub.next_due.isoformat() if sub.next_due else None,
            "payment_id": str(payment.id),
            "amount": _money(amount),
            "method": method,
            "reference": reference,
        }

        _write_platform_audit(
            actor_id=user.id,
            action="payment.recorded",
            entity_type="subscription",
            entity_id=sub.id,
            before=before_state,
            after=after_state,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {
                "ok": True,
                "payment_id": str(payment.id),
                "subscription_status": sub.status,
                "next_due": sub.next_due.isoformat() if sub.next_due else None,
            },
            status=status.HTTP_200_OK,
        )


class PlatformSubscriptionChangePlanView(APIView):
    """POST /api/v1/platform/subscriptions/<id>/change-plan."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(self, request: Request, subscription_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        totp_err = _require_totp(user)
        if totp_err:
            return totp_err

        sub = (
            Subscription.objects.select_related("tenant", "plan")
            .filter(id=subscription_id)
            .first()
        )
        if not sub:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Subscription not found.",
                status_code=404,
            )

        data = request.data if isinstance(request.data, dict) else {}
        plan_id = data.get("plan_id")
        if not plan_id:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="plan_id is required.",
                status_code=422,
            )

        plan = Plan.objects.filter(id=plan_id).first()
        if not plan:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Plan not found.",
                status_code=404,
            )

        before_state = {
            "plan_id": str(sub.plan.id),
            "plan_name": sub.plan.name,
            "billing_cycle": getattr(sub, "billing_cycle", "monthly"),
        }

        sub.plan = plan
        if data.get("billing_cycle"):
            sub.billing_cycle = str(data["billing_cycle"])
        sub.save()

        # Invalidate access mode cache
        invalidate_access_mode_cache(sub.tenant.slug)

        after_state = {
            "plan_id": str(plan.id),
            "plan_name": plan.name,
            "billing_cycle": sub.billing_cycle,
        }

        _write_platform_audit(
            actor_id=user.id,
            action="plan.changed",
            entity_type="subscription",
            entity_id=sub.id,
            before=before_state,
            after=after_state,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {
                "ok": True,
                "plan_id": str(plan.id),
                "plan_name": plan.name,
                "billing_cycle": sub.billing_cycle,
            },
            status=status.HTTP_200_OK,
        )


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except Exception:
        return False
