import uuid
from django.conf import settings
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


class Location(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="locations")
    building = models.CharField(max_length=100)
    floor = models.CharField(max_length=20, blank=True)
    room = models.CharField(max_length=20)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES)

    class Meta:
        unique_together = ('department', 'building', 'floor', 'room')

    def __str__(self) -> str:
        floor = f", Floor {self.floor}" if self.floor else ""
        return f"{self.department.code} - {self.building}{floor} - {self.room}"


class Category(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10)
    depreciation_years = models.PositiveIntegerField(default=5)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')

    class Meta:
        unique_together = ('code', 'name')

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


def asset_upload_path(instance, filename):
    return f"assets/{instance.asset.asset_id}/{filename}"


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

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assets_created", default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    disposed_at = models.DateTimeField(null=True, blank=True)

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
