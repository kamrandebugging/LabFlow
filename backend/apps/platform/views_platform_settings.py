"""Phase 2 Platform Commercial & Operational Settings views (Doc 15).

Covers:
- GET /api/v1/platform/settings
- PUT /api/v1/platform/settings (TOTP-gated write, audit, syncs Plan prices)
"""

import uuid
from decimal import Decimal

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import (
    Plan,
    PlatformSetting,
    Subscription,
)
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


class PlatformSettingsView(APIView):
    """GET / PUT /api/v1/platform/settings."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        # 1. Commercial Tiers: Read live prices from Plan table
        plans_by_name = {p.name.lower(): p for p in Plan.objects.filter(is_active=True)}

        starter_price = (
            f"{plans_by_name['starter'].price:.2f}"
            if "starter" in plans_by_name
            else "2999.00"
        )
        growth_price = (
            f"{plans_by_name['growth'].price:.2f}"
            if "growth" in plans_by_name
            else "5999.00"
        )
        scale_price = (
            f"{plans_by_name['scale'].price:.2f}"
            if "scale" in plans_by_name
            else "9999.00"
        )

        lifetime_single_plan = next(
            (
                p
                for name, p in plans_by_name.items()
                if "single" in name and "lifetime" in name
            ),
            None,
        )
        lifetime_multi_plan = next(
            (
                p
                for name, p in plans_by_name.items()
                if "multi" in name and "lifetime" in name
            ),
            None,
        )

        lifetime_single_price = (
            f"{lifetime_single_plan.price:.2f}" if lifetime_single_plan else "71999.00"
        )
        lifetime_multi_price = (
            f"{lifetime_multi_plan.price:.2f}" if lifetime_multi_plan else "143999.00"
        )

        setting_tiers = PlatformSetting.objects.filter(key="commercial_tiers").first()
        tiers_data = setting_tiers.value if setting_tiers else {}
        annual_maintenance_pct = tiers_data.get("annual_maintenance_pct", 15)

        commercial_tiers = {
            "starter_price": starter_price,
            "growth_price": growth_price,
            "scale_price": scale_price,
            "lifetime_single_price": lifetime_single_price,
            "lifetime_multi_price": lifetime_multi_price,
            "annual_maintenance_pct": annual_maintenance_pct,
        }

        # 2. Founding Offer
        founding_setting = PlatformSetting.objects.filter(key="founding_offer").first()
        founding_val = founding_setting.value if founding_setting else {}
        slots_used = Subscription.objects.filter(
            plan__name__icontains="founding"
        ).count()

        founding_offer = {
            "slots_total": founding_val.get("slots_total", 10),
            "slots_used": slots_used,
            "enabled": founding_val.get("enabled", True),
        }

        # 3. Platform Toggles
        toggles_setting = PlatformSetting.objects.filter(key="platform_toggles").first()
        toggles_val = toggles_setting.value if toggles_setting else {}

        platform_toggles = {
            "new_signups_enabled": toggles_val.get("new_signups_enabled", True),
            "maintenance_mode": toggles_val.get("maintenance_mode", False),
        }

        return Response(
            {
                "commercial_tiers": commercial_tiers,
                "founding_offer": founding_offer,
                "platform_toggles": platform_toggles,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request: Request) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        totp_err = _require_totp(user)
        if totp_err:
            return totp_err

        data = request.data if isinstance(request.data, dict) else {}
        section = data.get("section")
        section_data = data.get("data")

        if not section or not isinstance(section_data, dict):
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="section and data dict are required.",
                status_code=422,
            )

        before_setting = PlatformSetting.objects.filter(key=section).first()
        before_val = before_setting.value if before_setting else {}

        if section == "commercial_tiers":
            # Flow edited prices directly to the live Plan table
            if "starter_price" in section_data:
                Plan.objects.filter(name__iexact="Starter").update(
                    price=Decimal(str(section_data["starter_price"]))
                )
            if "growth_price" in section_data:
                Plan.objects.filter(name__iexact="Growth").update(
                    price=Decimal(str(section_data["growth_price"]))
                )
            if "scale_price" in section_data:
                Plan.objects.filter(name__iexact="Scale").update(
                    price=Decimal(str(section_data["scale_price"]))
                )
            if "lifetime_single_price" in section_data:
                Plan.objects.filter(name__icontains="Lifetime (Single").update(
                    price=Decimal(str(section_data["lifetime_single_price"]))
                )
            if "lifetime_multi_price" in section_data:
                Plan.objects.filter(name__icontains="Lifetime (Multi").update(
                    price=Decimal(str(section_data["lifetime_multi_price"]))
                )

            merged_data = {**before_val, **section_data}
            PlatformSetting.objects.update_or_create(
                key=section,
                defaults={"value": merged_data, "updated_by": user},
            )

        elif section in ("founding_offer", "platform_toggles"):
            merged_data = {**before_val, **section_data}
            PlatformSetting.objects.update_or_create(
                key=section,
                defaults={"value": merged_data, "updated_by": user},
            )
        else:
            return problem_response(
                code="unknown_section",
                title="Unknown settings section",
                detail=f"Section {section} is not supported.",
                status_code=422,
            )

        _write_platform_audit(
            actor_id=user.id,
            action="settings.updated",
            entity_type="platform_setting",
            entity_id=uuid.uuid4(),
            before={section: before_val},
            after={section: section_data},
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {"ok": True, "section": section, "data": section_data},
            status=status.HTTP_200_OK,
        )
