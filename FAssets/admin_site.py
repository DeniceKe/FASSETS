from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.db import transaction
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from datetime import timedelta

from accounts.audit import log_audit_event
from assets.reporting import apply_report_filters, build_report_filter_context, normalize_report_filters


ROLE_OPTIONS = [
    {"value": "admin", "label": "Admin"},
    {"value": "dean", "label": "Dean"},
    {"value": "cod", "label": "COD"},
    {"value": "lecturer", "label": "Lecturer"},
    {"value": "lab_technician", "label": "Lab Technician"},
    {"value": "internal_auditor", "label": "Auditor"},
]

STATUS_OPTIONS = [
    {"value": "available", "label": "Available"},
    {"value": "allocated", "label": "Allocated"},
    {"value": "maintenance", "label": "Under Maintenance"},
    {"value": "disposed", "label": "Disposed"},
]

CONDITION_OPTIONS = [
    {"value": "new", "label": "New"},
    {"value": "excellent", "label": "Excellent"},
    {"value": "good", "label": "Good"},
    {"value": "fair", "label": "Fair"},
    {"value": "poor", "label": "Poor"},
    {"value": "unserviceable", "label": "Unserviceable"},
]

ROOM_TYPE_OPTIONS = [
    {"value": "office", "label": "Office"},
    {"value": "lab", "label": "Laboratory"},
    {"value": "storage", "label": "Storage"},
]

ALLOCATION_STATUS_OPTIONS = [
    {"value": "active", "label": "Active"},
    {"value": "returned", "label": "Returned"},
    {"value": "overdue", "label": "Overdue"},
]

ALLOCATION_TYPE_OPTIONS = [
    {"value": "temporary", "label": "Temporary"},
    {"value": "permanent", "label": "Permanent"},
]

MAINTENANCE_TYPE_OPTIONS = [
    {"value": "preventive", "label": "Preventive"},
    {"value": "corrective", "label": "Corrective"},
]

MAINTENANCE_STATUS_OPTIONS = [
    {"value": "scheduled", "label": "Scheduled"},
    {"value": "in_progress", "label": "In Progress"},
    {"value": "completed", "label": "Completed"},
    {"value": "cancelled", "label": "Cancelled"},
]

RESOURCE_CONFIGS = {
    "faculties": {
        "title": "Faculty Manager",
        "singular": "Faculty",
        "api_base": "/api/faculties/",
        "title_fields": ["name"],
        "list_columns": [
            {"key": "name", "label": "Faculty"},
        ],
        "fields": [
            {"name": "name", "label": "Faculty Name", "type": "text", "required": True},
        ],
    },
    "departments": {
        "title": "Department Manager",
        "singular": "Department",
        "api_base": "/api/departments/",
        "title_fields": ["code", "name"],
        "list_columns": [
            {"key": "code", "label": "Code"},
            {"key": "name", "label": "Department"},
            {"key": "faculty_name", "label": "Faculty"},
        ],
        "fields": [
            {"name": "code", "label": "Code", "type": "text", "required": True},
            {"name": "name", "label": "Department Name", "type": "text", "required": True},
            {
                "name": "faculty",
                "label": "Faculty",
                "type": "select",
                "required": True,
                "options_endpoint": "/api/faculties/",
                "option_label_keys": ["name"],
            },
        ],
    },
    "categories": {
        "title": "Category Manager",
        "singular": "Category",
        "api_base": "/api/categories/",
        "title_fields": ["name"],
        "list_columns": [
            {"key": "name", "label": "Category"},
            {"key": "parent_name", "label": "Parent Category"},
            {"key": "depreciation_years", "label": "Depreciation Years"},
        ],
        "fields": [
            {"name": "name", "label": "Category Name", "type": "text", "required": True},
            {"name": "depreciation_years", "label": "Depreciation Years", "type": "number", "required": True},
            {
                "name": "parent",
                "label": "Parent Category",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/categories/",
                "option_label_keys": ["name"],
            },
        ],
    },
    "suppliers": {
        "title": "Supplier Manager",
        "singular": "Supplier",
        "api_base": "/api/suppliers/",
        "title_fields": ["name"],
        "list_columns": [
            {"key": "name", "label": "Supplier"},
            {"key": "email", "label": "Email"},
            {"key": "phone", "label": "Phone"},
        ],
        "fields": [
            {"name": "name", "label": "Supplier Name", "type": "text", "required": True},
            {"name": "email", "label": "Email", "type": "email", "required": False},
            {"name": "phone", "label": "Phone", "type": "text", "required": False},
            {"name": "address", "label": "Address", "type": "textarea", "required": False},
        ],
    },
    "locations": {
        "title": "Location Manager",
        "singular": "Location",
        "api_base": "/api/locations/",
        "title_fields": ["department_name", "building", "room"],
        "list_columns": [
            {"key": "department_name", "label": "Department"},
            {"key": "building", "label": "Building"},
            {"key": "room", "label": "Room"},
            {"key": "room_type", "label": "Room Type"},
        ],
        "fields": [
            {
                "name": "department",
                "label": "Department",
                "type": "select",
                "required": True,
                "options_endpoint": "/api/departments/",
                "option_label_keys": ["code", "name"],
            },
            {"name": "building", "label": "Building", "type": "text", "required": True},
            {"name": "floor", "label": "Floor", "type": "text", "required": False},
            {"name": "room", "label": "Room", "type": "text", "required": True},
            {"name": "room_type", "label": "Room Type", "type": "select", "required": True, "options": ROOM_TYPE_OPTIONS},
        ],
    },
    "assets": {
        "title": "Asset Manager",
        "singular": "Asset",
        "api_base": "/api/assets/",
        "title_fields": ["asset_id", "name"],
        "list_columns": [
            {"key": "thumbnail_url", "label": "Thumbnail", "image": True},
            {"key": "asset_id", "label": "Asset ID"},
            {"key": "barcode", "label": "Barcode"},
            {"key": "name", "label": "Asset"},
            {"key": "category_name", "label": "Category"},
            {"key": "status", "label": "Status", "badge": True},
        ],
        "fields": [
            {"name": "name", "label": "Asset Name", "type": "text", "required": True},
            {
                "name": "category",
                "label": "Category",
                "type": "select",
                "required": True,
                "options_endpoint": "/api/categories/",
                "option_label_keys": ["name"],
            },
            {"name": "description", "label": "Description", "type": "textarea", "required": False},
            {"name": "purchase_date", "label": "Purchase Date", "type": "date", "required": True},
            {
                "name": "purchase_cost",
                "label": "Purchase Cost",
                "type": "number",
                "required": True,
                "step": "0.01",
                "prefix": "KSH",
            },
            {
                "name": "supplier",
                "label": "Supplier",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/suppliers/",
                "option_label_keys": ["name"],
            },
            {
                "name": "current_location",
                "label": "Current Location",
                "type": "select",
                "required": True,
                "options_endpoint": "/api/locations/",
                "option_label_keys": ["department_name", "building", "room"],
            },
            {"name": "condition", "label": "Condition", "type": "select", "required": True, "options": CONDITION_OPTIONS},
            {"name": "status", "label": "Status", "type": "select", "required": True, "options": STATUS_OPTIONS},
            {"name": "disposal_reason", "label": "Disposal Reason", "type": "textarea", "required": False},
            {"name": "disposal_reference", "label": "Disposal Reference", "type": "text", "required": False},
            {"name": "warranty_expiry", "label": "Warranty Expiry", "type": "date", "required": False},
            {"name": "serial_number", "label": "Serial Number", "type": "text", "required": False},
            {
                "name": "thumbnail",
                "label": "Thumbnail Image",
                "type": "file",
                "required": False,
                "accept": "image/*",
                "preview_field": "thumbnail_url",
                "upload_endpoint": "thumbnail",
            },
        ],
    },
    "users": {
        "title": "User Manager",
        "singular": "User",
        "api_base": "/api/users/",
        "title_fields": ["username", "first_name", "last_name"],
        "list_columns": [
            {"key": "username", "label": "Username"},
            {"key": "user_type", "label": "Type"},
            {"key": "department_name", "label": "Department"},
            {"key": "staff_location_label", "label": "Office/Lab"},
            {"key": "role", "label": "Role"},
            {"key": "is_active", "label": "Active"},
        ],
        "fields": [
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "first_name", "label": "First Name", "type": "text", "required": False},
            {"name": "last_name", "label": "Last Name", "type": "text", "required": False},
            {"name": "email", "label": "Email", "type": "email", "required": False},
            {"name": "user_type", "label": "Account Type", "type": "select", "required": False, "options": [
                {"value": "student", "label": "Student"},
                {"value": "staff", "label": "Staff"},
            ]},
            {"name": "registration_number", "label": "Student ID", "type": "text", "required": False, "read_only_on_edit": True},
            {"name": "employee_id", "label": "Employee ID", "type": "text", "required": False, "read_only_on_edit": True},
            {
                "name": "department",
                "label": "Department",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/departments/",
                "option_label_keys": ["code", "name"],
            },
            {
                "name": "staff_location",
                "label": "Office / Lab",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/locations/",
                "option_label_keys": ["department_name", "building", "room"],
            },
            {"name": "role", "label": "Role", "type": "select", "required": False, "options": ROLE_OPTIONS},
            {"name": "is_active", "label": "Active", "type": "checkbox", "required": False},
        ],
    },
    "allocations": {
        "title": "Allocation Manager",
        "singular": "Allocation",
        "api_base": "/api/allocations/",
        "title_fields": ["asset_identifier", "allocated_to_username", "allocated_to_lab_label"],
        "list_columns": [
            {"key": "asset_identifier", "label": "Asset"},
            {"key": "allocated_to_username", "label": "User"},
            {"key": "allocated_to_lab_label", "label": "Lab"},
            {"key": "allocation_type", "label": "Type"},
            {"key": "status", "label": "Status", "badge": True},
        ],
        "fields": [
            {
                "name": "asset",
                "label": "Asset",
                "type": "select",
                "required": True,
                "options_endpoint": "/api/assets/",
                "option_label_keys": ["asset_id", "name"],
            },
            {
                "name": "allocated_to",
                "label": "Allocate To User",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/users/",
                "option_label_keys": ["username", "department_name"],
            },
            {
                "name": "allocated_to_lab",
                "label": "Allocate To Lab",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/locations/",
                "option_label_keys": ["department_name", "building", "room"],
            },
            {"name": "allocation_type", "label": "Allocation Type", "type": "select", "required": True, "options": ALLOCATION_TYPE_OPTIONS},
            {"name": "allocation_date", "label": "Allocation Date", "type": "date", "required": True},
            {"name": "expected_return_date", "label": "Expected Return Date", "type": "date", "required": False},
            {"name": "actual_return_date", "label": "Actual Return Date", "type": "date", "required": False},
            {"name": "purpose", "label": "Purpose", "type": "textarea", "required": True},
            {"name": "condition_out", "label": "Condition Out", "type": "select", "required": True, "options": CONDITION_OPTIONS},
            {"name": "condition_in", "label": "Condition In", "type": "select", "required": False, "options": CONDITION_OPTIONS},
            {"name": "status", "label": "Status", "type": "select", "required": True, "options": ALLOCATION_STATUS_OPTIONS},
        ],
    },
    "maintenance": {
        "title": "Maintenance Manager",
        "singular": "Maintenance Record",
        "api_base": "/api/maintenance/",
        "title_fields": ["asset_identifier", "maintenance_type", "status"],
        "list_columns": [
            {"key": "asset_identifier", "label": "Asset"},
            {"key": "maintenance_type", "label": "Type"},
            {"key": "status", "label": "Status", "badge": True},
            {"key": "scheduled_date", "label": "Scheduled"},
        ],
        "fields": [
            {
                "name": "asset",
                "label": "Asset",
                "type": "select",
                "required": True,
                "options_endpoint": "/api/assets/",
                "option_label_keys": ["asset_id", "name"],
            },
            {"name": "maintenance_type", "label": "Type", "type": "select", "required": True, "options": MAINTENANCE_TYPE_OPTIONS},
            {"name": "scheduled_date", "label": "Scheduled Date", "type": "date", "required": True},
            {"name": "completed_date", "label": "Completed Date", "type": "date", "required": False},
            {
                "name": "technician",
                "label": "Technician",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/users/",
                "option_label_keys": ["username", "department_name"],
            },
            {"name": "description", "label": "Description", "type": "textarea", "required": True},
            {"name": "cost", "label": "Cost", "type": "number", "required": False, "step": "0.01"},
            {"name": "parts_replaced", "label": "Parts Replaced", "type": "textarea", "required": False},
            {"name": "resolution_notes", "label": "Resolution Notes", "type": "textarea", "required": False},
            {"name": "status", "label": "Status", "type": "select", "required": True, "options": MAINTENANCE_STATUS_OPTIONS},
        ],
    },
}

MODEL_RESOURCE_MAP = {
    "Faculty": "faculties",
    "Department": "departments",
    "Category": "categories",
    "Supplier": "suppliers",
    "Location": "locations",
    "Asset": "assets",
    "User": "users",
    "Allocation": "allocations",
    "Maintenance": "maintenance",
}


class FAssetsAdminSite(AdminSite):
    site_header = "FASSETS Administration"
    site_title = "FASSETS Admin"
    index_title = "Administrative Control Center"
    index_template = "admin/index.html"
    login_template = "admin/login.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("inventory/", self.admin_view(self.inventory_view), name="inventory"),
            path("reports/", self.admin_view(self.reports_view), name="reports"),
            path("manage/<slug:resource>/", self.admin_view(self.manage_resource_view), name="manage_resource"),
            path(
                "asset-requests/<int:request_id>/review/",
                self.admin_view(self.review_asset_request_view),
                name="review_asset_request",
            ),
        ]
        return custom_urls + urls

    def each_context(self, request):
        context = super().each_context(request)

        from accounts.models import Department, Faculty
        from allocations.models import Allocation, AssetRequest
        from assets.models import Asset, AssetMovement, Category, DepreciationRecord, Supplier
        from maintenance.models import Maintenance

        User = get_user_model()

        context.update(
            {
                "dashboard_metrics": [
                    {"label": "Users", "value": User.objects.count()},
                    {"label": "Departments", "value": Department.objects.count()},
                    {"label": "Assets", "value": Asset.objects.count()},
                    {"label": "Allocations", "value": Allocation.objects.count()},
                    {"label": "Maintenance", "value": Maintenance.objects.count()},
                    {"label": "Categories", "value": Category.objects.count()},
                ],
                "admin_quick_links": [
                    {"label": "Manage Assets", "url": reverse("admin:manage_resource", kwargs={"resource": "assets"})},
                    {"label": "Manage Users", "url": reverse("admin:manage_resource", kwargs={"resource": "users"})},
                    {"label": "Manage Allocations", "url": reverse("admin:manage_resource", kwargs={"resource": "allocations"})},
                    {"label": "Manage Maintenance", "url": reverse("admin:manage_resource", kwargs={"resource": "maintenance"})},
                    {"label": "Open Reports", "url": reverse("admin:reports")},
                    {"label": "Review Requests", "url": f"{reverse('admin:index')}#asset-requests"},
                ],
                "admin_collections": [
                    {"label": "Faculties", "value": Faculty.objects.count()},
                    {"label": "Suppliers", "value": Supplier.objects.count()},
                    {"label": "Active Allocations", "value": Allocation.objects.filter(status__in=["active", "overdue"]).count()},
                ],
                "pending_asset_requests_count": AssetRequest.objects.filter(status="pending").count(),
                "pending_asset_requests": AssetRequest.objects.select_related(
                    "asset",
                    "requested_by",
                    "requested_by__profile",
                    "requested_by__profile__department",
                )
                .filter(status="pending")
                .order_by("-requested_at")[:10],
                "recent_assets": Asset.objects.select_related("category", "current_location")
                .order_by("-created_at")[:6],
                "recent_movements": AssetMovement.objects.select_related(
                    "asset",
                    "from_location",
                    "to_location",
                    "moved_by",
                ).order_by("-moved_at")[:6],
                "depreciation_totals": DepreciationRecord.objects.aggregate(
                    total_accumulated=Sum("accumulated_depreciation"),
                    total_book_value=Sum("net_book_value"),
                ),
                "recent_depreciation_records": DepreciationRecord.objects.select_related("asset")
                .order_by("-year", "asset__asset_id")[:6],
                "recent_allocations": Allocation.objects.select_related("asset", "allocated_to", "allocated_to_lab")
                .order_by("-allocation_date")[:6],
                "recent_maintenance": Maintenance.objects.select_related("asset", "technician")
                .order_by("-created_at")[:6],
                "recent_users": User.objects.order_by("-date_joined")[:6],
            }
        )
        return context

    def _annotate_app_list(self, app_list):
        for app in app_list:
            for model in app.get("models", []):
                resource = MODEL_RESOURCE_MAP.get(model.get("object_name"))
                if resource:
                    model["manage_url"] = reverse("admin:manage_resource", kwargs={"resource": resource})
                else:
                    model["manage_url"] = model.get("admin_url")
        return app_list

    @staticmethod
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
            from allocations.models import Allocation

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
            display_name = user.get_full_name().strip() or user.username
            results.append(
                {
                    "user": user,
                    "display_name": display_name,
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

    def index(self, request, extra_context=None):
        app_list = self._annotate_app_list(self.get_app_list(request))
        user_asset_lookup = self._build_user_asset_lookup_context(request.GET.get("user_asset_search", ""))
        context = {
            **self.each_context(request),
            "title": self.index_title,
            "app_list": app_list,
            "user_asset_lookup": user_asset_lookup,
            **(extra_context or {}),
        }
        request.current_app = self.name
        return TemplateResponse(request, self.index_template, context)

    def inventory_view(self, request):
        from assets.models import Asset, Category

        queryset = Asset.objects.select_related("category", "current_location", "current_location__department")

        q = request.GET.get("q", "").strip()
        category = request.GET.get("category", "").strip()
        status = request.GET.get("status", "").strip()

        if q:
            queryset = queryset.filter(
                Q(asset_id__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q)
            )

        if category:
            queryset = queryset.filter(category_id=category)

        if status:
            queryset = queryset.filter(status=status)

        context = {
            **self.each_context(request),
            "title": "Inventory",
            "assets": queryset.order_by("-created_at")[:200],
            "categories": Category.objects.all().order_by("name"),
            "total_results": queryset.count(),
            "q": q,
            "category": category,
            "status": status,
        }
        request.current_app = self.name
        return TemplateResponse(request, "admin/inventory.html", context)

    def reports_view(self, request):
        from allocations.models import Allocation, AssetRequest
        from assets.models import Asset, Category
        from maintenance.models import Maintenance

        categories = Category.objects.all().order_by("name")
        filters = normalize_report_filters(request.GET)
        inventory_qs = Asset.objects.select_related(
            "category",
            "supplier",
            "current_location",
            "current_location__department",
        ).order_by("asset_id")
        requests_qs = AssetRequest.objects.select_related(
            "asset",
            "requested_by",
            "reviewed_by",
        ).order_by("-requested_at")
        maintenance_qs = Maintenance.objects.select_related(
            "asset",
            "technician",
            "reported_by",
        ).order_by("-scheduled_date", "-created_at")
        returned_assets_qs = Allocation.objects.select_related(
            "asset",
            "allocated_to",
            "allocated_to_lab",
            "allocated_by",
        ).filter(status="returned").order_by("-actual_return_date", "-allocation_date")
        assigned_assets_qs = Allocation.objects.select_related(
            "asset",
            "allocated_to",
            "allocated_to_lab",
            "allocated_by",
        ).filter(status__in=["active", "overdue"]).order_by("-allocation_date")
        movement_qs = None
        depreciation_qs = None

        filtered_querysets = apply_report_filters(
            filters=filters,
            inventory_qs=inventory_qs,
            requests_qs=requests_qs,
            maintenance_qs=maintenance_qs,
            assigned_qs=assigned_assets_qs,
            returned_qs=returned_assets_qs,
            movement_qs=movement_qs,
            depreciation_qs=depreciation_qs,
        )
        inventory_qs = filtered_querysets["inventory_qs"]
        requests_qs = filtered_querysets["requests_qs"]
        maintenance_qs = filtered_querysets["maintenance_qs"]
        returned_assets_qs = filtered_querysets["returned_qs"]

        generated_by = request.user.get_full_name() or request.user.get_username() or "System"
        generated_at = timezone.localtime()
        selected_category = categories.filter(pk=filters["inventory_category"]).first() if filters["inventory_category"] else None
        filter_context = build_report_filter_context(filters, selected_category=selected_category)

        context = {
            **self.each_context(request),
            "title": "Reports",
            "inventory_assets": inventory_qs,
            "asset_requests_report": requests_qs,
            "maintenance_report": maintenance_qs,
            "returned_assets_report": returned_assets_qs,
            "categories": categories,
            "date_from": filters["date_from"],
            "date_to": filters["date_to"],
            "inventory_status": filters["inventory_status"],
            "asset_condition": filters["asset_condition"],
            "inventory_category": filters["inventory_category"],
            "request_status": filters["request_status"],
            "maintenance_status": filters["maintenance_status"],
            "report_generated_by": generated_by,
            "report_generated_at": generated_at,
            **filter_context,
        }
        request.current_app = self.name
        return TemplateResponse(request, "admin/reports.html", context)

    def manage_resource_view(self, request, resource):
        resource_config = RESOURCE_CONFIGS.get(resource)
        if not resource_config:
            raise Http404("Unknown resource.")

        context = {
            **self.each_context(request),
            "title": resource_config["title"],
            "resource": resource,
            "resource_config": resource_config,
            "edit_id": request.GET.get("edit", "").strip(),
            "allocation_shortcuts": {
                "enabled": True,
                "manager_url": reverse("admin:manage_resource", kwargs={"resource": "allocations"}),
            },
        }
        request.current_app = self.name
        return TemplateResponse(request, "admin/resource_manager.html", context)

    def review_asset_request_view(self, request, request_id):
        if request.method != "POST":
            raise Http404("Review action not available.")

        asset_request = get_object_or_404(
            self._get_asset_request_queryset(),
            pk=request_id,
        )
        action = request.POST.get("action", "").strip()
        decline_reason = request.POST.get("decline_reason", "").strip()
        handover_location = request.POST.get("handover_location", "").strip()
        issue_person_details = request.POST.get("issue_person_details", "").strip()

        if asset_request.status != "pending":
            messages.info(request, "This request has already been reviewed.")
            return redirect("admin:index")

        if action == "approve":
            try:
                allocation = self._approve_asset_request(
                    asset_request,
                    reviewer=request.user,
                    handover_location=handover_location,
                    issue_person_details=issue_person_details,
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("admin:index")

            log_audit_event(
                actor=request.user,
                action="create",
                instance=allocation,
                source=request.path,
                metadata={"fields": ["asset", "allocated_to", "allocated_by", "allocation_date", "expected_return_date", "purpose", "condition_out", "status"]},
            )
            log_audit_event(
                actor=request.user,
                action="update",
                instance=asset_request,
                source=request.path,
                metadata={"fields": ["status", "reviewed_by", "reviewed_at", "handover_location", "issue_person_details"]},
            )

            messages.success(request, f"Approved request for {asset_request.asset.name} and created its allocation.")
            return redirect("admin:index")

        if action == "decline":
            if not decline_reason:
                messages.error(request, "Please provide a reason before declining a request.")
                return redirect("admin:index")

            asset_request.status = "rejected"
            asset_request.decline_reason = decline_reason
            asset_request.reviewed_by = request.user
            asset_request.reviewed_at = timezone.now()
            asset_request.save(
                update_fields=["status", "decline_reason", "reviewed_by", "reviewed_at", "updated_at"]
            )
            log_audit_event(
                actor=request.user,
                action="update",
                instance=asset_request,
                source=request.path,
                metadata={"fields": ["status", "decline_reason", "reviewed_by", "reviewed_at"]},
            )
            messages.success(request, f"Declined request for {asset_request.asset.name}.")
            return redirect("admin:index")

        messages.error(request, "Unknown review action.")
        return redirect("admin:index")

    @staticmethod
    def _get_asset_request_queryset():
        from allocations.models import AssetRequest

        return AssetRequest.objects.select_related(
            "asset",
            "requested_by",
            "requested_by__profile",
            "requested_by__profile__department",
        )

    @staticmethod
    def _approve_asset_request(asset_request, reviewer, handover_location, issue_person_details):
        from allocations.models import Allocation

        allocation_date = timezone.localdate()
        purpose = asset_request.message.strip() or f"Approved asset request for {asset_request.asset.name}."

        with transaction.atomic():
            allocation = Allocation.objects.create(
                asset=asset_request.asset,
                allocated_to=asset_request.requested_by,
                allocated_by=reviewer,
                allocation_date=allocation_date,
                expected_return_date=allocation_date + timedelta(days=14),
                purpose=purpose,
                condition_out=asset_request.asset.condition,
                status="active",
            )

            asset_request.status = "approved"
            asset_request.reviewed_by = reviewer
            asset_request.reviewed_at = timezone.now()
            asset_request.handover_location = handover_location
            asset_request.issue_person_details = issue_person_details
            asset_request.save(
                update_fields=[
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "handover_location",
                    "issue_person_details",
                    "decline_reason",
                    "updated_at",
                ]
            )
            return allocation
