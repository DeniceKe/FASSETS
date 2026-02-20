from django.contrib import admin
from .models import Asset, MaintenanceRecord, Department


admin.site.register(Department)

admin.site.register(Asset)


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ("asset", "issue", "started_at", "resolved_at")



