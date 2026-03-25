from django.contrib import admin
from .models import Maintenance

@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display = ("asset", "maintenance_type", "status", "scheduled_date", "technician")
    list_filter = ("maintenance_type", "status")
    search_fields = ("asset__asset_id", "asset__name")