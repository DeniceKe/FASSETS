from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Department, Asset, MaintenanceRecord
from .serializers import (
    DepartmentSerializer,
    AssetSerializer,
    MaintenanceRecordSerializer,
)




class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all().order_by("name")
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]


# class AssetCategoryViewSet(viewsets.ModelViewSet):
#     queryset = AssetCategory.objects.all().order_by("name")
#     serializer_class = AssetCategorySerializer
#     permission_classes = [IsAuthenticated]


class AssetViewSet(viewsets.ModelViewSet):
    queryset = Asset.objects.all().order_by("-created_at")
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated]


# class AssetAssignmentViewSet(viewsets.ModelViewSet):
#     queryset = AssetAssignment.objects.all().order_by("-assigned_at")
#     serializer_class = AssetAssignmentSerializer
#     permission_classes = [IsAuthenticated]


class MaintenanceRecordViewSet(viewsets.ModelViewSet):
    queryset = MaintenanceRecord.objects.all().order_by("-started_at")
    serializer_class = MaintenanceRecordSerializer
    permission_classes = [IsAuthenticated]
