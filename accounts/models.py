from django.conf import settings
from django.db import models

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


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    employee_id = models.CharField(max_length=50, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return f"Profile: {self.user.username}"