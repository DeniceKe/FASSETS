from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.urls import reverse

from FAssets.admin_site import RESOURCE_CONFIGS
from accounts.audit import log_audit_event
from accounts.models import (
    ROLE_ADMIN,
    ROLE_COD,
    ROLE_DEAN,
    ROLE_INTERNAL_AUDITOR,
    ROLE_LAB_TECHNICIAN,
    ROLE_LECTURER,
)
from .models import Asset, AssetMovement, Category, DepreciationRecord
from allocations.models import Allocation, AssetRequest
from maintenance.models import Maintenance
from accounts.roles import get_role_label, infer_user_role
from django.utils import timezone
from .notifications import build_user_notifications
from .reporting import apply_report_filters, build_report_filter_context, normalize_report_filters

from .forms import AssetIssueReportForm, AssetRequestForm


def _user_can_request_assets(user, role=None):
    return (role or infer_user_role(user)) not in {ROLE_ADMIN, ROLE_INTERNAL_AUDITOR}


def _user_can_browse_department_assets_without_search(user, role=None):
    resolved_role = role or infer_user_role(user)
    return user.is_superuser or resolved_role in {ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_INTERNAL_AUDITOR, ROLE_LAB_TECHNICIAN}


def _user_can_manage_user_asset_lookup(user, role=None):
    resolved_role = role or infer_user_role(user)
    return user.is_superuser or resolved_role in {ROLE_ADMIN, ROLE_COD}


def _build_asset_search_filter(search_term):
    search_term = (search_term or "").strip()
    if not search_term:
        return Q()

    return (
        Q(asset_id__icontains=search_term)
        | Q(name__icontains=search_term)
        | Q(barcode__icontains=search_term)
        | Q(serial_number__icontains=search_term)
        | Q(description__icontains=search_term)
        | Q(category__name__icontains=search_term)
        | Q(current_location__building__icontains=search_term)
        | Q(current_location__room__icontains=search_term)
        | Q(current_location__department__name__icontains=search_term)
        | Q(current_location__department__code__icontains=search_term)
    )


def _build_user_asset_lookup_context(search_term):
    User = get_user_model()
    search_term = (search_term or "").strip()
    if not search_term:
        return {
            "query": "",
            "results": [],
            "searched": False,
        }

    matched_users = list(
        User.objects.select_related("profile", "profile__department")
        .filter(
            Q(username__icontains=search_term)
            | Q(first_name__icontains=search_term)
            | Q(last_name__icontains=search_term)
            | Q(email__icontains=search_term)
            | Q(profile__employee_id__icontains=search_term)
            | Q(profile__registration_number__icontains=search_term)
            | Q(profile__department__name__icontains=search_term)
            | Q(profile__department__code__icontains=search_term)
        )
        .distinct()
        .order_by("username")[:12]
    )

    allocations_by_user_id = {}
    if matched_users:
        active_allocations = (
            Allocation.objects.select_related(
                "asset",
                "asset__category",
                "asset__current_location",
                "asset__current_location__department",
            )
            .filter(
                allocated_to__in=matched_users,
                status__in=["active", "overdue"],
            )
            .order_by("asset__asset_id", "asset__name")
        )

        for allocation in active_allocations:
            allocations_by_user_id.setdefault(allocation.allocated_to_id, []).append(allocation)

    results = []
    for user in matched_users:
        profile = getattr(user, "profile", None)
        allocations = allocations_by_user_id.get(user.id, [])
        results.append(
            {
                "user": user,
                "display_name": user.get_full_name().strip() or user.username,
                "department_name": getattr(getattr(profile, "department", None), "name", "") or "No department assigned",
                "role_label": (getattr(profile, "get_role_display", lambda: "")() or getattr(profile, "role", "") or "No role assigned"),
                "identity_label": getattr(profile, "employee_id", "") or getattr(profile, "registration_number", "") or "No staff/student ID",
                "allocations": allocations,
                "allocation_count": len(allocations),
            }
        )

    return {
        "query": search_term,
        "results": results,
        "searched": True,
    }


WORKSPACE_RESOURCE_ORDER = [
    "assets",
    "allocations",
    "maintenance",
    "users",
    "categories",
    "suppliers",
    "locations",
    "departments",
    "faculties",
]

WORKSPACE_ACCESS_BY_ROLE = {
    ROLE_ADMIN: {"assets", "allocations", "maintenance", "users", "categories", "suppliers", "locations", "departments", "faculties"},
    ROLE_COD: {"assets", "allocations", "maintenance", "users", "categories", "suppliers", "locations"},
    ROLE_INTERNAL_AUDITOR: {"assets", "allocations", "maintenance", "users", "categories", "suppliers", "locations", "departments", "faculties"},
    ROLE_LAB_TECHNICIAN: {"assets", "allocations", "maintenance"},
}

WORKSPACE_ACTIONS = {
    "faculties": {
        "create": {ROLE_ADMIN},
        "edit": {ROLE_ADMIN},
        "delete": {ROLE_ADMIN},
    },
    "departments": {
        "create": {ROLE_ADMIN},
        "edit": {ROLE_ADMIN},
        "delete": {ROLE_ADMIN},
    },
    "categories": {
        "create": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "edit": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "delete": {ROLE_ADMIN},
    },
    "suppliers": {
        "create": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "edit": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "delete": {ROLE_ADMIN},
    },
    "locations": {
        "create": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "edit": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "delete": {ROLE_ADMIN},
    },
    "assets": {
        "create": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "edit": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "delete": {ROLE_ADMIN},
    },
    "users": {
        "create": {ROLE_ADMIN, ROLE_COD},
        "edit": {ROLE_ADMIN, ROLE_COD},
        "delete": {ROLE_ADMIN},
    },
    "allocations": {
        "create": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "edit": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "delete": set(),
    },
    "maintenance": {
        "create": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER},
        "edit": {ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN},
        "delete": set(),
    },
}

WORKSPACE_DESCRIPTIONS = {
    "assets": "Review and manage department assets visible to your assigned role.",
    "allocations": "Track issued assets and manage allocation activity within your allowed scope.",
    "maintenance": "Log, review, and follow maintenance work from your account workspace.",
    "users": "Manage department users and their assigned roles from the account workspace.",
    "categories": "Maintain the asset category structure available to your department operations.",
    "suppliers": "Review and update supplier records used for inventory registration.",
    "locations": "Manage rooms and handover locations used for asset tracking.",
    "departments": "Browse departmental structure and assignment information.",
    "faculties": "Browse faculty records and oversight structure.",
}

ROLE_WORKSPACE_DESCRIPTION_OVERRIDES = {
    ROLE_LAB_TECHNICIAN: {
        "assets": "View and manage assets assigned to your labs, including status, condition, and availability.",
        "allocations": "Check assets in and out for lab use and keep issue activity current.",
        "maintenance": "Request repairs and report damaged, missing, or malfunctioning lab equipment.",
    }
}


def _workspace_permissions_for(resource, user_role, is_superuser=False):
    actions = WORKSPACE_ACTIONS.get(resource, {})
    if is_superuser:
        return {
            "can_create": True,
            "can_edit": True,
            "can_delete": True,
        }

    return {
        "can_create": user_role in actions.get("create", set()),
        "can_edit": user_role in actions.get("edit", set()),
        "can_delete": user_role in actions.get("delete", set()),
    }


def _workspace_links_for(request, user_role):
    if request.user.is_superuser:
        allowed_resources = set(WORKSPACE_RESOURCE_ORDER)
    else:
        allowed_resources = WORKSPACE_ACCESS_BY_ROLE.get(user_role, set())

    links = []
    for resource in WORKSPACE_RESOURCE_ORDER:
        if resource not in allowed_resources:
            continue

        resource_config = RESOURCE_CONFIGS[resource]
        permissions = _workspace_permissions_for(resource, user_role, request.user.is_superuser)

        if permissions["can_edit"]:
            action_label = "Manage"
        elif permissions["can_create"]:
            action_label = "Open"
        else:
            action_label = "Browse"

        links.append(
            {
                "resource": resource,
                "label": resource_config["title"],
                "description": ROLE_WORKSPACE_DESCRIPTION_OVERRIDES.get(user_role, {}).get(
                    resource,
                    WORKSPACE_DESCRIPTIONS.get(resource, f"Open the {resource_config['singular'].lower()} workspace."),
                ),
                "action_label": action_label,
                "url": reverse("assets:workspace_resource", kwargs={"resource": resource}),
                "permissions": permissions,
            }
        )

    return links


def _user_can_view_reports(user, role=None):
    resolved_role = role or infer_user_role(user)
    return user.is_superuser or resolved_role in {ROLE_ADMIN, ROLE_COD, ROLE_INTERNAL_AUDITOR}


def _report_links_for(request, user_role):
    if not _user_can_view_reports(request.user, user_role):
        return []

    reports_center_url = reverse("assets:reports_center")
    links = [
        {
            "label": "Inventory Report",
            "description": "Print the asset list returned by the current report query.",
            "action_label": "Open Section",
            "url": f"{reports_center_url}#inventory-report",
        },
        {
            "label": "Dashboard Summary",
            "description": "Open overall asset, allocation, and maintenance totals.",
            "action_label": "Open Section",
            "url": f"{reports_center_url}#dashboard-summary",
        },
        {
            "label": "Assets By Department",
            "description": "Review asset totals grouped across departments.",
            "action_label": "Open Section",
            "url": f"{reports_center_url}#assets-by-department",
        },
        {
            "label": "Maintenance History",
            "description": "Inspect maintenance activity and servicing records.",
            "action_label": "Open Section",
            "url": f"{reports_center_url}#maintenance-history",
        },
        {
            "label": "Assigned Assets",
            "description": "Track assets currently assigned across the system.",
            "action_label": "Open Section",
            "url": f"{reports_center_url}#assigned-assets",
        },
        {
            "label": "Returned Assets",
            "description": "Review assets that have already been checked back in.",
            "action_label": "Open Section",
            "url": f"{reports_center_url}#returned-assets",
        },
        {
            "label": "Asset Movements",
            "description": "Follow asset movement history between locations.",
            "action_label": "Open Section",
            "url": f"{reports_center_url}#asset-movements",
        },
        {
            "label": "Depreciation Summary",
            "description": "Review depreciation and net book value records.",
            "action_label": "Open Section",
            "url": f"{reports_center_url}#depreciation-summary",
        },
    ]

    links.insert(
        0,
        {
            "label": "Reports Center",
            "description": "Open the full reports center with readable dashboard sections.",
            "action_label": "Open Center",
            "url": reports_center_url,
        },
    )

    return links


def _build_reports_center_context(request):
    role = infer_user_role(request.user)
    if not _user_can_view_reports(request.user, role):
        raise Http404("Reports are not available for this account.")

    profile = getattr(request.user, "profile", None)
    department = getattr(profile, "department", None)
    categories = Category.objects.all().order_by("name")
    filters = normalize_report_filters(request.GET)
    inventory_assets = Asset.objects.select_related(
        "category",
        "supplier",
        "current_location",
        "current_location__department",
    ).order_by("asset_id")
    asset_requests_queryset = AssetRequest.objects.select_related(
        "asset",
        "requested_by",
        "reviewed_by",
    ).order_by("-requested_at")
    maintenance_queryset = Maintenance.objects.select_related(
        "asset",
        "technician",
        "reported_by",
    ).order_by("-scheduled_date", "-created_at")
    assigned_assets_queryset = Allocation.objects.select_related(
        "asset",
        "allocated_to",
        "allocated_to__profile",
        "allocated_to_lab",
        "allocated_by",
    ).filter(status__in=["active", "overdue"]).order_by("-allocation_date")
    returned_assets_queryset = Allocation.objects.select_related(
        "asset",
        "allocated_to",
        "allocated_to__profile",
        "allocated_to__profile__department",
        "allocated_to_lab",
        "allocated_by",
    ).filter(status="returned").order_by("-actual_return_date", "-allocation_date")
    movement_queryset = AssetMovement.objects.select_related(
        "asset",
        "from_location",
        "from_location__department",
        "to_location",
        "to_location__department",
        "moved_by",
    ).order_by("-moved_at")
    depreciation_queryset = DepreciationRecord.objects.select_related(
        "asset",
        "asset__current_location",
        "asset__current_location__department",
    ).order_by("-year", "asset__asset_id")

    if not request.user.is_superuser and role == ROLE_COD:
        if department:
            inventory_assets = inventory_assets.filter(current_location__department=department)
            asset_requests_queryset = asset_requests_queryset.filter(asset__current_location__department=department)
            maintenance_queryset = maintenance_queryset.filter(asset__current_location__department=department)
            assigned_assets_queryset = assigned_assets_queryset.filter(asset__current_location__department=department)
            returned_assets_queryset = returned_assets_queryset.filter(asset__current_location__department=department)
            movement_queryset = movement_queryset.filter(
                Q(from_location__department=department)
                | Q(to_location__department=department)
                | Q(asset__current_location__department=department)
            ).distinct()
            depreciation_queryset = depreciation_queryset.filter(asset__current_location__department=department)
        else:
            inventory_assets = inventory_assets.none()
            asset_requests_queryset = asset_requests_queryset.none()
            maintenance_queryset = maintenance_queryset.none()
            assigned_assets_queryset = assigned_assets_queryset.none()
            returned_assets_queryset = returned_assets_queryset.none()
            movement_queryset = movement_queryset.none()
            depreciation_queryset = depreciation_queryset.none()

    filtered_querysets = apply_report_filters(
        filters=filters,
        inventory_qs=inventory_assets,
        requests_qs=asset_requests_queryset,
        maintenance_qs=maintenance_queryset,
        assigned_qs=assigned_assets_queryset,
        returned_qs=returned_assets_queryset,
        movement_qs=movement_queryset,
        depreciation_qs=depreciation_queryset,
    )
    inventory_assets = filtered_querysets["inventory_qs"]
    asset_requests_queryset = filtered_querysets["requests_qs"]
    maintenance_queryset = filtered_querysets["maintenance_qs"]
    assigned_assets_queryset = filtered_querysets["assigned_qs"]
    returned_assets_queryset = filtered_querysets["returned_qs"]
    movement_queryset = filtered_querysets["movement_qs"]
    depreciation_queryset = filtered_querysets["depreciation_qs"]
    depreciation_totals = depreciation_queryset.aggregate(
        total_depreciation=Sum("depreciation_amount"),
        total_accumulated=Sum("accumulated_depreciation"),
        total_book_value=Sum("net_book_value"),
    )
    assets_by_department = (
        inventory_assets.values("current_location__department__code", "current_location__department__name")
        .annotate(total_assets=Count("id"))
        .order_by("current_location__department__name")
    )
    generated_by = request.user.get_full_name() or request.user.get_username() or "System"
    generated_at = timezone.localtime()
    resolved_role = get_role_label(role, default="Unassigned")
    selected_category = categories.filter(pk=filters["inventory_category"]).first() if filters["inventory_category"] else None
    filter_context = build_report_filter_context(filters, selected_category=selected_category)

    return {
        "report_summary": {
            "total_assets": inventory_assets.count(),
            "available_assets": inventory_assets.filter(status="available").count(),
            "allocated_assets": inventory_assets.filter(status="allocated").count(),
            "maintenance_assets": inventory_assets.filter(status="maintenance").count(),
            "disposed_assets": inventory_assets.filter(status="disposed").count(),
            "active_allocations": assigned_assets_queryset.count(),
            "returned_allocations": returned_assets_queryset.count(),
        },
        "inventory_assets": inventory_assets[:100],
        "assets_by_department": assets_by_department,
        "asset_requests_report": asset_requests_queryset[:100],
        "maintenance_report": maintenance_queryset[:100],
        "assigned_assets_report": assigned_assets_queryset[:100],
        "returned_assets_report": returned_assets_queryset[:100],
        "movement_report": movement_queryset[:100],
        "depreciation_totals": depreciation_totals,
        "depreciation_records": depreciation_queryset[:50],
        "user_role": resolved_role,
        "report_generated_by": generated_by,
        "report_generated_at": generated_at,
        "categories": categories,
        "date_from": filters["date_from"],
        "date_to": filters["date_to"],
        "inventory_status": filters["inventory_status"],
        "asset_condition": filters["asset_condition"],
        "inventory_category": filters["inventory_category"],
        "request_status": filters["request_status"],
        "maintenance_status": filters["maintenance_status"],
        **filter_context,
    }


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


def _resolve_report_section(section_id):
    return section_id if section_id in REPORT_SECTION_DETAILS else "inventory-report"


HELP_CENTER_TOPICS = [
    {
        "slug": "sign-in-and-access",
        "category": "Getting Started",
        "title": "Sign in and open the right workspace",
        "summary": "Use your account to reach the dashboard, confirm your role, and work from the pages meant for your responsibilities.",
        "audience": "All users",
        "keywords": ["login", "sign in", "access", "dashboard", "account", "role"],
        "steps": [
            "Use your username, staff ID, or student ID with your password.",
            "Open the dashboard after sign-in and confirm your visible sections match your role.",
            "Use profile details if you need to verify department or identity information.",
        ],
    },
    {
        "slug": "find-assets",
        "category": "Borrowing",
        "title": "Find available assets in your department",
        "summary": "Search the Department Assets area using familiar details like asset ID, name, category, barcode, or location.",
        "audience": "Borrowing accounts",
        "keywords": ["find assets", "search", "department assets", "barcode", "location", "category"],
        "steps": [
            "Open Department Assets from the dashboard navigation.",
            "Search using the asset name, asset ID, category, barcode, or location.",
            "Review the results and choose an available item before taking the next action.",
        ],
    },
    {
        "slug": "request-assets",
        "category": "Borrowing",
        "title": "Request an asset correctly",
        "summary": "Complete the reason, time period, and place of use so the request can be reviewed without back-and-forth clarification.",
        "audience": "Borrowing accounts",
        "keywords": ["request asset", "borrow", "dates", "usage location", "reason", "approval"],
        "steps": [
            "Search for the asset from Department Assets.",
            "Enter the reason for use, the requested dates, and the place of use.",
            "Submit the request and return to My Assets to follow approval progress.",
        ],
    },
    {
        "slug": "return-assets",
        "category": "Borrowing",
        "title": "Return an asset correctly",
        "summary": "Bring the asset back through your department handover point, allow condition checking, and let the office record the return in the system.",
        "audience": "Users with assigned assets",
        "keywords": ["return asset", "handover", "return date", "returned", "check in", "department office"],
        "steps": [
            "Open My Assets and check the return date or return status shown for the item.",
            "Bring the asset to your department office or the agreed handover point by the due date, together with any issued accessories.",
            "Allow the receiving staff member to inspect the condition and mark the allocation as returned in the system.",
        ],
    },
    {
        "slug": "notifications",
        "category": "Follow-Up",
        "title": "Use notifications to know what to do next",
        "summary": "Open the notification bell to see reminders, the required action, more context, and the correct dashboard destination.",
        "audience": "All signed-in users",
        "keywords": ["notifications", "reminders", "what to do", "returns", "maintenance", "next step"],
        "steps": [
            "Open the notification bell from the top bar.",
            "Select a reminder to read the full details and the next required action.",
            "Use the action button to jump back to the relevant dashboard section.",
        ],
    },
    {
        "slug": "report-maintenance",
        "category": "Maintenance",
        "title": "Report an issue or maintenance need",
        "summary": "Use the assets under your care section to report faults, damage, missing parts, or planned maintenance needs.",
        "audience": "Users with assigned assets",
        "keywords": ["maintenance", "report issue", "fault", "repair", "damage", "service"],
        "steps": [
            "Open My Assets and find the item under your care.",
            "Describe the problem clearly so the technician or reviewer knows what needs attention.",
            "Check notifications and dashboard updates for scheduled follow-up or technician assignment.",
        ],
    },
    {
        "slug": "user-asset-lookup",
        "category": "Oversight",
        "title": "Search a user and review assigned assets",
        "summary": "Admins and CoDs can search a person and review all active or overdue assets currently assigned to that account.",
        "audience": "Admins and CoDs",
        "keywords": ["user assets", "search user", "assigned assets", "admin", "cod", "lookup"],
        "steps": [
            "Open User Assets from the dashboard navigation.",
            "Search by username, name, email, employee ID, student ID, or department.",
            "Review the assignments or launch Allocate Asset for the selected person.",
        ],
    },
    {
        "slug": "workspace-tools",
        "category": "Operations",
        "title": "Use workspace tools for record management",
        "summary": "Role-based workspace tools support asset, allocation, maintenance, location, and user record management from one operational area.",
        "audience": "Operational roles",
        "keywords": ["workspace", "manage records", "allocations", "assets", "maintenance", "quick help"],
        "steps": [
            "Open Workspace Tools from the dashboard.",
            "Choose the resource you need to manage, then search or start a new record.",
            "Use Quick help, required-field markers, and restore options to finish the task safely.",
        ],
    },
    {
        "slug": "reports-center",
        "category": "Oversight",
        "title": "Open the reports center for oversight review",
        "summary": "Administrator and auditor accounts can review readable system reports for asset distribution, maintenance history, movements, and issued assets.",
        "audience": "Administrators and auditors",
        "keywords": ["reports", "oversight", "audit", "assigned assets", "maintenance history", "depreciation"],
        "steps": [
            "Open Reports from the dashboard if your role has access.",
            "Choose the full reports center or jump to a specific section.",
            "Use the report sections to review trends, accountability, and operational follow-up.",
        ],
    },
]


def _help_topic_match_score(topic, query):
    if not query:
        return 1

    haystack = " ".join(
        [
            topic["title"],
            topic["summary"],
            topic["category"],
            topic["audience"],
            " ".join(topic.get("keywords", [])),
        ]
    ).lower()
    query_terms = [term for term in query.lower().split() if term]
    if not query_terms or not all(term in haystack for term in query_terms):
        return 0

    score = 0
    for term in query_terms:
        if term in topic["title"].lower():
            score += 3
        elif term in topic["summary"].lower():
            score += 2
        else:
            score += 1
    return score


def _help_center_capabilities(request, role):
    user = request.user
    is_authenticated = user.is_authenticated
    return {
        "is_authenticated": is_authenticated,
        "can_request_assets": is_authenticated and _user_can_request_assets(user, role),
        "can_view_user_asset_lookup": is_authenticated and (user.is_superuser or role in {ROLE_ADMIN, ROLE_COD}),
        "has_workspace_tools": is_authenticated and bool(_workspace_links_for(request, role)),
        "can_view_reports": is_authenticated and _user_can_view_reports(user, role),
    }


def _help_topic_is_visible(topic, capabilities):
    if not capabilities["is_authenticated"]:
        return topic["slug"] == "sign-in-and-access"

    if topic["slug"] in {"sign-in-and-access", "find-assets", "notifications", "report-maintenance"}:
        return True
    if topic["slug"] in {"request-assets", "return-assets"}:
        return capabilities["can_request_assets"]
    if topic["slug"] == "user-asset-lookup":
        return capabilities["can_view_user_asset_lookup"]
    if topic["slug"] == "workspace-tools":
        return capabilities["has_workspace_tools"]
    if topic["slug"] == "reports-center":
        return capabilities["can_view_reports"]
    return True


def _build_help_topic_card(request, topic, role, capabilities):
    user = request.user
    dashboard_url = reverse("assets:dashboard")
    login_url = reverse("login")

    action_label = "Open Help Topic"
    action_url = reverse("assets:help_center") + f"#{topic['slug']}"
    availability = "Available in your system area"

    if topic["slug"] == "sign-in-and-access":
        if capabilities["is_authenticated"]:
            action_label = "Open Dashboard"
            action_url = dashboard_url
            availability = "Available now"
        else:
            action_label = "Open Login"
            action_url = login_url
            availability = "Sign in required"
    elif topic["slug"] == "find-assets":
        if capabilities["is_authenticated"]:
            action_label = "Open Department Assets"
            action_url = f"{dashboard_url}#department-assets"
            availability = "Available now"
        else:
            action_label = "Sign In To Search"
            action_url = login_url
            availability = "Sign in required"
    elif topic["slug"] == "request-assets":
        if capabilities["can_request_assets"]:
            action_label = "Open Request Area"
            action_url = f"{dashboard_url}#department-assets"
            availability = "Available now"
        else:
            action_label = "Sign In To Request"
            action_url = login_url
            availability = "Sign in required"
    elif topic["slug"] == "return-assets":
        if capabilities["can_request_assets"]:
            action_label = "Open My Assets"
            action_url = f"{dashboard_url}#personal-overview"
            availability = "Available now"
        else:
            action_label = "Sign In To View Return Steps"
            action_url = login_url
            availability = "Sign in required"
    elif topic["slug"] == "notifications":
        if capabilities["is_authenticated"]:
            action_label = "Open Dashboard"
            action_url = dashboard_url
            availability = "Available now"
        else:
            action_label = "Sign In For Notifications"
            action_url = login_url
            availability = "Sign in required"
    elif topic["slug"] == "report-maintenance":
        if capabilities["is_authenticated"]:
            action_label = "Open My Assets"
            action_url = f"{dashboard_url}#personal-overview"
            availability = "Available now"
        else:
            action_label = "Sign In To Report"
            action_url = login_url
            availability = "Sign in required"
    elif topic["slug"] == "user-asset-lookup":
        if capabilities["can_view_user_asset_lookup"]:
            action_label = "Open User Assets"
            action_url = f"{dashboard_url}#user-asset-lookup"
            availability = "Available to your account"
        else:
            action_label = "Sign In For Oversight Tools"
            action_url = login_url
            availability = "Available to Admins and CoDs"
    elif topic["slug"] == "workspace-tools":
        if capabilities["has_workspace_tools"]:
            action_label = "Open Workspace Tools"
            action_url = f"{dashboard_url}#role-workspace"
            availability = "Available to your account"
        else:
            action_label = "Sign In For Workspace Tools"
            action_url = login_url
            availability = "Available to operational roles"
    elif topic["slug"] == "reports-center":
        if capabilities["can_view_reports"]:
            action_label = "Open Reports Center"
            action_url = reverse("assets:reports_center")
            availability = "Available to your account"
        else:
            action_label = "Sign In For Reports"
            action_url = login_url
            availability = "Available to administrators and auditors"

    return {
        **topic,
        "action_label": action_label,
        "action_url": action_url,
        "availability": availability,
    }


def _help_topic_cards_for(request, role, *, query="", limit=None):
    capabilities = _help_center_capabilities(request, role)
    topics = []
    for topic in HELP_CENTER_TOPICS:
        if not _help_topic_is_visible(topic, capabilities):
            continue
        score = _help_topic_match_score(topic, query)
        if not score:
            continue
        topics.append((score, _build_help_topic_card(request, topic, role, capabilities)))

    topics.sort(key=lambda item: (-item[0], item[1]["category"], item[1]["title"]))
    cards = [topic for _, topic in topics]
    if limit is not None:
        cards = cards[:limit]
    return cards


def _build_help_center_context(request):
    role = infer_user_role(request.user) if request.user.is_authenticated else ""
    query = request.GET.get("q", "").strip()
    topic_cards = _help_topic_cards_for(request, role, query=query)
    featured_topics = topic_cards[:3]

    return {
        "help_query": query,
        "help_topics": topic_cards,
        "help_topics_count": len(topic_cards),
        "featured_help_topics": featured_topics,
        "help_user_role": get_role_label(role, default="Guest"),
    }


def about(request):
    return render(request, "about.html")


def help_center(request):
    return render(request, "help_center.html", _build_help_center_context(request))


@login_required
def dashboard(request):
    return render(request, "dashboard.html", _build_dashboard_context(request))


@login_required
def reports_center(request):
    context = _build_reports_center_context(request)
    if request.GET.get("print") == "1":
        print_section = _resolve_report_section(request.GET.get("section", "").strip())
        context.update(
            {
                "print_section": print_section,
                "print_section_title": REPORT_SECTION_DETAILS[print_section]["title"],
                "print_section_heading": REPORT_SECTION_DETAILS[print_section]["heading"],
            }
        )
        return render(request, "reports_center_print.html", context)
    return render(request, "reports_center.html", context)


def _build_dashboard_context(
    request,
    *,
    request_form_asset_id=None,
    request_form_values_by_asset=None,
    request_form_errors_by_asset=None,
    issue_form_asset_id=None,
    issue_form_values_by_asset=None,
    issue_form_errors_by_asset=None,
    asset_search_query=None,
):
    notification_id = request.GET.get("notification", "").strip()
    focus_asset_id_param = request.GET.get("focus_asset_id", "").strip()
    try:
        notification_focus_asset_id = int(focus_asset_id_param) if focus_asset_id_param else None
    except ValueError:
        notification_focus_asset_id = None

    assets_qs = Asset.objects.select_related(
        "category",
        "current_location",
        "current_location__department",
        "supplier",
    )
    allocations_qs = Allocation.objects.select_related("asset", "allocated_to", "allocated_to_lab")
    maintenance_qs = Maintenance.objects.select_related("asset", "technician", "reported_by")

    profile = getattr(request.user, "profile", None)
    department = getattr(profile, "department", None)
    role = infer_user_role(request.user)
    can_request_assets = _user_can_request_assets(request.user, role)
    can_browse_department_assets_without_search = _user_can_browse_department_assets_without_search(request.user, role)
    show_department_category_breakdown = can_browse_department_assets_without_search
    can_view_activity_overview = request.user.is_superuser or role in {ROLE_ADMIN, ROLE_COD, ROLE_INTERNAL_AUDITOR, ROLE_LAB_TECHNICIAN}
    can_view_user_asset_lookup = _user_can_manage_user_asset_lookup(request.user, role)
    asset_workspace_permissions = _workspace_permissions_for("assets", role, request.user.is_superuser)
    role_workspace_links = _workspace_links_for(request, role)
    report_links = _report_links_for(request, role)
    can_view_reports = bool(report_links)

    if not request.user.is_superuser and role not in {ROLE_ADMIN, ROLE_DEAN, ROLE_INTERNAL_AUDITOR}:
        if department:
            assets_qs = assets_qs.filter(current_location__department=department)
            allocations_qs = allocations_qs.filter(asset__current_location__department=department)
            maintenance_qs = maintenance_qs.filter(asset__current_location__department=department)
        else:
            assets_qs = assets_qs.none()
            allocations_qs = allocations_qs.none()
            maintenance_qs = maintenance_qs.none()

    total_assets = assets_qs.count()
    available = assets_qs.filter(status="available").count()
    allocated = assets_qs.filter(status="allocated").count()
    maintenance = assets_qs.filter(status="maintenance").count()
    disposed = assets_qs.filter(status="disposed").count()
    active_allocations = allocations_qs.filter(status__in=["active", "overdue"]).count()
    asset_search = (
        asset_search_query
        if asset_search_query is not None
        else request.GET.get("asset_search", "")
    ).strip()
    category_search = request.GET.get("category_search", "").strip()
    inventory_search = request.GET.get("inventory_search", "").strip()
    activity_search = request.GET.get("activity_search", "").strip()
    user_asset_search = request.GET.get("user_asset_search", "").strip()
    dashboard_search_active = bool(asset_search)
    category_search_active = bool(category_search)
    inventory_search_active = bool(inventory_search)
    activity_search_active = bool(activity_search)
    user_asset_search_active = bool(user_asset_search) and can_view_user_asset_lookup
    asset_search_filter = _build_asset_search_filter(asset_search)
    category_search_filter = _build_asset_search_filter(category_search)
    inventory_search_filter = _build_asset_search_filter(inventory_search)
    activity_search_filter = _build_asset_search_filter(activity_search)

    searched_assets_qs = assets_qs.filter(asset_search_filter) if dashboard_search_active else assets_qs.none()
    category_assets_qs = assets_qs.filter(category_search_filter) if category_search_active else assets_qs.none()
    inventory_assets_qs = assets_qs.filter(inventory_search_filter) if inventory_search_active else assets_qs.none()
    activity_assets_qs = assets_qs.filter(activity_search_filter) if activity_search_active else assets_qs.none()
    user_asset_lookup = _build_user_asset_lookup_context(user_asset_search) if can_view_user_asset_lookup else {
        "query": "",
        "results": [],
        "searched": False,
    }
    department_category_breakdown = (
        category_assets_qs.values("category__name")
        .annotate(
            total=Count("id"),
            available_count=Count("id", filter=Q(status="available")),
            allocated_count=Count("id", filter=Q(status="allocated")),
            maintenance_count=Count("id", filter=Q(status="maintenance")),
            disposed_count=Count("id", filter=Q(status="disposed")),
        )
        .order_by("-total", "category__name")
    )
    department_distribution = (
        inventory_assets_qs.values("current_location__department__name", "current_location__department__code")
        .annotate(total=Count("id"))
        .order_by("-total", "current_location__department__name")[:6]
    )
    assets_under_care_queryset = Allocation.objects.select_related(
        "asset",
        "asset__category",
        "asset__current_location",
        "asset__current_location__department",
    ).filter(
        allocated_to=request.user,
        status__in=["active", "overdue"],
    )
    has_assets_under_care = assets_under_care_queryset.exists()
    if asset_search or request_form_asset_id:
        default_dashboard_section = "department-assets"
    elif category_search_active and show_department_category_breakdown:
        default_dashboard_section = "category-control"
    elif inventory_search_active:
        default_dashboard_section = "inventory-views"
    elif activity_search_active and can_view_activity_overview:
        default_dashboard_section = "activity-overview"
    elif user_asset_search_active:
        default_dashboard_section = "user-asset-lookup"
    elif issue_form_asset_id or has_assets_under_care:
        default_dashboard_section = "personal-overview"
    elif role == ROLE_LAB_TECHNICIAN and role_workspace_links:
        default_dashboard_section = "role-workspace"
    else:
        default_dashboard_section = "personal-overview"

    department_assets_qs = assets_qs
    if not can_browse_department_assets_without_search:
        department_assets_qs = department_assets_qs.filter(status="available")

    if asset_search:
        department_assets_qs = department_assets_qs.filter(asset_search_filter)
    elif request_form_asset_id:
        department_assets_qs = department_assets_qs.filter(pk=request_form_asset_id)
    else:
        department_assets_qs = department_assets_qs.none()

    department_assets = department_assets_qs.order_by("name")[:100]
    category_assets = category_assets_qs.order_by("category__name", "name")[:100]
    request_status_by_asset = {
        request.asset_id: request.status
        for request in AssetRequest.objects.filter(
            requested_by=request.user,
            asset__in=department_assets,
            status="pending",
        )
    }
    assets_under_care = assets_under_care_queryset.order_by("-allocation_date", "-id")[:100]
    open_maintenance_by_asset_id = {}
    open_maintenance_records = (
        Maintenance.objects.select_related("asset", "technician", "reported_by")
        .filter(
            asset_id__in=assets_under_care_queryset.values_list("asset_id", flat=True),
            status__in=["scheduled", "in_progress"],
        )
        .order_by("scheduled_date", "created_at")
    )
    for record in open_maintenance_records:
        open_maintenance_by_asset_id.setdefault(record.asset_id, record)
    assets_under_care_by_category = (
        assets_under_care_queryset.values("asset__category__name")
        .annotate(total=Count("id"))
        .order_by("-total", "asset__category__name")
    )
    dashboard_notifications = build_user_notifications(request.user)
    focused_notification = None
    if notification_id:
        focused_notification = next(
            (notification for notification in dashboard_notifications if notification.get("id") == notification_id),
            None,
        )
    elif notification_focus_asset_id is not None:
        focus_token = f"focus_asset_id={notification_focus_asset_id}"
        focused_notification = next(
            (notification for notification in dashboard_notifications if focus_token in notification.get("action_url", "")),
            None,
        )
    dashboard_help_topics = _help_topic_cards_for(request, role, limit=6)

    recent_requests = AssetRequest.objects.select_related("asset", "reviewed_by").filter(
        requested_by=request.user,
    )[:6]
    return {
        "total_assets": total_assets,
        "available": available,
        "allocated": allocated,
        "maintenance": maintenance,
        "disposed": disposed,
        "active_allocations": active_allocations,
        "department_category_breakdown": department_category_breakdown,
        "recent_assets": (
            inventory_assets_qs.order_by("-created_at")[:5]
            if inventory_search_active
            else assets_qs.none()
        ),
        "recent_allocations": (
            allocations_qs.filter(
                Q(asset__in=activity_assets_qs)
                | Q(allocated_to__username__icontains=activity_search)
                | Q(allocated_to_lab__building__icontains=activity_search)
                | Q(allocated_to_lab__room__icontains=activity_search)
                | Q(allocated_to_lab__department__name__icontains=activity_search)
                | Q(purpose__icontains=activity_search)
            ).order_by("-allocation_date")[:5]
            if activity_search_active
            else allocations_qs.none()
        ),
        "recent_maintenance": (
            maintenance_qs.filter(
                Q(asset__in=activity_assets_qs)
                | Q(description__icontains=activity_search)
                | Q(parts_replaced__icontains=activity_search)
                | Q(resolution_notes__icontains=activity_search)
                | Q(technician__username__icontains=activity_search)
                | Q(reported_by__username__icontains=activity_search)
            ).order_by("-scheduled_date")[:5]
            if activity_search_active
            else maintenance_qs.none()
        ),
        "department_assets": department_assets,
        "category_assets": category_assets,
        "request_status_by_asset": request_status_by_asset,
        "recent_requests": recent_requests,
        "assets_under_care": assets_under_care,
        "assets_under_care_total": assets_under_care_queryset.count(),
        "open_maintenance_by_asset_id": open_maintenance_by_asset_id,
        "assets_under_care_by_category": assets_under_care_by_category,
        "dashboard_notifications": dashboard_notifications,
        "dashboard_notification_count": len(dashboard_notifications),
        "focused_notification": focused_notification,
        "dashboard_help_topics": dashboard_help_topics,
        "dashboard_help_topics_count": len(dashboard_help_topics),
        "department_distribution": department_distribution,
        "user_role": get_role_label(role, default="Unassigned"),
        "user_department": department,
        "request_form_asset_id": request_form_asset_id,
        "request_form_values_by_asset": request_form_values_by_asset or {},
        "request_form_errors_by_asset": request_form_errors_by_asset or {},
        "issue_form_asset_id": issue_form_asset_id,
        "issue_form_values_by_asset": issue_form_values_by_asset or {},
        "issue_form_errors_by_asset": issue_form_errors_by_asset or {},
        "asset_search": asset_search,
        "category_search": category_search,
        "inventory_search": inventory_search,
        "activity_search": activity_search,
        "user_asset_search": user_asset_search,
        "dashboard_search_active": dashboard_search_active,
        "category_search_active": category_search_active,
        "inventory_search_active": inventory_search_active,
        "activity_search_active": activity_search_active,
        "user_asset_search_active": user_asset_search_active,
        "default_dashboard_section": default_dashboard_section,
        "department_assets_total": department_assets_qs.count(),
        "department_assets_search_active": bool(asset_search or request_form_asset_id),
        "category_assets_total": category_assets_qs.count(),
        "role_workspace_links": role_workspace_links,
        "asset_workspace_permissions": asset_workspace_permissions,
        "report_links": report_links,
        "can_request_assets": can_request_assets,
        "show_department_category_breakdown": show_department_category_breakdown,
        "can_browse_department_assets_without_search": can_browse_department_assets_without_search,
        "can_view_activity_overview": can_view_activity_overview,
        "can_view_reports": can_view_reports,
        "can_view_user_asset_lookup": can_view_user_asset_lookup,
        "user_asset_lookup": user_asset_lookup,
        "notification_focus_asset_id": notification_focus_asset_id,
    }


@staff_member_required
def asset_list(request):
    query_string = request.META.get("QUERY_STRING", "")
    target = "/admin/inventory/"
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target)


@login_required
def workspace_resource(request, resource):
    user_role = infer_user_role(request.user)
    resource_config = RESOURCE_CONFIGS.get(resource)
    if not resource_config:
        raise Http404("Unknown workspace resource.")

    allowed_resources = set(WORKSPACE_RESOURCE_ORDER) if request.user.is_superuser else WORKSPACE_ACCESS_BY_ROLE.get(user_role, set())
    if resource not in allowed_resources:
        messages.error(request, "Your account role does not have access to that workspace.")
        return redirect("assets:dashboard")

    workspace_permissions = _workspace_permissions_for(resource, user_role, request.user.is_superuser)
    allocation_permissions = _workspace_permissions_for("allocations", user_role, request.user.is_superuser)
    notification_id = request.GET.get("notification", "").strip()
    workspace_notifications = build_user_notifications(request.user)
    focused_notification = (
        next((notification for notification in workspace_notifications if notification.get("id") == notification_id), None)
        if notification_id
        else None
    )
    context = {
        "title": resource_config["title"],
        "resource": resource,
        "resource_config": resource_config,
        "edit_id": request.GET.get("edit", "").strip(),
        "workspace_permissions": workspace_permissions,
        "allocation_shortcuts": {
            "enabled": allocation_permissions["can_create"],
            "manager_url": reverse("assets:workspace_resource", kwargs={"resource": "allocations"}),
        },
        "focused_notification": focused_notification,
        "user_role": get_role_label(user_role, default="Unassigned"),
        "workspace_description": WORKSPACE_DESCRIPTIONS.get(resource, ""),
    }
    return render(request, "workspace/resource_manager.html", context)


@login_required
@require_POST
def request_asset(request, asset_id):
    asset_search = request.POST.get("asset_search", "").strip()

    def dashboard_redirect():
        dashboard_url = reverse("assets:dashboard")
        return f"{dashboard_url}?asset_search={asset_search}" if asset_search else dashboard_url

    if not _user_can_request_assets(request.user):
        messages.error(request, "Administrator and auditor accounts cannot request assets.")
        return redirect(dashboard_redirect())

    asset = get_object_or_404(
        Asset.objects.select_related("current_location", "current_location__department"),
        pk=asset_id,
    )

    profile = getattr(request.user, "profile", None)
    department = getattr(profile, "department", None)

    if not request.user.is_superuser and department and asset.current_location.department_id != department.id:
        messages.error(request, "You can only request assets from your department.")
        return redirect(dashboard_redirect())

    if asset.status != "available":
        messages.error(request, "This asset is not currently available for requests.")
        return redirect(dashboard_redirect())

    existing_request = AssetRequest.objects.filter(asset=asset, requested_by=request.user, status="pending").first()
    if existing_request:
        messages.info(request, "You already have a pending request for this asset.")
        return redirect(dashboard_redirect())

    form = AssetRequestForm(request.POST)
    if not form.is_valid():
        request_form_values_by_asset = {
            asset.id: {
                "message": request.POST.get("message", ""),
                "requested_start_at": request.POST.get("requested_start_at", ""),
                "requested_end_at": request.POST.get("requested_end_at", ""),
                "usage_location": request.POST.get("usage_location", ""),
                "asset_search": asset_search,
            }
        }
        request_form_errors_by_asset = {
            asset.id: {
                "message": list(form.errors.get("message", [])),
                "requested_start_at": list(form.errors.get("requested_start_at", [])),
                "requested_end_at": list(form.errors.get("requested_end_at", [])),
                "usage_location": list(form.errors.get("usage_location", [])),
                "non_field_errors": list(form.non_field_errors()),
            }
        }
        context = _build_dashboard_context(
            request,
            request_form_asset_id=asset.id,
            request_form_values_by_asset=request_form_values_by_asset,
            request_form_errors_by_asset=request_form_errors_by_asset,
            asset_search_query=asset_search,
        )
        return render(request, "dashboard.html", context, status=400)

    created_request = AssetRequest.objects.create(
        asset=asset,
        requested_by=request.user,
        message=form.cleaned_data["message"],
        requested_start_at=form.cleaned_data["requested_start_at"],
        requested_end_at=form.cleaned_data["requested_end_at"],
        usage_location=form.cleaned_data["usage_location"],
    )
    log_audit_event(
        actor=request.user,
        action="create",
        instance=created_request,
        source=request.path,
        metadata={"fields": ["asset", "message", "requested_start_at", "requested_end_at", "usage_location"]},
    )
    messages.success(request, f"Your request for {asset.name} has been submitted.")
    return redirect(dashboard_redirect())


@login_required
@require_POST
def report_asset_issue(request, asset_id):
    allocation = get_object_or_404(
        Allocation.objects.select_related(
            "asset",
            "asset__category",
            "asset__current_location",
            "asset__current_location__department",
        ),
        asset_id=asset_id,
        allocated_to=request.user,
        status__in=["active", "overdue"],
    )
    asset = allocation.asset
    form = AssetIssueReportForm(request.POST)

    if not form.is_valid():
        issue_form_values_by_asset = {
            asset.id: {
                "description": request.POST.get("description", ""),
            }
        }
        issue_form_errors_by_asset = {
            asset.id: {
                "description": list(form.errors.get("description", [])),
                "non_field_errors": list(form.non_field_errors()),
            }
        }
        context = _build_dashboard_context(
            request,
            issue_form_asset_id=asset.id,
            issue_form_values_by_asset=issue_form_values_by_asset,
            issue_form_errors_by_asset=issue_form_errors_by_asset,
        )
        return render(request, "dashboard.html", context, status=400)

    maintenance_record = Maintenance.objects.create(
        asset=asset,
        maintenance_type="corrective",
        scheduled_date=timezone.localdate(),
        description=form.cleaned_data["description"],
        reported_by=request.user,
        status="scheduled",
    )
    log_audit_event(
        actor=request.user,
        action="create",
        instance=maintenance_record,
        source=request.path,
        metadata={"fields": ["asset", "maintenance_type", "scheduled_date", "description", "reported_by", "status"]},
    )
    messages.success(request, f"Your maintenance report for {asset.name} has been submitted.")
    return redirect(f"{reverse('assets:dashboard')}#personal-overview")


@login_required
@require_POST
def cancel_request(request, request_id):
    asset_request = get_object_or_404(
        AssetRequest.objects.select_related("asset"),
        pk=request_id,
        requested_by=request.user,
    )

    if asset_request.status != "pending":
        messages.error(request, "Only pending requests can be cancelled.")
        return redirect("assets:dashboard")

    asset_request.status = "cancelled"
    asset_request.reviewed_by = None
    asset_request.reviewed_at = None
    asset_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "decline_reason",
            "handover_location",
            "issue_person_details",
            "updated_at",
        ]
    )
    log_audit_event(
        actor=request.user,
        action="update",
        instance=asset_request,
        source=request.path,
        metadata={"fields": ["status", "reviewed_by", "reviewed_at"]},
    )
    messages.success(request, f"Your request for {asset_request.asset.name} has been cancelled.")
    return redirect("assets:dashboard")


@login_required
@require_POST
def mark_user_asset_returned(request, allocation_id):
    role = infer_user_role(request.user)
    user_asset_search = request.POST.get("user_asset_search", "").strip()

    dashboard_url = reverse("assets:dashboard")
    redirect_target = f"{dashboard_url}?user_asset_search={user_asset_search}#user-asset-lookup" if user_asset_search else f"{dashboard_url}#user-asset-lookup"

    if not _user_can_manage_user_asset_lookup(request.user, role):
        messages.error(request, "Your account role cannot mark searched user assets as returned.")
        return redirect(redirect_target)

    allocation = get_object_or_404(
        Allocation.objects.select_related(
            "asset",
            "allocated_to",
            "allocated_to__profile",
            "allocated_to__profile__department",
        ),
        pk=allocation_id,
        status__in=["active", "overdue"],
    )

    actor_department = getattr(getattr(request.user, "profile", None), "department", None)
    recipient_department = getattr(getattr(allocation.allocated_to, "profile", None), "department", None)
    actor_department_id = getattr(actor_department, "id", None)
    recipient_department_id = getattr(recipient_department, "id", None)
    if not request.user.is_superuser and actor_department_id and recipient_department_id:
        if actor_department_id != recipient_department_id:
            messages.error(request, "You can only return assets for users in your department.")
            return redirect(redirect_target)

    allocation.status = "returned"
    allocation.actual_return_date = timezone.localdate()
    if not allocation.condition_in:
        allocation.condition_in = allocation.asset.condition
    allocation.save()
    log_audit_event(
        actor=request.user,
        action="update",
        instance=allocation,
        source=request.path,
        metadata={"fields": ["status", "actual_return_date", "condition_in"]},
    )

    messages.success(request, f"{allocation.asset.name} has been marked as returned.")
    return redirect(redirect_target)
