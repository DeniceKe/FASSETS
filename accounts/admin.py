from django.contrib import admin
from .models import AuditLog, Faculty, Department, Profile

admin.site.register(Faculty)
admin.site.register(Department)
admin.site.register(Profile)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "target_repr", "actor_username", "source")
    list_filter = ("action", "target_content_type")
    search_fields = ("target_repr", "actor_username", "source")
    readonly_fields = (
        "actor",
        "actor_username",
        "action",
        "target_content_type",
        "target_object_id",
        "target_repr",
        "source",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
