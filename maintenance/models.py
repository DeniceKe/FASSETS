from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from assets.models import Asset

MAINTENANCE_TYPE = [
    ('preventive', 'Preventive'),
    ('corrective', 'Corrective'),
]

MAINTENANCE_STATUS = [
    ('scheduled', 'Scheduled'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]

class Maintenance(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="maintenance_records")
    maintenance_type = models.CharField(max_length=20, choices=MAINTENANCE_TYPE)

    scheduled_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)

    technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_tasks")
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_reports",
    )

    description = models.TextField()
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    parts_replaced = models.TextField(blank=True)
    resolution_notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=MAINTENANCE_STATUS, default='scheduled')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scheduled_date']

    def __str__(self) -> str:
        return f"{self.asset.asset_id} - {self.maintenance_type} - {self.status}"

    def clean(self):
        super().clean()

        if self.completed_date and self.completed_date < self.scheduled_date:
            raise ValidationError("Completed date cannot be earlier than the scheduled date.")

        if self.status == "completed" and not self.completed_date:
            self.completed_date = timezone.localdate()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        has_open_maintenance = self.asset.maintenance_records.filter(
            status__in=["scheduled", "in_progress"]
        ).exclude(pk=self.pk).exists()
        has_active_allocation = self.asset.allocations.filter(status__in=["active", "overdue"]).exists()

        if self.status in {"scheduled", "in_progress"}:
            self.asset.status = "maintenance"
        elif not has_open_maintenance:
            self.asset.status = "allocated" if has_active_allocation else "available"

        self.asset.save(update_fields=["status", "updated_at"])
