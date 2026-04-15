from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AllocationViewSet,
    AssetDistributionReportView,
    AssetMovementHistoryReportView,
    AssetViewSet,
    AssetMovementViewSet,
    AssignedAssetsReportView,
    CategoryViewSet,
    DepreciationRecordViewSet,
    DepreciationSummaryReportView,
    DashboardReportView,
    DepartmentViewSet,
    FacultyViewSet,
    HealthCheckView,
    LocationViewSet,
    MaintenanceHistoryReportView,
    MaintenanceViewSet,
    SupplierViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("faculties", FacultyViewSet, basename="faculty")
router.register("departments", DepartmentViewSet, basename="department")
router.register("users", UserViewSet, basename="user")
router.register("categories", CategoryViewSet, basename="category")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("locations", LocationViewSet, basename="location")
router.register("assets", AssetViewSet, basename="asset")
router.register("asset-movements", AssetMovementViewSet, basename="asset-movement")
router.register("depreciation-records", DepreciationRecordViewSet, basename="depreciation-record")
router.register("allocations", AllocationViewSet, basename="allocation")
router.register("maintenance", MaintenanceViewSet, basename="maintenance")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("reports/dashboard/", DashboardReportView.as_view(), name="report-dashboard"),
    path("reports/assets-by-department/", AssetDistributionReportView.as_view(), name="report-assets-by-department"),
    path("reports/maintenance-history/", MaintenanceHistoryReportView.as_view(), name="report-maintenance-history"),
    path("reports/assigned-assets/", AssignedAssetsReportView.as_view(), name="report-assigned-assets"),
    path("reports/asset-movements/", AssetMovementHistoryReportView.as_view(), name="report-asset-movements"),
    path("reports/depreciation-summary/", DepreciationSummaryReportView.as_view(), name="report-depreciation-summary"),
]
