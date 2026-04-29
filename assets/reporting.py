import datetime

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.utils.dateparse import parse_date

from allocations.models import REQUEST_STATUS
from assets.models import CONDITION_CHOICES, STATUS_CHOICES
from maintenance.models import MAINTENANCE_STATUS

IGNORED_ACTIVITY_STATUS_FILTERS = {"available": ("request_status", "maintenance_status")}

REPORT_SECTION_DETAILS = {
    "inventory-report": {
        "title": "Inventory Report",
        "heading": "Assets matching the current query",
    },
    "dashboard-summary": {
        "title": "Dashboard Summary",
        "heading": "Overall asset posture",
    },
    "assets-by-department": {
        "title": "Assets By Department",
        "heading": "Department distribution",
    },
    "assigned-assets": {
        "title": "Assigned Assets",
        "heading": "Currently issued assets",
    },
    "returned-assets": {
        "title": "Returned Assets",
        "heading": "Assets already checked back in",
    },
    "maintenance-history": {
        "title": "Maintenance History",
        "heading": "Maintenance records",
    },
    "asset-movements": {
        "title": "Asset Movements",
        "heading": "Location movement history",
    },
    "depreciation-summary": {
        "title": "Depreciation Summary",
        "heading": "Depreciation totals and latest records",
    },
    "request-report": {
        "title": "Request Report",
        "heading": "Asset requests and decisions",
    },
}


def _choice_options(choices):
    return [{"value": value, "label": label} for value, label in choices]


def _resolve_choice_label(value, choices, fallback):
    if not value:
        return fallback
    mapping = dict(choices)
    return mapping.get(value, str(value).replace("_", " ").title())


def _format_filter_date(value, parsed_value, fallback):
    if parsed_value:
        return parsed_value.strftime("%b %d, %Y")
    return value or fallback


def normalize_report_filters(params):
    filters = {
        "date_from": params.get("date_from", "").strip(),
        "date_to": params.get("date_to", "").strip(),
        "inventory_status": params.get("inventory_status", "").strip(),
        "asset_condition": params.get("asset_condition", "").strip(),
        "inventory_category": params.get("asset_category", params.get("inventory_category", "")).strip(),
        "request_status": params.get("request_status", "").strip(),
        "maintenance_status": params.get("maintenance_status", "").strip(),
    }

    date_from_parsed = parse_date(filters["date_from"]) if filters["date_from"] else None
    date_to_parsed = parse_date(filters["date_to"]) if filters["date_to"] else None

    if date_from_parsed and date_to_parsed and date_from_parsed > date_to_parsed:
        filters["date_from"], filters["date_to"] = filters["date_to"], filters["date_from"]
        date_from_parsed, date_to_parsed = date_to_parsed, date_from_parsed

    ignored_filter_keys = []
    for filter_key in IGNORED_ACTIVITY_STATUS_FILTERS.get(filters["inventory_status"], ()):
        if filters[filter_key]:
            ignored_filter_keys.append(filter_key)
            filters[filter_key] = ""

    filters["date_from_parsed"] = date_from_parsed
    filters["date_to_parsed"] = date_to_parsed
    filters["ignored_filter_keys"] = ignored_filter_keys
    filters["ignore_related_activity_status_filters"] = filters["inventory_status"] == "available"
    return filters


def apply_report_filters(
    *,
    filters,
    inventory_qs,
    requests_qs,
    maintenance_qs,
    assigned_qs,
    returned_qs,
    movement_qs,
    depreciation_qs,
):
    def filter_queryset(queryset, *args, **kwargs):
        if queryset is None:
            return None
        return queryset.filter(*args, **kwargs)

    inventory_status = filters["inventory_status"]
    asset_condition = filters["asset_condition"]
    inventory_category = filters["inventory_category"]
    request_status = filters["request_status"]
    maintenance_status = filters["maintenance_status"]
    date_from = filters["date_from_parsed"]
    date_to = filters["date_to_parsed"]
    ignore_related_activity_status_filters = (
        filters.get("ignore_related_activity_status_filters") or inventory_status == "available"
    )

    if inventory_status:
        inventory_qs = inventory_qs.filter(status=inventory_status)

    if asset_condition:
        inventory_qs = inventory_qs.filter(condition=asset_condition)
        requests_qs = filter_queryset(requests_qs, asset__condition=asset_condition)
        maintenance_qs = filter_queryset(maintenance_qs, asset__condition=asset_condition)
        assigned_qs = filter_queryset(assigned_qs, asset__condition=asset_condition)
        returned_qs = filter_queryset(returned_qs, asset__condition=asset_condition)
        movement_qs = filter_queryset(movement_qs, asset__condition=asset_condition)
        depreciation_qs = filter_queryset(depreciation_qs, asset__condition=asset_condition)

    if inventory_category:
        inventory_qs = inventory_qs.filter(category_id=inventory_category)
        requests_qs = filter_queryset(requests_qs, asset__category_id=inventory_category)
        maintenance_qs = filter_queryset(maintenance_qs, asset__category_id=inventory_category)
        assigned_qs = filter_queryset(assigned_qs, asset__category_id=inventory_category)
        returned_qs = filter_queryset(returned_qs, asset__category_id=inventory_category)
        movement_qs = filter_queryset(movement_qs, asset__category_id=inventory_category)
        depreciation_qs = filter_queryset(depreciation_qs, asset__category_id=inventory_category)

    if request_status and not ignore_related_activity_status_filters:
        requests_qs = filter_queryset(requests_qs, status=request_status)

    if maintenance_status and not ignore_related_activity_status_filters:
        maintenance_qs = filter_queryset(maintenance_qs, status=maintenance_status)

    if date_from:
        requests_qs = filter_queryset(requests_qs, requested_at__date__gte=date_from)
        maintenance_qs = filter_queryset(maintenance_qs, scheduled_date__gte=date_from)
        assigned_qs = filter_queryset(assigned_qs, allocation_date__gte=date_from)
        returned_qs = filter_queryset(returned_qs, actual_return_date__gte=date_from)
        movement_qs = filter_queryset(movement_qs, moved_at__date__gte=date_from)
        depreciation_qs = filter_queryset(depreciation_qs, created_at__date__gte=date_from)

    if date_to:
        requests_qs = filter_queryset(requests_qs, requested_at__date__lte=date_to)
        maintenance_qs = filter_queryset(maintenance_qs, scheduled_date__lte=date_to)
        assigned_qs = filter_queryset(assigned_qs, allocation_date__lte=date_to)
        returned_qs = filter_queryset(returned_qs, actual_return_date__lte=date_to)
        movement_qs = filter_queryset(movement_qs, moved_at__date__lte=date_to)
        depreciation_qs = filter_queryset(depreciation_qs, created_at__date__lte=date_to)

    return {
        "inventory_qs": inventory_qs,
        "requests_qs": requests_qs,
        "maintenance_qs": maintenance_qs,
        "assigned_qs": assigned_qs,
        "returned_qs": returned_qs,
        "movement_qs": movement_qs,
        "depreciation_qs": depreciation_qs,
    }


def build_report_filter_context(filters, selected_category=None):
    report_filters = [
        {
            "label": "Date From",
            "value": _format_filter_date(filters["date_from"], filters["date_from_parsed"], "Any start date"),
        },
        {
            "label": "Date To",
            "value": _format_filter_date(filters["date_to"], filters["date_to_parsed"], "Any end date"),
        },
        {
            "label": "Asset Status",
            "value": _resolve_choice_label(filters["inventory_status"], STATUS_CHOICES, "All asset status"),
        },
        {
            "label": "Asset Condition",
            "value": _resolve_choice_label(filters["asset_condition"], CONDITION_CHOICES, "All asset conditions"),
        },
        {
            "label": "Asset Category",
            "value": selected_category.name if selected_category else "All asset categories",
        },
        {
            "label": "Request Status",
            "value": _resolve_choice_label(filters["request_status"], REQUEST_STATUS, "All request status"),
        },
        {
            "label": "Maintenance Status",
            "value": _resolve_choice_label(filters["maintenance_status"], MAINTENANCE_STATUS, "All maintenance status"),
        },
    ]

    active_items = [
        f"{item['label']}: {item['value']}"
        for item in report_filters
        if not item["value"].lower().startswith("all ") and not item["value"].lower().startswith("any ")
    ]

    return {
        "report_filters": report_filters,
        "report_active_filters_text": " | ".join(active_items) if active_items else "No filters applied. Full report scope.",
        "asset_status_options": _choice_options(STATUS_CHOICES),
        "asset_condition_options": _choice_options(CONDITION_CHOICES),
        "request_status_options": _choice_options(REQUEST_STATUS),
        "maintenance_status_options": _choice_options(MAINTENANCE_STATUS),
    }


def resolve_report_section(section_id):
    return section_id if section_id in REPORT_SECTION_DETAILS else "inventory-report"


def _chart_rows(rows, *, label_key, value_key, empty_label):
    data = list(rows)
    max_value = max((item[value_key] for item in data), default=0)

    if not data:
        return [
            {
                "label": empty_label,
                "value": 0,
                "percentage": 0,
                "color": "#94a3b8",
            }
        ]

    color_palette = [
        "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"
    ]

    chart_rows = []
    for i, item in enumerate(data):
        value = item[value_key]
        chart_rows.append(
            {
                "label": item[label_key],
                "value": value,
                "percentage": int(round((value / max_value) * 100)) if max_value else 0,
                "color": color_palette[i % len(color_palette)],
            }
        )
    return chart_rows


def _recent_month_starts(months):
    today = timezone.localdate()
    current = today.replace(day=1)
    results = []
    for _ in range(months):
        results.append(current)
        previous_month_last_day = current - datetime.timedelta(days=1)
        current = previous_month_last_day.replace(day=1)
    return list(reversed(results))


def build_dashboard_chart_context(*, assets_qs, allocations_qs, maintenance_qs):
    status_counts = [
        {"label": "Available", "value": assets_qs.filter(status="available").count(), "color": "#10b981"},
        {"label": "Allocated", "value": assets_qs.filter(status="allocated").count(), "color": "#3b82f6"},
        {"label": "Maintenance", "value": assets_qs.filter(status="maintenance").count(), "color": "#f59e0b"},
        {"label": "Disposed", "value": assets_qs.filter(status="disposed").count(), "color": "#ef4444"},
    ]
    total_assets = sum(item["value"] for item in status_counts)
    status_chart = []
    for item in status_counts:
        status_chart.append(
            {
                **item,
                "share": int(round((item["value"] / total_assets) * 100)) if total_assets else 0,
                "percentage": int(round((item["value"] / total_assets) * 100)) if total_assets else 0,
            }
        )

    # Color palette for categories and departments
    color_palette = [
        "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"
    ]

    category_chart = _chart_rows(
        assets_qs.values("category__name")
        .annotate(total=Count("id"))
        .order_by("-total", "category__name")[:6],
        label_key="category__name",
        value_key="total",
        empty_label="No categories yet",
    )

    department_chart = _chart_rows(
        assets_qs.values("current_location__department__name")
        .annotate(total=Count("id"))
        .order_by("-total", "current_location__department__name")[:6],
        label_key="current_location__department__name",
        value_key="total",
        empty_label="No departments yet",
    )

    month_starts = _recent_month_starts(6)
    month_lookup = {month_start: index for index, month_start in enumerate(month_starts)}
    allocation_counts = [0] * len(month_starts)
    maintenance_counts = [0] * len(month_starts)

    allocation_rows = (
        allocations_qs.annotate(month=TruncMonth("allocation_date"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )
    for row in allocation_rows:
        month_value = row["month"]
        if month_value:
            month_start = (month_value.date() if hasattr(month_value, "date") else month_value).replace(day=1)
            if month_start in month_lookup:
                allocation_counts[month_lookup[month_start]] = row["total"]

    maintenance_rows = (
        maintenance_qs.annotate(month=TruncMonth("scheduled_date"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )
    for row in maintenance_rows:
        month_value = row["month"]
        if month_value:
            month_start = (month_value.date() if hasattr(month_value, "date") else month_value).replace(day=1)
            if month_start in month_lookup:
                maintenance_counts[month_lookup[month_start]] = row["total"]

    activity_peak = max(allocation_counts + maintenance_counts, default=0)
    activity_chart = []
    for index, month_start in enumerate(month_starts):
        allocation_total = allocation_counts[index]
        maintenance_total = maintenance_counts[index]
        activity_chart.append(
            {
                "label": month_start.strftime("%b %Y"),
                "allocation_count": allocation_total,
                "maintenance_count": maintenance_total,
                "allocation_height": int(round((allocation_total / activity_peak) * 100)) if activity_peak else 0,
                "maintenance_height": int(round((maintenance_total / activity_peak) * 100)) if activity_peak else 0,
            }
        )

    return {
        "dashboard_status_chart": status_chart,
        "dashboard_category_chart": category_chart,
        "dashboard_department_chart": department_chart,
        "dashboard_activity_chart": activity_chart,
        "dashboard_chart_total_assets": total_assets,
    }
