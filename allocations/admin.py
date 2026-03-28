from django.contrib import admin
from .models import Allocation, AssetRequest

@admin.register(Allocation)
class AllocationAdmin(admin.ModelAdmin):
    list_display = ("asset", "allocated_to", "allocated_to_lab", "status", "allocation_date", "expected_return_date")
    list_filter = ("status",)
    search_fields = ("asset__asset_id", "asset__name", "allocated_to__username")


@admin.register(AssetRequest)
class AssetRequestAdmin(admin.ModelAdmin):
    list_display = ("asset", "requested_by", "status", "requested_at", "reviewed_by", "reviewed_at")
    list_filter = ("status", "requested_at", "reviewed_at")
    search_fields = ("asset__asset_id", "asset__name", "requested_by__username", "decline_reason")
    readonly_fields = ("requested_at", "updated_at", "reviewed_at")
