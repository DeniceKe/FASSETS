from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AllocationViewSet,
    AssetDistributionReportView,
    AssetViewSet,
    AssignedAssetsReportView,
    CategoryViewSet,
    DashboardReportView,
    DepartmentViewSet,
    FacultyViewSet,
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
router.register("allocations", AllocationViewSet, basename="allocation")
router.register("maintenance", MaintenanceViewSet, basename="maintenance")

urlpatterns = [
    path("", include(router.urls)),
    path("reports/dashboard/", DashboardReportView.as_view(), name="report-dashboard"),
    path("reports/assets-by-department/", AssetDistributionReportView.as_view(), name="report-assets-by-department"),
    path("reports/maintenance-history/", MaintenanceHistoryReportView.as_view(), name="report-maintenance-history"),
    path("reports/assigned-assets/", AssignedAssetsReportView.as_view(), name="report-assigned-assets"),
]
