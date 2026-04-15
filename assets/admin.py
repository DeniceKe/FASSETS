from django.contrib import admin
from .models import (
    Asset, Category, Location, Supplier,
    AssetImage, AssetDocument, AssetMovement, DepreciationRecord
)
from .services import record_asset_movement, sync_asset_depreciation, sync_asset_disposal_state

class AssetImageInline(admin.TabularInline):
    model = AssetImage
    extra = 0

class AssetDocumentInline(admin.TabularInline):
    model = AssetDocument
    extra = 0

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("asset_id", "name", "category", "status", "condition", "current_location", "purchase_date")
    list_filter = ("status", "condition", "category", "current_location__department")
    search_fields = ("asset_id", "barcode", "name", "serial_number", "description")
    readonly_fields = ("asset_id", "barcode", "disposed_at")
    inlines = [AssetImageInline, AssetDocumentInline]

    def save_model(self, request, obj, form, change):
        previous_location = None
        previous_status = None
        if change and obj.pk:
            previous_asset = Asset.objects.get(pk=obj.pk)
            previous_location = previous_asset.current_location
            previous_status = previous_asset.status

        super().save_model(request, obj, form, change)
        disposal_update_fields = sync_asset_disposal_state(obj, previous_status=previous_status)
        if disposal_update_fields:
            disposal_update_fields.append("updated_at")
            obj.save(update_fields=disposal_update_fields)
        sync_asset_depreciation(obj)

        if previous_location and previous_location_id(previous_location) != previous_location_id(obj.current_location):
            record_asset_movement(
                asset=obj,
                from_location=previous_location,
                to_location=obj.current_location,
                moved_by=request.user,
                notes="Location updated from Django admin.",
            )


def previous_location_id(location):
    return getattr(location, "pk", None)

@admin.register(AssetMovement)
class AssetMovementAdmin(admin.ModelAdmin):
    list_display = ("asset", "from_location", "to_location", "moved_by", "moved_at")
    list_filter = ("from_location__department", "to_location__department", "moved_at")
    search_fields = ("asset__asset_id", "asset__name", "moved_by__username", "notes")


@admin.register(DepreciationRecord)
class DepreciationRecordAdmin(admin.ModelAdmin):
    list_display = ("asset", "year", "depreciation_amount", "accumulated_depreciation", "net_book_value")
    list_filter = ("year",)
    search_fields = ("asset__asset_id", "asset__name")


admin.site.register(Category)
admin.site.register(Location)
admin.site.register(Supplier)
