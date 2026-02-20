from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


# =========================
# Department
# =========================
class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.name




# =========================
# Asset
# =========================
class Asset(models.Model):
    STATUS_CHOICES = [
        ("AVAILABLE", "Available"),
        ("ASSIGNED", "Assigned"),
        ("MAINTENANCE", "Maintenance"),
        ("LOST", "Lost"),
        ("DISPOSED", "Disposed"),
    ]

    asset_tag = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique asset identification code",
        auto_created=True,
        
    )
    
    name = models.CharField(max_length=200)

    # category = models.ForeignKey(
    #     AssetCategory,
    #     on_delete=models.PROTECT,
    #     related_name="assets"
    # )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="assets"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="AVAILABLE"
    )
    
    # assignment = models.CharField(max_length=200, blank=True, null=True)
    # def clean(self):
    #     if not self.pk and self.asset.status != "AVAILABLE":
    #         raise ValidationError("Asset is not available for assignment.")

    # def save(self, *args, **kwargs):
    #     self.clean()

    #     if not self.pk:
    #         self.asset.status = "ASSIGNED"
    #         self.asset.save(update_fields=["status"])

    #     if self.pk and self.returned_at:
    #         self.asset.status = "AVAILABLE"
    #         self.asset.save(update_fields=["status"])

    #     super().save(*args, **kwargs)

    # def __str__(self):
    #     return f"{self.asset} → {self.assigned_to}"
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.asset_tag} - {self.name}"


# =========================
# Asset Assignment
# =========================
# class AssetAssignment(models.Model):
#     asset = models.ForeignKey(
#         Asset,
#         on_delete=models.PROTECT,
#         related_name="assignments"
#     )

#     assigned_to = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.PROTECT,
#         related_name="assigned_assets"
#     )

#     assigned_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.PROTECT,
#         related_name="issued_assets"
#     )

#     assigned_at = models.DateTimeField(auto_now_add=True)
#     returned_at = models.DateTimeField(blank=True, null=True)




# =========================
# Maintenance Record
# =========================
class MaintenanceRecord(models.Model):
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="maintenance_records"
    )

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    issue = models.CharField(max_length=255)
    started_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.asset.status = "MAINTENANCE"
            self.asset.save(update_fields=["status"])

        if self.pk and self.resolved_at:
            self.asset.status = "AVAILABLE"
            self.asset.save(update_fields=["status"])

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Maintenance - {self.asset.asset_tag}"




        
  





