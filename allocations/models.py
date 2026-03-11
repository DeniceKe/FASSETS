from django.conf import settings
from django.db import models
from django.utils import timezone

from assets.models import Asset, CONDITION_CHOICES

ALLOCATION_STATUS = [
    ('active', 'Active'),
    ('returned', 'Returned'),
    ('overdue', 'Overdue'),
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