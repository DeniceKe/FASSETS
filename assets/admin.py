from django.contrib import admin
from .models import (
    Asset, Category, Location, Supplier,
    AssetImage, AssetDocument, AssetMovement, DepreciationRecord
)

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
    search_fields = ("asset_id", "name", "serial_number", "description")
    inlines = [AssetImageInline, AssetDocumentInline]

admin.site.register(Category)
admin.site.register(Location)
admin.site.register(Supplier)
admin.site.register(AssetMovement)
admin.site.register(DepreciationRecord)