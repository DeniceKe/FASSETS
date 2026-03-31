from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Department, Faculty
from accounts.roles import (
    ROLE_ADMIN,
    ROLE_COD,
    ROLE_DEAN,
    ROLE_LAB_TECHNICIAN,
    ROLE_LECTURER,
    infer_user_role,
    user_has_role,
)
from allocations.models import Allocation
from assets.models import Asset, AssetMovement, Category, DepreciationRecord, Location, Supplier
from assets.services import record_asset_movement, sync_asset_depreciation
from maintenance.models import Maintenance

from .serializers import (
    AllocationSerializer,
    AssetSerializer,
    AssetMovementSerializer,
    CategorySerializer,
    DepreciationRecordSerializer,
    DepartmentSerializer,
    FacultySerializer,
    LocationSerializer,
    MaintenanceSerializer,
    SupplierSerializer,
    UserSerializer,
)

User = get_user_model()


class RolePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        allowed_roles = getattr(view, "allowed_roles", {})
        if not allowed_roles:
            return True

        action = getattr(view, "action", None) or request.method.lower()
        roles = allowed_roles.get(action, allowed_roles.get("*", []))
        if not roles:
            return False

        return user_has_role(request.user, *roles)


class ScopedQuerysetMixin:
    def user_department(self):
        profile = getattr(self.request.user, "profile", None)
        return getattr(profile, "department", None)

    def filter_department_queryset(self, queryset, department_lookup: str):
        department = self.user_department()
        role = infer_user_role(self.request.user)

        if self.request.user.is_superuser or role in {ROLE_ADMIN, ROLE_DEAN}:
            return queryset

        if department is None:
            return queryset.none()

        return queryset.filter(**{department_lookup: department})


class FacultyViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Faculty.objects.all().order_by("name")
    serializer_class = FacultySerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN],
        "create": [ROLE_ADMIN],
        "update": [ROLE_ADMIN],
        "partial_update": [ROLE_ADMIN],
        "destroy": [ROLE_ADMIN],
    }


class DepartmentViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Department.objects.select_related("faculty").all().order_by("name")
    serializer_class = DepartmentSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "create": [ROLE_ADMIN],
        "update": [ROLE_ADMIN],
        "partial_update": [ROLE_ADMIN],
        "destroy": [ROLE_ADMIN],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        return self.filter_department_queryset(queryset, "id")


class UserViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = User.objects.select_related("profile", "profile__department").all().order_by("username")
    serializer_class = UserSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD],
        "create": [ROLE_ADMIN],
        "update": [ROLE_ADMIN],
        "partial_update": [ROLE_ADMIN],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        role = infer_user_role(self.request.user)
        if self.request.user.is_superuser or role in {ROLE_ADMIN, ROLE_DEAN}:
            return queryset

        department = self.user_department()
        if department is None:
            return queryset.none()

        return queryset.filter(profile__department=department)


class CategoryViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.select_related("parent").all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "create": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "partial_update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "destroy": [ROLE_ADMIN],
    }


class SupplierViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all().order_by("name")
    serializer_class = SupplierSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "create": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "partial_update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "destroy": [ROLE_ADMIN],
    }


class LocationViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Location.objects.select_related("department").all().order_by("building", "room")
    serializer_class = LocationSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "create": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "partial_update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "destroy": [ROLE_ADMIN],
    }
    filterset_fields = ["department", "room_type", "building"]
    search_fields = ["building", "room", "department__name", "department__code"]
    ordering_fields = ["building", "room"]

    def get_queryset(self):
        queryset = super().get_queryset()
        return self.filter_department_queryset(queryset, "department")


class AssetViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Asset.objects.select_related(
        "category",
        "supplier",
        "current_location",
        "current_location__department",
        "created_by",
    ).all().order_by("-created_at")
    serializer_class = AssetSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "create": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "partial_update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "destroy": [ROLE_ADMIN],
    }
    filterset_fields = ["category", "status", "condition", "current_location__department"]
    search_fields = ["asset_id", "name", "serial_number", "description", "barcode"]
    ordering_fields = ["created_at", "purchase_date", "purchase_cost", "asset_id", "name"]

    def get_queryset(self):
        queryset = super().get_queryset()
        return self.filter_department_queryset(queryset, "current_location__department")

    def perform_create(self, serializer):
        asset = serializer.save(created_by=self.request.user)
        sync_asset_depreciation(asset)

    def perform_update(self, serializer):
        previous_asset = self.get_object()
        previous_location = previous_asset.current_location
        asset = serializer.save()
        sync_asset_depreciation(asset)

        if previous_location_id(previous_location) != previous_location_id(asset.current_location):
            record_asset_movement(
                asset=asset,
                from_location=previous_location,
                to_location=asset.current_location,
                moved_by=self.request.user,
                notes="Location updated through asset management.",
            )


class AllocationViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Allocation.objects.select_related(
        "asset",
        "asset__current_location",
        "asset__current_location__department",
        "allocated_to",
        "allocated_to_lab",
        "allocated_by",
    ).all()
    serializer_class = AllocationSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "create": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "partial_update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
    }
    filterset_fields = ["status", "asset", "allocated_to", "allocated_to_lab"]
    search_fields = ["asset__asset_id", "asset__name", "allocated_to__username"]
    ordering_fields = ["allocation_date", "expected_return_date", "actual_return_date"]

    def get_queryset(self):
        queryset = super().get_queryset()
        role = infer_user_role(self.request.user)

        if self.request.user.is_superuser or role in {ROLE_ADMIN, ROLE_DEAN}:
            return queryset

        if role == ROLE_LECTURER:
            return queryset.filter(allocated_to=self.request.user)

        department = self.user_department()
        if department is None:
            return queryset.none()

        return queryset.filter(asset__current_location__department=department)

    def perform_create(self, serializer):
        serializer.save(allocated_by=self.request.user)


class MaintenanceViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Maintenance.objects.select_related(
        "asset",
        "asset__current_location",
        "asset__current_location__department",
        "technician",
        "reported_by",
    ).all()
    serializer_class = MaintenanceSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "create": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
        "partial_update": [ROLE_ADMIN, ROLE_COD, ROLE_LAB_TECHNICIAN],
    }
    filterset_fields = ["status", "maintenance_type", "asset", "technician"]
    search_fields = ["asset__asset_id", "asset__name", "description", "resolution_notes"]
    ordering_fields = ["scheduled_date", "completed_date", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        role = infer_user_role(self.request.user)

        if self.request.user.is_superuser or role in {ROLE_ADMIN, ROLE_DEAN}:
            return queryset

        if role == ROLE_LECTURER:
            return queryset.filter(
                Q(reported_by=self.request.user) | Q(asset__allocations__allocated_to=self.request.user)
            ).distinct()

        department = self.user_department()
        if department is None:
            return queryset.none()

        return queryset.filter(asset__current_location__department=department)

    def perform_create(self, serializer):
        serializer.save(reported_by=self.request.user)


class AssetMovementViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AssetMovement.objects.select_related(
        "asset",
        "asset__current_location",
        "asset__current_location__department",
        "from_location",
        "from_location__department",
        "to_location",
        "to_location__department",
        "moved_by",
    ).all()
    serializer_class = AssetMovementSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
    }
    filterset_fields = ["asset", "from_location", "to_location", "moved_by"]
    search_fields = ["asset__asset_id", "asset__name", "notes", "moved_by__username"]
    ordering_fields = ["moved_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        role = infer_user_role(self.request.user)

        if self.request.user.is_superuser or role in {ROLE_ADMIN, ROLE_DEAN}:
            return queryset

        department = self.user_department()
        if department is None:
            return queryset.none()

        return queryset.filter(
            Q(asset__current_location__department=department)
            | Q(from_location__department=department)
            | Q(to_location__department=department)
        ).distinct()


class DepreciationRecordViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DepreciationRecord.objects.select_related(
        "asset",
        "asset__category",
        "asset__current_location",
        "asset__current_location__department",
    ).all()
    serializer_class = DepreciationRecordSerializer
    permission_classes = [RolePermission]
    allowed_roles = {
        "list": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
        "retrieve": [ROLE_ADMIN, ROLE_DEAN, ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER],
    }
    filterset_fields = ["asset", "year"]
    search_fields = ["asset__asset_id", "asset__name"]
    ordering_fields = ["year", "created_at", "net_book_value"]

    def get_queryset(self):
        queryset = super().get_queryset()
        return self.filter_department_queryset(queryset, "asset__current_location__department")


class DashboardReportView(ScopedQuerysetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        assets = self.filter_department_queryset(Asset.objects.all(), "current_location__department")
        allocations = self.filter_department_queryset(Allocation.objects.all(), "asset__current_location__department")
        maintenance = self.filter_department_queryset(Maintenance.objects.all(), "asset__current_location__department")

        return Response(
            {
                "total_assets": assets.count(),
                "available_assets": assets.filter(status="available").count(),
                "allocated_assets": assets.filter(status="allocated").count(),
                "maintenance_assets": assets.filter(status="maintenance").count(),
                "disposed_assets": assets.filter(status="disposed").count(),
                "active_allocations": allocations.filter(status__in=["active", "overdue"]).count(),
                "open_maintenance": maintenance.filter(status__in=["scheduled", "in_progress"]).count(),
            }
        )


class AssetDistributionReportView(ScopedQuerysetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        assets = self.filter_department_queryset(Asset.objects.all(), "current_location__department")
        data = list(
            assets.values("current_location__department__code", "current_location__department__name")
            .annotate(total_assets=Count("id"))
            .order_by("current_location__department__name")
        )
        return Response(data)


class MaintenanceHistoryReportView(ScopedQuerysetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        maintenance = self.filter_department_queryset(
            Maintenance.objects.select_related("asset", "technician", "reported_by").all(),
            "asset__current_location__department",
        )
        serializer = MaintenanceSerializer(maintenance, many=True)
        return Response(serializer.data)


class AssignedAssetsReportView(ScopedQuerysetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        allocations = self.filter_department_queryset(
            Allocation.objects.select_related("asset", "allocated_to", "allocated_to_lab", "allocated_by").filter(
                status__in=["active", "overdue"]
            ),
            "asset__current_location__department",
        )

        if user_has_role(request.user, ROLE_LECTURER):
            allocations = allocations.filter(allocated_to=request.user)

        serializer = AllocationSerializer(allocations, many=True)
        return Response(serializer.data)


class AssetMovementHistoryReportView(ScopedQuerysetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        movements = AssetMovement.objects.select_related(
            "asset",
            "asset__current_location",
            "asset__current_location__department",
            "from_location",
            "from_location__department",
            "to_location",
            "to_location__department",
            "moved_by",
        ).all()
        role = infer_user_role(request.user)

        if not (request.user.is_superuser or role in {ROLE_ADMIN, ROLE_DEAN}):
            department = self.user_department()
            if department is None:
                movements = movements.none()
            else:
                movements = movements.filter(
                    Q(asset__current_location__department=department)
                    | Q(from_location__department=department)
                    | Q(to_location__department=department)
                ).distinct()

        movements = movements.order_by("-moved_at")[:50]
        serializer = AssetMovementSerializer(movements, many=True)
        return Response(serializer.data)


class DepreciationSummaryReportView(ScopedQuerysetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        records = self.filter_department_queryset(
            DepreciationRecord.objects.select_related("asset", "asset__current_location", "asset__current_location__department"),
            "asset__current_location__department",
        )
        totals = records.aggregate(
            total_depreciation=Sum("depreciation_amount"),
            total_accumulated=Sum("accumulated_depreciation"),
            total_book_value=Sum("net_book_value"),
        )
        latest_records = records.order_by("-year", "asset__asset_id")[:20]
        return Response(
            {
                "totals": {
                    "total_depreciation": totals["total_depreciation"] or 0,
                    "total_accumulated": totals["total_accumulated"] or 0,
                    "total_book_value": totals["total_book_value"] or 0,
                },
                "records": DepreciationRecordSerializer(latest_records, many=True).data,
            }
        )


def previous_location_id(location):
    return getattr(location, "pk", None)
