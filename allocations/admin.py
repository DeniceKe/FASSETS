from django.contrib import admin
from .models import Allocation

@admin.register(Allocation)
class AllocationAdmin(admin.ModelAdmin):
    list_display = ("asset", "allocated_to", "allocated_to_lab", "status", "allocation_date", "expected_return_date")
    list_filter = ("status",)
    search_fields = ("asset__asset_id", "asset__name", "allocated_to__username")