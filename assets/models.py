import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
import datetime
from accounts.models import Department

CONDITION_CHOICES = [
    ('new', 'New'),
    ('excellent', 'Excellent'),
    ('good', 'Good'),
    ('fair', 'Fair'),
    ('poor', 'Poor'),
    ('unserviceable', 'Unserviceable'),
]

STATUS_CHOICES = [
    ('available', 'Available'),
    ('allocated', 'Allocated'),
    ('maintenance', 'Under Maintenance'),
    ('disposed', 'Disposed'),
]

ROOM_TYPE_CHOICES = [
    ('office', 'Office'),
    ('lab', 'Laboratory'),
    ('storage', 'Storage'),
]

LOCATION_BUILDING_ABBREVIATIONS = {
    "physical science complex": "PSC",
}


class Location(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="locations")
    building = models.CharField(max_length=100)
    floor = models.CharField(max_length=20, blank=True)
    room = models.CharField(max_length=20)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES)

    class Meta:
        unique_together = ('department', 'building', 'floor', 'room')

    def short_building_name(self) -> str:
        building_name = (self.building or "").strip()
        normalized_building_name = building_name.casefold()
        for phrase, abbreviation in LOCATION_BUILDING_ABBREVIATIONS.items():
            if phrase in normalized_building_name:
                start = normalized_building_name.index(phrase)
                end = start + len(phrase)
                return f"{building_name[:start]}{abbreviation}{building_name[end:]}".strip()
        return building_name

    @property
    def short_label(self) -> str:
        floor = f", Floor {self.floor}" if self.floor else ""
        return f"{self.department.code} - {self.short_building_name()}{floor} - {self.room}"

    def __str__(self) -> str:
        floor = f", Floor {self.floor}" if self.floor else ""
        return f"{self.department.code} - {self.building}{floor} - {self.room}"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    depreciation_years = models.PositiveIntegerField(default=5)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')

    def __str__(self) -> str:
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


def asset_upload_path(instance, filename):
    return f"assets/{instance.asset.asset_id}/{filename}"


def asset_thumbnail_upload_path(instance, filename):
    return f"assets/{instance.asset_id}/thumbnails/{filename}"


class Asset(models.Model):
    asset_id = models.CharField(max_length=20, unique=True, blank=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="assets", default=1)
    description = models.TextField(blank=True)

    purchase_date = models.DateField(default=datetime.datetime.now)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets")

    current_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="assets")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='good')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')

    warranty_expiry = models.DateField(null=True, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)

    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True)
    thumbnail = models.ImageField(upload_to=asset_thumbnail_upload_path, blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assets_created", default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    disposed_at = models.DateTimeField(null=True, blank=True)
    disposal_reason = models.TextField(blank=True)
    disposal_reference = models.CharField(max_length=100, blank=True)

    def clean(self):
        super().clean()

        if self.status != "disposed":
            return

        if not self.disposal_reason.strip():
            raise ValidationError({"disposal_reason": "Provide a disposal reason before marking an asset as disposed."})

        if self.pk and self.allocations.filter(status__in=["active", "overdue"]).exists():
            raise ValidationError("Return or close active allocations before disposing of this asset.")

        if self.pk and self.maintenance_records.filter(status__in=["scheduled", "in_progress"]).exists():
            raise ValidationError("Complete or cancel open maintenance before disposing of this asset.")

    def save(self, *args, **kwargs):
        from .services import sync_asset_disposal_state

        previous_status = None
        if self.pk:
            previous_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()

        lifecycle_update_fields = sync_asset_disposal_state(self, previous_status=previous_status)
        self.full_clean()

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and lifecycle_update_fields:
            kwargs["update_fields"] = list({*update_fields, *lifecycle_update_fields})

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.asset_id} - {self.name}"

    @property
    def department(self):
        return self.current_location.department


class AssetImage(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=asset_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Image for {self.asset.asset_id}"


class AssetDocument(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=asset_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Doc {self.title} for {self.asset.asset_id}"


class AssetMovement(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="movements")
    from_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="movements_out")
    to_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="movements_in")
    moved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movements_made")
    moved_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.asset.asset_id}: {self.from_location} -> {self.to_location}"


class DepreciationRecord(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="depreciation_records")
    year = models.PositiveIntegerField()
    depreciation_amount = models.DecimalField(max_digits=12, decimal_places=2)
    accumulated_depreciation = models.DecimalField(max_digits=12, decimal_places=2)
    net_book_value = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('asset', 'year')
        ordering = ['year']

    def __str__(self) -> str:
        return f"{self.asset.asset_id} - {self.year}"
