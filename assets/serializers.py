from rest_framework import serializers
from .models import Department, Asset, MaintenanceRecord


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = "__all__"


# class AssetCategorySerializer(serializers.ModelSerializer):
#     class Meta:
#         model = AssetCategory
#         fields = "__all__"


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = "__all__"


# class AssetAssignmentSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = AssetAssignment
#         fields = "__all__"


class MaintenanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceRecord
        fields = "__all__"
