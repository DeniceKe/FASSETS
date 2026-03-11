from django.conf import settings
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

    description = models.TextField()
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    parts_replaced = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=MAINTENANCE_STATUS, default='scheduled')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scheduled_date']

    def __str__(self) -> str:
        return f"{self.asset.asset_id} - {self.maintenance_type} - {self.status}"