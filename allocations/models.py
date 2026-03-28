from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from assets.models import Asset, CONDITION_CHOICES

ALLOCATION_STATUS = [
    ('active', 'Active'),
    ('returned', 'Returned'),
    ('overdue', 'Overdue'),
]

REQUEST_STATUS = [
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled'),
]

class Allocation(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="allocations")
    allocated_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="allocations_received")
    allocated_to_lab = models.ForeignKey('assets.Location', on_delete=models.PROTECT, null=True, blank=True, related_name="lab_allocations")

    allocated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="allocations_made")

    allocation_date = models.DateField(default=timezone.now)
    expected_return_date = models.DateField()
    actual_return_date = models.DateField(null=True, blank=True)

    purpose = models.TextField()

    condition_out = models.CharField(max_length=20, choices=CONDITION_CHOICES)
    condition_in = models.CharField(max_length=20, choices=CONDITION_CHOICES, null=True, blank=True)

    status = models.CharField(max_length=20, choices=ALLOCATION_STATUS, default='active')

    class Meta:
        ordering = ['-allocation_date']

    def __str__(self) -> str:
        return f"{self.asset.asset_id} -> {self.allocated_to or self.allocated_to_lab}"

    def clean(self):
        super().clean()

        if bool(self.allocated_to) == bool(self.allocated_to_lab):
            raise ValidationError("Allocate the asset to exactly one recipient: a user or a laboratory.")

        if self.expected_return_date and self.allocation_date and self.expected_return_date < self.allocation_date:
            raise ValidationError("Expected return date cannot be earlier than the allocation date.")

        active_statuses = {"active", "overdue"}
        if self.status in active_statuses and self.actual_return_date:
            self.status = "returned"

        if self.status == "returned" and not self.actual_return_date:
            self.actual_return_date = timezone.localdate()

        conflicting_allocations = Allocation.objects.filter(asset=self.asset, status__in=active_statuses)
        if self.pk:
            conflicting_allocations = conflicting_allocations.exclude(pk=self.pk)

        if self.status in active_statuses and conflicting_allocations.exists():
            raise ValidationError("This asset already has an active allocation.")

        if self.pk is None and self.asset.status != "available":
            raise ValidationError("Only available assets can be allocated.")

    def save(self, *args, **kwargs):
        if self.status == "active" and self.expected_return_date < timezone.localdate():
            self.status = "overdue"

        self.full_clean()
        super().save(*args, **kwargs)

        active_exists = self.asset.allocations.filter(status__in=["active", "overdue"]).exclude(pk=self.pk).exists()
        if self.status in {"active", "overdue"}:
            self.asset.status = "allocated"
        elif self.asset.status == "allocated" and not active_exists:
            self.asset.status = "available"
        self.asset.save(update_fields=["status", "updated_at"])


class AssetRequest(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="requests")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="asset_requests")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asset_requests_reviewed",
    )
    status = models.CharField(max_length=20, choices=REQUEST_STATUS, default="pending")
    message = models.TextField(blank=True)
    decline_reason = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self) -> str:
        return f"{self.asset.asset_id} request by {self.requested_by.username}"

    def clean(self):
        super().clean()

        if self.asset.status != "available" and self.status == "pending":
            raise ValidationError("Only available assets can be requested.")

        if self.status == "rejected" and not self.decline_reason.strip():
            raise ValidationError("A decline reason is required when rejecting a request.")

        existing_pending = AssetRequest.objects.filter(
            asset=self.asset,
            requested_by=self.requested_by,
            status="pending",
        )
        if self.pk:
            existing_pending = existing_pending.exclude(pk=self.pk)

        if existing_pending.exists():
            raise ValidationError("You already have a pending request for this asset.")

    def save(self, *args, **kwargs):
        if self.status != "rejected":
            self.decline_reason = ""
        self.full_clean()
        super().save(*args, **kwargs)
