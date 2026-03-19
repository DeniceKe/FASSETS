from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from accounts.models import Department, Faculty, Profile
from assets.models import Asset, Category, Location, Supplier
from allocations.models import Allocation
from maintenance.models import Maintenance

User = get_user_model()


class FacultySerializer(serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = ["id", "name"]


class DepartmentSerializer(serializers.ModelSerializer):
    faculty_name = serializers.CharField(source="faculty.name", read_only=True)

    class Meta:
        model = Department
        fields = ["id", "code", "name", "faculty", "faculty_name"]


class LocationSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Location
        fields = ["id", "department", "department_name", "building", "floor", "room", "room_type"]


class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "code", "depreciation_years", "parent", "parent_name"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "email", "phone", "address"]


class ProfileSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Profile
        fields = ["employee_id", "department", "department_name", "role"]


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    employee_id = serializers.CharField(source="profile.employee_id", required=False, allow_blank=True)
    department = serializers.PrimaryKeyRelatedField(
        source="profile.department",
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
    )
    department_name = serializers.CharField(source="profile.department.name", read_only=True)
    role = serializers.CharField(source="profile.role", required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "password",
            "employee_id",
            "department",
            "department_name",
            "role",
        ]

    @transaction.atomic
    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", None) or User.objects.make_random_password()
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save(update_fields=["password"])

        profile = user.profile
        for field, value in profile_data.items():
            setattr(profile, field, value)
        profile.save()
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()

        profile = instance.profile
        for field, value in profile_data.items():
            setattr(profile, field, value)
        profile.save()
        return instance


class AssetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    current_location_label = serializers.SerializerMethodField()
    department_name = serializers.CharField(source="current_location.department.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_id",
            "name",
            "category",
            "category_name",
            "description",
            "purchase_date",
            "purchase_cost",
            "supplier",
            "supplier_name",
            "current_location",
            "current_location_label",
            "department_name",
            "condition",
            "status",
            "warranty_expiry",
            "serial_number",
            "barcode",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
            "disposed_at",
        ]
        read_only_fields = ["asset_id", "created_by", "created_at", "updated_at"]

    def get_current_location_label(self, obj):
        return str(obj.current_location)


class AllocationSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    asset_identifier = serializers.CharField(source="asset.asset_id", read_only=True)
    allocated_to_username = serializers.CharField(source="allocated_to.username", read_only=True)
    allocated_to_lab_label = serializers.SerializerMethodField()
    allocated_by_username = serializers.CharField(source="allocated_by.username", read_only=True)

    class Meta:
        model = Allocation
        fields = [
            "id",
            "asset",
            "asset_name",
            "asset_identifier",
            "allocated_to",
            "allocated_to_username",
            "allocated_to_lab",
            "allocated_to_lab_label",
            "allocated_by",
            "allocated_by_username",
            "allocation_date",
            "expected_return_date",
            "actual_return_date",
            "purpose",
            "condition_out",
            "condition_in",
            "status",
        ]
        read_only_fields = ["allocated_by"]

    def get_allocated_to_lab_label(self, obj):
        return str(obj.allocated_to_lab) if obj.allocated_to_lab else ""


class MaintenanceSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    asset_identifier = serializers.CharField(source="asset.asset_id", read_only=True)
    technician_username = serializers.CharField(source="technician.username", read_only=True)
    reported_by_username = serializers.CharField(source="reported_by.username", read_only=True)

    class Meta:
        model = Maintenance
        fields = [
            "id",
            "asset",
            "asset_name",
            "asset_identifier",
            "maintenance_type",
            "scheduled_date",
            "completed_date",
            "technician",
            "technician_username",
            "reported_by",
            "reported_by_username",
            "description",
            "cost",
            "parts_replaced",
            "resolution_notes",
            "status",
            "created_at",
        ]
        read_only_fields = ["reported_by", "created_at"]
