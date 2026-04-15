from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from accounts.models import Department, Faculty, Profile
from accounts.roles import ROLE_ADMIN, ROLE_COD, ROLE_DEAN, infer_user_role
from assets.models import Asset, AssetMovement, Category, DepreciationRecord, Location, Supplier
from allocations.models import Allocation
from maintenance.models import Maintenance

User = get_user_model()


def cod_actor_department(request):
    if not request or not request.user.is_authenticated:
        return None

    actor = request.user
    actor_role = infer_user_role(actor)
    if actor.is_superuser or actor_role in {ROLE_ADMIN, ROLE_DEAN}:
        return None

    if actor_role != ROLE_COD:
        return None

    actor_department = getattr(getattr(actor, "profile", None), "department", None)
    if actor_department is None:
        raise serializers.ValidationError("A CoD account must belong to a department before managing department records.")

    return actor_department


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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        actor_department = cod_actor_department(self.context.get("request"))
        if actor_department is None:
            return attrs

        department = attrs.get("department", getattr(self.instance, "department", None))
        if department != actor_department:
            raise serializers.ValidationError("CoD users can only manage locations in their own department.")

        return attrs


class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "depreciation_years", "parent", "parent_name"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "email", "phone", "address"]


class ProfileSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    staff_location_label = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["employee_id", "department", "department_name", "staff_location", "staff_location_label", "role"]

    def get_staff_location_label(self, obj):
        return str(obj.staff_location) if obj.staff_location else ""


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    employee_id = serializers.CharField(source="profile.employee_id", required=False, allow_blank=True)
    registration_number = serializers.CharField(source="profile.registration_number", required=False, allow_blank=True)
    user_type = serializers.CharField(source="profile.user_type", required=False, allow_blank=True)
    department = serializers.PrimaryKeyRelatedField(
        source="profile.department",
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
    )
    department_name = serializers.CharField(source="profile.department.name", read_only=True)
    staff_location = serializers.PrimaryKeyRelatedField(
        source="profile.staff_location",
        queryset=Location.objects.select_related("department").all(),
        required=False,
        allow_null=True,
    )
    staff_location_label = serializers.SerializerMethodField()
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
            "registration_number",
            "user_type",
            "department",
            "department_name",
            "staff_location",
            "staff_location_label",
            "role",
        ]

    def get_staff_location_label(self, obj):
        return str(obj.profile.staff_location) if getattr(obj.profile, "staff_location", None) else ""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        profile_data = attrs.setdefault("profile", {})
        request = self.context.get("request")
        requested_department = profile_data.get("department", getattr(getattr(self.instance, "profile", None), "department", None))
        requested_staff_location = profile_data.get("staff_location", getattr(getattr(self.instance, "profile", None), "staff_location", None))

        if requested_staff_location is not None and requested_department is not None and requested_staff_location.department != requested_department:
            raise serializers.ValidationError("The selected office or lab must belong to the same department as the user.")

        if not request or not request.user.is_authenticated:
            return attrs

        actor = request.user
        actor_role = infer_user_role(actor)
        if actor.is_superuser or actor_role in {ROLE_ADMIN, ROLE_DEAN}:
            return attrs

        if actor_role != ROLE_COD:
            return attrs

        actor_department = getattr(getattr(actor, "profile", None), "department", None)
        if actor_department is None:
            raise serializers.ValidationError("A CoD account must belong to a department before managing users.")

        has_department_value = "department" in profile_data
        requested_role = profile_data.get("role")

        if self.instance is None and requested_department is None:
            profile_data["department"] = actor_department
            requested_department = actor_department
        elif has_department_value and requested_department is None:
            raise serializers.ValidationError("CoD users cannot remove a user's department assignment.")
        elif requested_department is not None and requested_department != actor_department:
            raise serializers.ValidationError("CoD users can only manage users in their own department.")

        resolved_department = requested_department or getattr(getattr(self.instance, "profile", None), "department", None)
        resolved_staff_location = requested_staff_location if "staff_location" in profile_data else getattr(getattr(self.instance, "profile", None), "staff_location", None)

        if requested_role in {ROLE_ADMIN, ROLE_DEAN}:
            raise serializers.ValidationError("CoD users cannot assign Admin or Dean roles.")

        if resolved_staff_location is not None and resolved_department is not None and resolved_staff_location.department != resolved_department:
            raise serializers.ValidationError("The selected office or lab must belong to the same department as the user.")

        return attrs

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
    thumbnail_url = serializers.SerializerMethodField()

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
            "thumbnail",
            "thumbnail_url",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
            "disposed_at",
            "disposal_reason",
            "disposal_reference",
        ]
        read_only_fields = ["asset_id", "created_by", "created_at", "updated_at", "thumbnail_url", "disposed_at"]

    def get_current_location_label(self, obj):
        return str(obj.current_location)

    def get_thumbnail_url(self, obj):
        request = self.context.get("request")
        if not obj.thumbnail:
            return ""
        url = obj.thumbnail.url
        normalized_url = url if url.startswith("/") else f"/{url}"
        return request.build_absolute_uri(normalized_url) if request else normalized_url

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        actor_department = cod_actor_department(self.context.get("request"))
        current_location = attrs.get("current_location", getattr(instance, "current_location", None))
        if actor_department is not None and current_location and current_location.department != actor_department:
            raise serializers.ValidationError("CoD users can only manage assets in their own department.")

        status = attrs.get("status", getattr(instance, "status", "available"))
        disposal_reason = attrs.get("disposal_reason", getattr(instance, "disposal_reason", ""))

        if status == "disposed":
            if not str(disposal_reason or "").strip():
                raise serializers.ValidationError(
                    {"disposal_reason": ["Provide a disposal reason before marking an asset as disposed."]}
                )

            if instance is not None:
                if instance.allocations.filter(status__in=["active", "overdue"]).exists():
                    raise serializers.ValidationError(
                        "Return or close active allocations before disposing of this asset."
                    )

                if instance.maintenance_records.filter(status__in=["scheduled", "in_progress"]).exists():
                    raise serializers.ValidationError(
                        "Complete or cancel open maintenance before disposing of this asset."
                    )

        return attrs


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
            "allocation_type",
            "allocation_date",
            "expected_return_date",
            "actual_return_date",
            "purpose",
            "condition_out",
            "condition_in",
            "status",
        ]
        read_only_fields = ["allocated_by"]

    def validate(self, attrs):
        attrs = super().validate(attrs)

        instance = self.instance
        allocation_type = attrs.get("allocation_type", getattr(instance, "allocation_type", "temporary"))
        asset = attrs.get("asset", getattr(instance, "asset", None))
        allocated_to = attrs.get("allocated_to", getattr(instance, "allocated_to", None))
        allocated_to_lab = attrs.get("allocated_to_lab", getattr(instance, "allocated_to_lab", None))
        allocation_date = attrs.get("allocation_date", getattr(instance, "allocation_date", None))
        expected_return_date = attrs.get("expected_return_date", getattr(instance, "expected_return_date", None))

        if bool(allocated_to) == bool(allocated_to_lab):
            raise serializers.ValidationError("Allocate the asset to exactly one recipient: a user or a laboratory.")

        if allocation_type == "temporary" and not expected_return_date:
            raise serializers.ValidationError("Temporary allocations require an expected return date.")

        if allocation_type == "permanent":
            attrs["expected_return_date"] = None
            expected_return_date = None

        if expected_return_date and allocation_date and expected_return_date < allocation_date:
            raise serializers.ValidationError("Expected return date cannot be earlier than the allocation date.")

        actor_department = cod_actor_department(self.context.get("request"))
        if actor_department is not None:
            if asset is None or asset.current_location.department != actor_department:
                raise serializers.ValidationError("CoD users can only allocate assets from their own department.")

            if allocated_to is not None:
                recipient_department = getattr(getattr(allocated_to, "profile", None), "department", None)
                if recipient_department != actor_department:
                    raise serializers.ValidationError("CoD users can only allocate assets to users in their own department.")

            if allocated_to_lab is not None and allocated_to_lab.department != actor_department:
                raise serializers.ValidationError("CoD users can only allocate assets to laboratories in their own department.")

        return attrs

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

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

    def validate(self, attrs):
        attrs = super().validate(attrs)

        instance = self.instance
        asset = attrs.get("asset", getattr(instance, "asset", None))
        technician = attrs.get("technician", getattr(instance, "technician", None))
        scheduled_date = attrs.get("scheduled_date", getattr(instance, "scheduled_date", None))
        completed_date = attrs.get("completed_date", getattr(instance, "completed_date", None))

        if completed_date and scheduled_date and completed_date < scheduled_date:
            raise serializers.ValidationError("Completed date cannot be earlier than the scheduled date.")

        if asset is not None and asset.status == "disposed":
            raise serializers.ValidationError("Disposed assets cannot be scheduled for maintenance.")

        actor_department = cod_actor_department(self.context.get("request"))
        if actor_department is not None:
            if asset is None or asset.current_location.department != actor_department:
                raise serializers.ValidationError("CoD users can only manage maintenance records for assets in their own department.")

            if technician is not None:
                technician_department = getattr(getattr(technician, "profile", None), "department", None)
                if technician_department != actor_department:
                    raise serializers.ValidationError("CoD users can only assign technicians from their own department.")

        return attrs

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class AssetMovementSerializer(serializers.ModelSerializer):
    asset_identifier = serializers.CharField(source="asset.asset_id", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    from_location_label = serializers.SerializerMethodField()
    to_location_label = serializers.SerializerMethodField()
    moved_by_username = serializers.CharField(source="moved_by.username", read_only=True)

    class Meta:
        model = AssetMovement
        fields = [
            "id",
            "asset",
            "asset_identifier",
            "asset_name",
            "from_location",
            "from_location_label",
            "to_location",
            "to_location_label",
            "moved_by",
            "moved_by_username",
            "moved_at",
            "notes",
        ]
        read_only_fields = fields

    def get_from_location_label(self, obj):
        return str(obj.from_location)

    def get_to_location_label(self, obj):
        return str(obj.to_location)


class DepreciationRecordSerializer(serializers.ModelSerializer):
    asset_identifier = serializers.CharField(source="asset.asset_id", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)

    class Meta:
        model = DepreciationRecord
        fields = [
            "id",
            "asset",
            "asset_identifier",
            "asset_name",
            "year",
            "depreciation_amount",
            "accumulated_depreciation",
            "net_book_value",
            "created_at",
        ]
        read_only_fields = fields
