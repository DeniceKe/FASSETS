from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    DepartmentViewSet,
    AssetViewSet,
    MaintenanceRecordViewSet,
)

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="departments")
# router.register(r"categories", AssetCategoryViewSet, basename="categories")
router.register(r"assets", AssetViewSet, basename="assets")
# router.register(r"assignments", AssetAssignmentViewSet, basename="assignments")
router.register(r"maintenance", MaintenanceRecordViewSet, basename="maintenance")

urlpatterns = [
    path("", include(router.urls)),
]
