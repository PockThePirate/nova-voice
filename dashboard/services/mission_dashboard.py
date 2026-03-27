"""
Build dashboard context for education, freelance income, and IoT lab widgets.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone

from dashboard.models import DailyBuildBlock, IncomeProfile, IoTLabEntry, PipelineItem


def format_usd_minor(cents: int | None) -> str:
    """
    Format integer cents as a compact USD string for dashboard tiles.

    Args:
        cents (int | None): Amount in cents, or None for empty display.

    Returns:
        str: Human-readable dollar amount or em dash.

    Example:
        assert format_usd_minor(8500000) == "$85,000"
    """
    if cents is None:
        return "—"
    return f"${cents / 100:,.0f}"


class DashboardMissionContextBuilder:
    """
    Assemble mission-control widget data for ``dashboard_view`` template context.

    Args:
        None (class uses only static ``extend``).

    Returns:
        DashboardMissionContextBuilder: Callable namespace; use ``extend``.

    Example:
        ctx = DashboardMissionContextBuilder.extend(base_context)
    """

    @classmethod
    def extend(cls, context: dict) -> dict:
        """
        Merge income, pipeline, build block, and IoT lab keys into context.

        Args:
            context (dict): Existing template context from ``dashboard_view``.

        Returns:
            dict: Same dict instance with added keys for new panels.

        Example:
            DashboardMissionContextBuilder.extend({"request": request, ...})
        """
        profile, _ = IncomeProfile.objects.get_or_create(
            pk=1,
            defaults={
                "annual_target_cents": 8_500_000,
                "currency": "USD",
            },
        )
        stage_counts: dict[str, int] = {}
        for stage, _label in PipelineItem.STAGE_CHOICES:
            stage_counts[stage] = PipelineItem.objects.filter(stage=stage).count()

        pipeline_qs = PipelineItem.objects.all()[:20]
        pipeline_rows = [
            {
                "item": p,
                "expected_display": format_usd_minor(p.expected_value_cents),
            }
            for p in pipeline_qs
        ]
        today = timezone.localdate()
        daily_build = DailyBuildBlock.objects.filter(date=today).first()
        iot_entries = list(IoTLabEntry.objects.all()[:12])

        context.update(
            {
                "income_annual_display": format_usd_minor(profile.annual_target_cents),
                "income_monthly_display": format_usd_minor(profile.monthly_target_cents),
                "income_currency": profile.currency,
                "pipeline_stage_counts": stage_counts,
                "pipeline_rows": pipeline_rows,
                "daily_build": daily_build,
                "iot_entries": iot_entries,
                "admin_income_url": reverse("admin:dashboard_incomeprofile_changelist"),
                "admin_pipeline_url": reverse("admin:dashboard_pipelineitem_changelist"),
                "admin_build_url": reverse("admin:dashboard_dailybuildblock_changelist"),
                "admin_iot_url": reverse("admin:dashboard_iotlabentry_changelist"),
            }
        )
        return context
