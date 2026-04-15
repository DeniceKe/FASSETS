from django.utils.dateparse import parse_date

from allocations.models import REQUEST_STATUS
from assets.models import CONDITION_CHOICES, STATUS_CHOICES
from maintenance.models import MAINTENANCE_STATUS

IGNORED_ACTIVITY_STATUS_FILTERS = {"available": ("request_status", "maintenance_status")}


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
    report_filter_notice = ""
    if filters.get("ignore_related_activity_status_filters"):
        report_filter_notice = "Available assets ignore request and maintenance status filters."

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
        "report_filter_notice": report_filter_notice,
        "ignore_related_activity_status_filters": filters.get("ignore_related_activity_status_filters", False),
    }
