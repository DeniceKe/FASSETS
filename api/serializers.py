from rest_framework import serializers
from assets.models import Asset

class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = [
            "id", "asset_id", "name", "description",
            "purchase_date", "purchase_cost",
            "status", "condition",
            "category", "supplier", "current_location",
            "warranty_expiry", "serial_number",
            "created_at", "updated_at",
        ]
        read_only_fields = ["asset_id", "created_at", "updated_at"]