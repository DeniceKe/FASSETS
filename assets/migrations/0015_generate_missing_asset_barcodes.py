from django.db import migrations
from django.db.models import F, Q


def populate_missing_barcodes(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")
    (
        Asset.objects
        .exclude(asset_id__isnull=True)
        .exclude(asset_id="")
        .filter(Q(barcode__isnull=True) | Q(barcode=""))
        .update(barcode=F("asset_id"))
    )


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0014_asset_thumbnail"),
    ]

    operations = [
        migrations.RunPython(populate_missing_barcodes, migrations.RunPython.noop),
    ]
