import hashlib
from urllib.parse import urlencode

from django.utils import timezone
from django.urls import reverse

from allocations.models import Allocation
from maintenance.models import Maintenance


def build_user_notifications(user, limit=6):
    if not getattr(user, "is_authenticated", False):
        return []

    today = timezone.localdate()
    notifications = []
    seen_notifications = set()
    dashboard_url = reverse("assets:dashboard")
    maintenance_workspace_url = reverse("assets:workspace_resource", kwargs={"resource": "maintenance"})

    def build_notification_id(*parts):
        raw_key = "|".join(str(part or "") for part in parts)
        return hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:12]

    def build_dashboard_action_url(section, **query_params):
        clean_params = {
            key: value
            for key, value in query_params.items()
            if value not in {None, ""}
        }
        query_string = urlencode(clean_params)
        section_fragment = section if section.startswith("#") else f"#{section}"
        if query_string:
            return f"{dashboard_url}?{query_string}{section_fragment}"
        return f"{dashboard_url}{section_fragment}"

    def build_workspace_action_url(base_url, **query_params):
        clean_params = {
            key: value
            for key, value in query_params.items()
            if value not in {None, ""}
        }
        query_string = urlencode(clean_params)
        if query_string:
            return f"{base_url}?{query_string}"
        return base_url

    def fallback_action_required(action_label, action_target):
        if action_target == "#role-workspace":
            return "Open the workspace tools and review the record that needs your attention."
        if action_target == "#activity-overview":
            return "Open the activity overview and review the related record."
        return "Open your dashboard and review the item that needs your attention."

    def add_notification(
        *,
        level,
        title,
        message,
        asset_label,
        target_date,
        priority,
        sort_date,
        action_required="",
        context_note="",
        action_target="#personal-overview",
        action_label="Open Dashboard",
        action_url="",
    ):
        notification_key = (title, message, asset_label, target_date)
        if notification_key in seen_notifications:
            return

        seen_notifications.add(notification_key)
        notification_id = build_notification_id(level, title, message, asset_label, target_date, action_target)
        notifications.append(
            {
                "id": notification_id,
                "level": level,
                "title": title,
                "message": message,
                "asset_label": asset_label,
                "target_date": target_date,
                "priority": priority,
                "sort_date": sort_date,
                "action_required": action_required,
                "context_note": context_note,
                "action_target": action_target,
                "action_label": action_label,
                "action_url": action_url or build_dashboard_action_url(action_target, notification=notification_id),
            }
        )

    assets_under_care_queryset = Allocation.objects.select_related("asset").filter(
        allocated_to=user,
        status__in=["active", "overdue"],
    )
    assets_under_care_asset_ids = list(assets_under_care_queryset.values_list("asset_id", flat=True))

    for allocation in assets_under_care_queryset.exclude(expected_return_date__isnull=True).order_by("expected_return_date", "asset__name"):
        days_until_return = (allocation.expected_return_date - today).days

        if allocation.status == "overdue" or days_until_return < 0:
            add_notification(
                level="urgent",
                title="Return overdue",
                message=f"{allocation.asset.name} should have been returned on {allocation.expected_return_date:%b %d, %Y}.",
                asset_label=allocation.asset.asset_id,
                target_date=allocation.expected_return_date,
                priority=0,
                sort_date=allocation.expected_return_date,
                action_required="Return this asset to your department office as soon as possible, or contact the department office immediately if you cannot return it today.",
                context_note=f"Issued for: {allocation.purpose}" if allocation.purpose else "",
                action_url=build_dashboard_action_url("#personal-overview", focus_asset_id=allocation.asset_id),
            )
        elif days_until_return == 0:
            add_notification(
                level="warning",
                title="Return due today",
                message=f"{allocation.asset.name} is due back today. Return it or contact the department office if you need an extension.",
                asset_label=allocation.asset.asset_id,
                target_date=allocation.expected_return_date,
                priority=1,
                sort_date=allocation.expected_return_date,
                action_required="Return this asset today, or request an extension before the end of the day if you still need it.",
                context_note=f"Issued for: {allocation.purpose}" if allocation.purpose else "",
                action_url=build_dashboard_action_url("#personal-overview", focus_asset_id=allocation.asset_id),
            )
        elif days_until_return <= 7:
            add_notification(
                level="info",
                title="Return due soon",
                message=f"{allocation.asset.name} is due back on {allocation.expected_return_date:%b %d, %Y}.",
                asset_label=allocation.asset.asset_id,
                target_date=allocation.expected_return_date,
                priority=2,
                sort_date=allocation.expected_return_date,
                action_required="Plan the return early and confirm the handover point with your department before the due date.",
                context_note=f"Issued for: {allocation.purpose}" if allocation.purpose else "",
                action_url=build_dashboard_action_url("#personal-overview", focus_asset_id=allocation.asset_id),
            )

    if assets_under_care_asset_ids:
        maintenance_notifications_qs = Maintenance.objects.select_related("asset").filter(
            asset_id__in=assets_under_care_asset_ids,
            status__in=["scheduled", "in_progress"],
        ).order_by("scheduled_date", "created_at")

        for item in maintenance_notifications_qs:
            days_until_service = (item.scheduled_date - today).days

            if item.status == "in_progress":
                add_notification(
                    level="warning",
                    title="Maintenance in progress",
                    message=f"{item.asset.name} is currently under {item.get_maintenance_type_display().lower()} maintenance.",
                    asset_label=item.asset.asset_id,
                    target_date=item.scheduled_date,
                    priority=1,
                    sort_date=item.scheduled_date,
                    action_required="Avoid relying on this asset until the maintenance work is finished, and contact your department if you need an alternative.",
                    context_note=item.description,
                    action_url=build_dashboard_action_url("#personal-overview", focus_asset_id=item.asset_id),
                )
            elif days_until_service < 0:
                add_notification(
                    level="urgent",
                    title="Scheduled maintenance overdue",
                    message=f"{item.asset.name} was scheduled for maintenance on {item.scheduled_date:%b %d, %Y}.",
                    asset_label=item.asset.asset_id,
                    target_date=item.scheduled_date,
                    priority=0,
                    sort_date=item.scheduled_date,
                    action_required="Follow up with the department office or technician and keep the asset available for servicing until the work is completed.",
                    context_note=item.description,
                    action_url=build_dashboard_action_url("#personal-overview", focus_asset_id=item.asset_id),
                )
            elif days_until_service == 0:
                add_notification(
                    level="warning",
                    title="Scheduled maintenance today",
                    message=f"{item.asset.name} is scheduled for {item.get_maintenance_type_display().lower()} maintenance today.",
                    asset_label=item.asset.asset_id,
                    target_date=item.scheduled_date,
                    priority=1,
                    sort_date=item.scheduled_date,
                    action_required="Make the asset available for servicing today and pause normal use until the technician has completed the work.",
                    context_note=item.description,
                    action_url=build_dashboard_action_url("#personal-overview", focus_asset_id=item.asset_id),
                )
            elif days_until_service <= 7:
                add_notification(
                    level="info",
                    title="Maintenance scheduled soon",
                    message=f"{item.asset.name} has maintenance scheduled for {item.scheduled_date:%b %d, %Y}.",
                    asset_label=item.asset.asset_id,
                    target_date=item.scheduled_date,
                    priority=2,
                    sort_date=item.scheduled_date,
                    action_required="Keep the asset available on the scheduled date and watch for any instructions from the department or technician.",
                    context_note=item.description,
                    action_url=build_dashboard_action_url("#personal-overview", focus_asset_id=item.asset_id),
                )

    technician_maintenance_qs = Maintenance.objects.select_related("asset").filter(
        technician=user,
        status__in=["scheduled", "in_progress"],
    ).order_by("scheduled_date", "created_at")

    for item in technician_maintenance_qs:
        days_until_service = (item.scheduled_date - today).days
        maintenance_type_label = item.get_maintenance_type_display().lower()

        if item.status == "in_progress":
            add_notification(
                level="warning",
                title="Assigned maintenance in progress",
                message=f"You are assigned to {maintenance_type_label} maintenance for {item.asset.name}.",
                asset_label=item.asset.asset_id,
                target_date=item.scheduled_date,
                priority=1,
                sort_date=item.scheduled_date,
                action_required="Open the maintenance workspace, update the task progress, and record any findings, parts used, or blockers.",
                context_note=item.description,
                action_target=maintenance_workspace_url,
                action_label="Open Workspace Tools",
                action_url=build_workspace_action_url(maintenance_workspace_url, search=item.asset.asset_id, edit=item.id),
            )
        elif days_until_service < 0:
            add_notification(
                level="urgent",
                title="Assigned maintenance overdue",
                message=f"Your scheduled maintenance for {item.asset.name} was due on {item.scheduled_date:%b %d, %Y}.",
                asset_label=item.asset.asset_id,
                target_date=item.scheduled_date,
                priority=0,
                sort_date=item.scheduled_date,
                action_required="Review the delayed task, contact the department if the schedule needs to change, and update the maintenance record right away.",
                context_note=item.description,
                action_target=maintenance_workspace_url,
                action_label="Open Workspace Tools",
                action_url=build_workspace_action_url(maintenance_workspace_url, search=item.asset.asset_id, edit=item.id),
            )
        elif days_until_service == 0:
            add_notification(
                level="warning",
                title="Assigned maintenance today",
                message=f"You are scheduled to perform {maintenance_type_label} maintenance for {item.asset.name} today.",
                asset_label=item.asset.asset_id,
                target_date=item.scheduled_date,
                priority=1,
                sort_date=item.scheduled_date,
                action_required="Open the maintenance workspace, inspect the asset today, and update the record after the work starts or finishes.",
                context_note=item.description,
                action_target=maintenance_workspace_url,
                action_label="Open Workspace Tools",
                action_url=build_workspace_action_url(maintenance_workspace_url, search=item.asset.asset_id, edit=item.id),
            )
        elif days_until_service <= 7:
            add_notification(
                level="info",
                title="Assigned maintenance soon",
                message=f"You are scheduled to perform {maintenance_type_label} maintenance for {item.asset.name} on {item.scheduled_date:%b %d, %Y}.",
                asset_label=item.asset.asset_id,
                target_date=item.scheduled_date,
                priority=2,
                sort_date=item.scheduled_date,
                action_required="Review the task in advance, prepare any tools or parts you need, and update the record when work begins.",
                context_note=item.description,
                action_target=maintenance_workspace_url,
                action_label="Open Workspace Tools",
                action_url=build_workspace_action_url(maintenance_workspace_url, search=item.asset.asset_id, edit=item.id),
            )

    notifications.sort(key=lambda item: (item["priority"], item["sort_date"], item["title"], item["asset_label"]))
    notifications = notifications[:limit]
    for notification in notifications:
        if "notification=" not in notification["action_url"]:
            action_url, fragment = notification["action_url"], ""
            if "#" in action_url:
                action_url, fragment = action_url.split("#", 1)
                fragment = f"#{fragment}"
            separator = "&" if "?" in action_url else "?"
            notification["action_url"] = f'{action_url}{separator}notification={notification["id"]}{fragment}'
        if not notification.get("action_required"):
            notification["action_required"] = fallback_action_required(
                notification.get("action_label", ""),
                notification.get("action_target", "#personal-overview"),
            )
        notification.pop("priority", None)
        notification.pop("sort_date", None)
    return notifications
