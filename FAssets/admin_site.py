from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import path, reverse


ROLE_OPTIONS = [
    {"value": "admin", "label": "Admin"},
    {"value": "dean", "label": "Dean"},
    {"value": "cod", "label": "COD"},
    {"value": "lecturer", "label": "Lecturer"},
    {"value": "lab_technician", "label": "Lab Technician"},
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
        "title_fields": ["code", "name"],
        "list_columns": [
            {"key": "code", "label": "Code"},
            {"key": "name", "label": "Category"},
            {"key": "depreciation_years", "label": "Depreciation Years"},
        ],
        "fields": [
            {"name": "code", "label": "Code", "type": "text", "required": True},
            {"name": "name", "label": "Category Name", "type": "text", "required": True},
            {"name": "depreciation_years", "label": "Depreciation Years", "type": "number", "required": True},
            {
                "name": "parent",
                "label": "Parent Category",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/categories/",
                "option_label_keys": ["code", "name"],
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
            {"key": "asset_id", "label": "Asset ID"},
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
                "option_label_keys": ["code", "name"],
            },
            {"name": "description", "label": "Description", "type": "textarea", "required": False},
            {"name": "purchase_date", "label": "Purchase Date", "type": "date", "required": True},
            {"name": "purchase_cost", "label": "Purchase Cost", "type": "number", "required": True, "step": "0.01"},
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
            {"name": "warranty_expiry", "label": "Warranty Expiry", "type": "date", "required": False},
            {"name": "serial_number", "label": "Serial Number", "type": "text", "required": False},
            {"name": "barcode", "label": "Barcode", "type": "text", "required": False},
        ],
    },
    "users": {
        "title": "User Manager",
        "singular": "User",
        "api_base": "/api/users/",
        "title_fields": ["username", "first_name", "last_name"],
        "list_columns": [
            {"key": "username", "label": "Username"},
            {"key": "department_name", "label": "Department"},
            {"key": "role", "label": "Role"},
            {"key": "is_active", "label": "Active"},
        ],
        "fields": [
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "first_name", "label": "First Name", "type": "text", "required": False},
            {"name": "last_name", "label": "Last Name", "type": "text", "required": False},
            {"name": "email", "label": "Email", "type": "email", "required": False},
            {"name": "password", "label": "Password", "type": "password", "required": False, "omit_if_blank_on_edit": True},
            {"name": "employee_id", "label": "Employee ID", "type": "text", "required": False},
            {
                "name": "department",
                "label": "Department",
                "type": "select",
                "required": False,
                "options_endpoint": "/api/departments/",
                "option_label_keys": ["code", "name"],
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
            {"name": "allocation_date", "label": "Allocation Date", "type": "date", "required": True},
            {"name": "expected_return_date", "label": "Expected Return Date", "type": "date", "required": True},
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
            path("manage/<slug:resource>/", self.admin_view(self.manage_resource_view), name="manage_resource"),
        ]
        return custom_urls + urls

    def each_context(self, request):
        context = super().each_context(request)

        from accounts.models import Department, Faculty
        from allocations.models import Allocation
        from assets.models import Asset, Category, Supplier
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
                ],
                "admin_collections": [
                    {"label": "Faculties", "value": Faculty.objects.count()},
                    {"label": "Suppliers", "value": Supplier.objects.count()},
                    {"label": "Open Maintenance", "value": Maintenance.objects.filter(status__in=["scheduled", "in_progress"]).count()},
                    {"label": "Active Allocations", "value": Allocation.objects.filter(status__in=["active", "overdue"]).count()},
                ],
                "recent_assets": Asset.objects.select_related("category", "current_location")
                .order_by("-created_at")[:6],
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

    def index(self, request, extra_context=None):
        app_list = self._annotate_app_list(self.get_app_list(request))
        context = {
            **self.each_context(request),
            "title": self.index_title,
            "app_list": app_list,
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
        }
        request.current_app = self.name
        return TemplateResponse(request, "admin/resource_manager.html", context)
