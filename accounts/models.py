from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models


ROLE_ADMIN = "admin"
ROLE_DEAN = "dean"
ROLE_COD = "cod"
ROLE_LECTURER = "lecturer"
ROLE_LAB_TECHNICIAN = "lab_technician"
ROLE_INTERNAL_AUDITOR = "internal_auditor"

ROLE_CHOICES = [
    (ROLE_ADMIN, "Admin"),
    (ROLE_DEAN, "Dean"),
    (ROLE_COD, "COD"),
    (ROLE_LECTURER, "Lecturer"),
    (ROLE_LAB_TECHNICIAN, "Lab Technician"),
    (ROLE_INTERNAL_AUDITOR, "Auditor"),
]

USER_TYPE_STUDENT = "student"
USER_TYPE_STAFF = "staff"

USER_TYPE_CHOICES = [
    (USER_TYPE_STUDENT, "Student"),
    (USER_TYPE_STAFF, "Staff"),
]


class Faculty(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self) -> str:
        return self.name


class Department(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="departments")

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


def profile_photo_upload_path(instance, filename):
    return f"profiles/{instance.user_id}/{filename}"


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    employee_id = models.CharField(max_length=50, blank=True)
    registration_number = models.CharField(max_length=50, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    staff_location = models.ForeignKey(
        "assets.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_profiles",
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, blank=True)
    photo = models.ImageField(upload_to=profile_photo_upload_path, blank=True, null=True)

    def __str__(self) -> str:
        return f"Profile: {self.user.username}"

    @property
    def effective_role(self) -> str:
        if self.user.is_superuser:
            return ROLE_ADMIN
        return self.role or ""


class AuditLog(models.Model):
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    target_object_id = models.CharField(max_length=64, blank=True)
    target_repr = models.CharField(max_length=255)
    source = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        target_label = self.target_repr or "Unknown target"
        actor_label = self.actor_username or "Unknown actor"
        return f"{self.get_action_display()} {target_label} by {actor_label}"
