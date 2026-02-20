from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("DEAN", "Dean of Faculty"),
        ("FAC_ADMIN", "Faculty Administrator"),
        ("COD", "Chair of Department"),
        ("LECTURER", "Lecturer"),
        ("LAB_TECH", "Lab Technician"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    # ✅ SAFE STRING REFERENCE (NO IMPORT)
    department = models.ForeignKey(
        "assets.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


